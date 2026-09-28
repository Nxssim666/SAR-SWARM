# Mission KPIs published by the ground-station monitor. NaN marks "not available".

std_msgs/Header header

# Seconds since the first drone was seen working the mission.
float64 mission_time

uint32 drones_alive

# Fraction of the area ever inside a detector footprint, and within revisit_period.
float64 explored_fraction
float64 fresh_fraction

uint32 num_tracking
uint32 num_holding
uint32 num_degraded
bool target_detected

# Seconds from mission start to the first estimate anywhere in the swarm.
float64 time_to_first_detection

# Distance from the best estimate to ground truth [m] (simulation only).
float64 tracking_error

# Smallest distance between two live drones, and to an obstacle any drone reports [m].
float64 min_separation
float64 min_obstacle_distance
