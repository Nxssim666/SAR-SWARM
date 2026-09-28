# An operator command from the ground station (/swarm/v2/command). Each drone applies
# a sequence number at most once and reports it back in DroneState.command_sequence.

uint8 HOLD=1
uint8 RESUME=2
uint8 RETURN_TO_LAUNCH=3
uint8 LAND=4

# Milliseconds since the Unix epoch on the ground station's clock (strictly increasing).
uint64 sequence
builtin_interfaces/Time stamp
uint8 command

# Addressed drones; empty means every drone.
uint32[] drone_ids
