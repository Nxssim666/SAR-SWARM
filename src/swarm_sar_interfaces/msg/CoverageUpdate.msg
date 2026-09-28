# Cells a drone observed, as flat indices into the coverage grid of its mission
# (/swarm/v2/coverage). Receivers on the same mission merge them with an element-wise
# maximum, which is idempotent and order-independent.

builtin_interfaces/Time stamp
uint32 drone_id
uint64 mission_sequence

# true: every cell the sender ever observed (periodic snapshot that repairs lost updates).
bool full

# Flat cell index (ix * ny + iy) and the time the cell was last observed [s, ROS time].
uint32[] cells
float64[] last_seen
