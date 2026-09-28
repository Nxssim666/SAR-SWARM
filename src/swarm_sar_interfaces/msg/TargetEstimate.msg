# A drone's estimate of the target's state under a constant-velocity model.
# Positions are in the mission frame (ENU metres around the mission origin) of the
# enclosing message's mission_sequence.

# Time at which state and covariance are valid.
builtin_interfaces/Time stamp

# Time of the newest detection (by any drone) folded into this estimate.
builtin_interfaces/Time last_measurement_stamp

# [x, y, vx, vy] in m and m/s.
float64[4] state

# Row-major 4x4 covariance of state, in m^2, m^2/s and m^2/s^2.
float64[16] covariance
