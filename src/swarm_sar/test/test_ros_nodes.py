"""
In-process test of the ROS 2 nodes (skipped unless ROS 2, px4_msgs and the interfaces are sourced).

A probe node plays PX4 and the depth camera: it streams vehicle status (armed,
offboard), attitude, local position, camera info and open-space depth frames,
and publishes a mission. The drone node runs in shadow mode. The test checks
that the drone accepts the mission, broadcasts its state, publishes shadow
setpoints and publishes nothing at all to PX4, and that the monitor publishes
metrics for it.
"""

import array
import math
import time

import numpy as np
import pytest

rclpy = pytest.importorskip('rclpy')
pytest.importorskip('swarm_sar_interfaces.msg')
pytest.importorskip('px4_msgs.msg')
pytest.importorskip('sensor_msgs.msg')

from px4_msgs.msg import (TrajectorySetpoint, VehicleAttitude,  # noqa: E402, I100
                          VehicleLocalPosition, VehicleStatus)
from rclpy.executors import SingleThreadedExecutor  # noqa: E402
from rclpy.parameter import Parameter  # noqa: E402
from sensor_msgs.msg import CameraInfo, Image  # noqa: E402
from swarm_sar.core.messages import Phase  # noqa: E402
from swarm_sar.mission_file import example_mission, parse_mission  # noqa: E402
from swarm_sar.ros.codec import Codec, MessageTypes  # noqa: E402
from swarm_sar.ros.drone_node import DroneNode  # noqa: E402
from swarm_sar.ros.monitor_node import MonitorNode  # noqa: E402
from swarm_sar.ros.topics import METRICS_TOPIC, MISSION_TOPIC, STATUS_TOPIC  # noqa: E402
from swarm_sar.ros.util import (broadcast_qos, latched_qos, px4_qos,  # noqa: E402
                                reliable_qos, sensor_qos)
from swarm_sar_interfaces.msg import DroneState, SwarmMetrics  # noqa: E402

WIDTH, HEIGHT = 64, 36
FX = (WIDTH / 2.0) / math.tan(math.radians(87.0) / 2.0)
DRONE_ID = 4


@pytest.fixture
def ros_context():
    rclpy.init()
    yield
    rclpy.try_shutdown()


def _vehicle_messages(probe, spec):
    stamp_us = probe.get_clock().now().nanoseconds // 1000
    status = VehicleStatus()
    status.timestamp = stamp_us
    status.arming_state = VehicleStatus.ARMING_STATE_ARMED
    status.nav_state = VehicleStatus.NAVIGATION_STATE_OFFBOARD
    attitude = VehicleAttitude()
    attitude.timestamp = stamp_us
    attitude.q = np.array([math.cos(math.pi / 4), 0.0, 0.0, math.sin(math.pi / 4)],
                          dtype=np.float32)  # nose east
    position = VehicleLocalPosition()
    position.timestamp = stamp_us
    position.z = -float(spec.altitude)
    position.xy_valid = position.z_valid = position.v_xy_valid = True
    position.heading_good_for_control = True
    position.xy_global = True
    position.ref_lat = spec.origin.latitude
    position.ref_lon = spec.origin.longitude
    return status, attitude, position


def _depth_messages(probe):
    info = CameraInfo()
    info.header.stamp = probe.get_clock().now().to_msg()
    info.width, info.height = WIDTH, HEIGHT
    info.k = [FX, 0.0, (WIDTH - 1) / 2.0, 0.0, FX, (HEIGHT - 1) / 2.0, 0.0, 0.0, 1.0]
    image = Image()
    image.header.stamp = info.header.stamp
    image.width, image.height = WIDTH, HEIGHT
    image.encoding = '32FC1'
    image.step = WIDTH * 4
    image.data = array.array('B', np.full((HEIGHT, WIDTH), 20.0, dtype='<f4').tobytes())
    return info, image


def test_shadow_mode_drone_and_monitor(ros_context):
    spec = parse_mission(example_mission(), sequence=int(time.time() * 1000))
    drone = DroneNode(parameter_overrides=[Parameter('drone_id', value=DRONE_ID),
                                           Parameter('depth_stride', value=1)])
    monitor = MonitorNode()
    probe = rclpy.create_node('probe')
    codec = Codec(MessageTypes.load())
    publishers = {
        'status': probe.create_publisher(VehicleStatus, '/fmu/out/vehicle_status', px4_qos()),
        'attitude': probe.create_publisher(VehicleAttitude, '/fmu/out/vehicle_attitude',
                                           px4_qos()),
        'position': probe.create_publisher(VehicleLocalPosition,
                                           '/fmu/out/vehicle_local_position', px4_qos()),
        'info': probe.create_publisher(CameraInfo, '/camera/camera/depth/camera_info',
                                       sensor_qos()),
        'image': probe.create_publisher(Image, '/camera/camera/depth/image_rect_raw',
                                        sensor_qos()),
    }
    mission_pub = probe.create_publisher(type(codec.encode_mission(spec)), MISSION_TOPIC,
                                         latched_qos())
    states, setpoints, metrics = [], [], []
    probe.create_subscription(DroneState, STATUS_TOPIC, states.append, broadcast_qos(64))
    probe.create_subscription(TrajectorySetpoint, '/drone/shadow/trajectory_setpoint',
                              setpoints.append, reliable_qos())
    probe.create_subscription(SwarmMetrics, METRICS_TOPIC, metrics.append, reliable_qos())

    executor = SingleThreadedExecutor()
    for node in (drone, monitor, probe):
        executor.add_node(node)
    mission_pub.publish(codec.encode_mission(spec))
    deadline = time.monotonic() + 6.0
    next_frame = 0.0
    try:
        while time.monotonic() < deadline:
            if time.monotonic() >= next_frame:
                for key, msg in zip(('status', 'attitude', 'position'),
                                    _vehicle_messages(probe, spec)):
                    publishers[key].publish(msg)
                info, image = _depth_messages(probe)
                publishers['info'].publish(info)
                publishers['image'].publish(image)
                next_frame = time.monotonic() + 0.05
            executor.spin_once(timeout_sec=0.01)

        mine = [m for m in states if m.drone_id == DRONE_ID]
        assert mine, 'the drone never broadcast its state'
        assert mine[-1].mission_sequence == spec.sequence
        assert mine[-1].phase == int(Phase.TRANSIT)
        assert setpoints, 'shadow mode published no setpoints'
        assert all(math.isfinite(float(sp.yaw)) for sp in setpoints)
        # Shadow mode: not a single publisher toward PX4 exists.
        for topic in ('/fmu/in/trajectory_setpoint', '/fmu/in/offboard_control_mode',
                      '/fmu/in/vehicle_command'):
            assert probe.count_publishers(topic) == 0, topic
        assert metrics and metrics[-1].drones_alive >= 1
    finally:
        for node in (drone, monitor, probe):
            executor.remove_node(node)
            node.destroy_node()
