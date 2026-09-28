"""
Topic names and frames: the single source of truth for the ROS interface.

Swarm topics carry the protocol version in their namespace. A v1 node and a
v2 node therefore never exchange messages they would misinterpret; they
simply do not see each other, which is why mixed-version fleets must not fly
together (the ground station's acknowledgement check makes that visible).
"""

SWARM_NAMESPACE = '/swarm/v2'
STATUS_TOPIC = SWARM_NAMESPACE + '/status'
COVERAGE_TOPIC = SWARM_NAMESPACE + '/coverage'
MISSION_TOPIC = SWARM_NAMESPACE + '/mission'
COMMAND_TOPIC = SWARM_NAMESPACE + '/command'

# Relative to the drone node's namespace, so each companion's detector feeds its own drone.
TARGET_REPORT_TOPIC = 'target_reports'
SHADOW_SETPOINT_TOPIC = '~/shadow/trajectory_setpoint'

# PX4 uXRCE-DDS topics, relative to the configured PX4 namespace (PX4 v1.14/v1.15 names).
PX4_LOCAL_POSITION = 'fmu/out/vehicle_local_position'
PX4_ATTITUDE = 'fmu/out/vehicle_attitude'
PX4_STATUS = 'fmu/out/vehicle_status'
PX4_OFFBOARD_MODE = 'fmu/in/offboard_control_mode'
PX4_TRAJECTORY_SETPOINT = 'fmu/in/trajectory_setpoint'
PX4_VEHICLE_COMMAND = 'fmu/in/vehicle_command'

# Ground-station monitor outputs (RViz2 fixed frame: MISSION_FRAME).
MISSION_FRAME = 'mission'
MARKERS_TOPIC = '/swarm_sar/markers'
COVERAGE_GRID_TOPIC = '/swarm_sar/coverage'
METRICS_TOPIC = '/swarm_sar/metrics'


def px4_topic(namespace: str, name: str) -> str:
    """Join a PX4 namespace (``''`` or ``/px4_1``) and a relative PX4 topic name."""
    if namespace and (not namespace.startswith('/') or namespace.endswith('/')):
        raise ValueError(f"px4 namespace must be '' or '/name' without a trailing slash, "
                         f'got {namespace!r}')
    return f'{namespace}/{name}' if namespace else f'/{name}'
