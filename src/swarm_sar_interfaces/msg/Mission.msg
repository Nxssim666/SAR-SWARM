# A mission for the whole swarm, published by the ground station (/swarm/v2/mission).
# A drone adopts a mission only if its sequence is higher than any it has seen, so
# re-deliveries are harmless and a stale mission can never replace a newer one.

# Milliseconds since the Unix epoch on the ground station's clock. Drones reject a
# sequence ahead of their own clock by more than max_clock_skew.
uint64 sequence
string mission_id

# Origin of the shared mission frame (WGS84, degrees).
float64 origin_latitude
float64 origin_longitude

# Flight altitude above each drone's home [m] and coverage grid cell size [m].
float32 altitude
float32 grid_resolution

# Transit waypoints, flown in order before the search (may be empty).
float64[] waypoint_latitudes
float64[] waypoint_longitudes

# Search area polygon (3 to 256 vertices, not self-intersecting).
float64[] area_latitudes
float64[] area_longitudes
