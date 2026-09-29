#!/bin/bash
# Run a command in the built workspace (ROS 2 Jazzy + swarm_sar + sar_gcs_bridge).
set -e
source /opt/ros/jazzy/setup.bash
source /ws/install/setup.bash
exec "$@"
