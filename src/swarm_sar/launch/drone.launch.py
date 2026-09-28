"""
Launch the drone node on a companion computer (one per drone).

Starts in shadow mode: nothing is sent to PX4 until control_enabled:=true.

Examples::

    ros2 launch swarm_sar drone.launch.py drone_id:=3
    ros2 launch swarm_sar drone.launch.py drone_id:=3 control_enabled:=true max_speed:=1.5
    ros2 launch swarm_sar drone.launch.py drone_id:=1 px4_namespace:=/px4_1 px4_system_id:=2
    ros2 launch swarm_sar drone.launch.py --show-args
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from swarm_sar.launch_args import drone_launch_arguments, resolve_drone_arguments


def generate_launch_description():
    """Declare every argument (generated from DroneConfig) and defer setup."""
    declared = [DeclareLaunchArgument(arg.name, default_value=arg.default,
                                      description=arg.description)
                for arg in drone_launch_arguments()]
    return LaunchDescription(declared + [OpaqueFunction(function=_launch_setup)])


def _launch_setup(context, *args, **kwargs):
    raw = {arg.name: LaunchConfiguration(arg.name).perform(context)
           for arg in drone_launch_arguments()}
    plan = resolve_drone_arguments(raw)  # raises ConfigError naming the offending argument
    return [Node(package='swarm_sar', executable='drone_node', name='drone',
                 namespace=plan.namespace, output='screen', parameters=[plan.parameters],
                 ros_arguments=['--log-level', plan.log_level])]
