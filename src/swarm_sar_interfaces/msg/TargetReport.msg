# One detection of the search target by a drone's onboard detector, georeferenced by
# the detector (topic target_reports in the drone's namespace).

builtin_interfaces/Time stamp
float64 latitude
float64 longitude

# 1-sigma horizontal position uncertainty [m] and detector score [0, 1].
float32 position_std
float32 confidence
