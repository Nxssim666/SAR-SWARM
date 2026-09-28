# Periodic broadcast of one drone on the shared swarm channel (/swarm/v2/status).
#
# The position is WGS84 because every drone has its own local frame. goal and
# target_estimate are in the mission frame of mission_sequence (ENU metres around the
# mission origin) and are only meaningful to drones on the same mission.

uint8 PROTOCOL_VERSION=2

uint8 PHASE_STANDBY=0
uint8 PHASE_TRANSIT=1
uint8 PHASE_SEARCH=2
uint8 PHASE_TRACK=3
uint8 PHASE_HOLD=4

uint8 HEALTH_OK=0
uint8 HEALTH_DEGRADED=1
uint8 HEALTH_CRITICAL=2

# Bits of the faults field.
uint32 FAULT_FC_LINK=1
uint32 FAULT_POSE_STALE=2
uint32 FAULT_POSE_INVALID=4
uint32 FAULT_ATTITUDE_STALE=8
uint32 FAULT_NO_GLOBAL_REFERENCE=16
uint32 FAULT_DEPTH_STALE=32
uint32 FAULT_DEPTH_BLIND=64
uint32 FAULT_OUTSIDE_GEOFENCE=128
uint32 FAULT_ALTITUDE_MISMATCH=256
uint32 FAULT_WAYPOINT_UNREACHABLE=512
uint32 FAULT_MISSION_REJECTED=1024
uint32 FAULT_CONTROL_OVERRUN=2048
uint32 FAULT_RADIO_SILENT=4096

uint8 protocol_version
builtin_interfaces/Time stamp
uint32 drone_id
uint8 phase
uint8 health
uint32 faults

# Sequence of the active mission (0 = none) and of the last operator command processed.
uint64 mission_sequence
uint64 command_sequence

bool has_position
float64 latitude
float64 longitude

# Ground velocity [m/s] and heading [rad, counter-clockwise from east].
float32 velocity_east
float32 velocity_north
float32 heading

bool has_goal
float64 goal_x
float64 goal_y

bool has_target_estimate
TargetEstimate target_estimate

# Distance to the nearest obstacle the depth camera currently knows of [m]; +inf if none.
float32 nearest_obstacle
