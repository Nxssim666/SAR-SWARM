# The swarm side for the swarm CI workflow (ADR 0026): ROS 2 Jazzy with the onboard
# packages (unchanged), the ground bridge, and the swarm simulation.
#
#   docker build -f sim/swarm/Dockerfile -t sar-swarm .      # from the repository root
FROM ros:jazzy-ros-base@sha256:c3706ef0a0aa45413c07803cf433602f543b22e45b4855f6fca955c2d8ecc4e8

SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3-colcon-common-extensions python3-numpy python3-pip python3-pytest \
        ros-jazzy-ament-flake8 ros-jazzy-ament-pep257 \
    && rm -rf /var/lib/apt/lists/*
# nats-py has no Debian or rosdep package; pinned like the fleet service's lock file.
RUN pip3 install --no-cache-dir --break-system-packages "nats-py==2.16.0"

WORKDIR /ws
COPY src/swarm_sar_interfaces src/swarm_sar_interfaces
COPY src/swarm_sar src/swarm_sar
COPY src/sar_gcs_bridge src/sar_gcs_bridge
RUN source /opt/ros/jazzy/setup.bash \
    && colcon build --packages-select swarm_sar_interfaces swarm_sar sar_gcs_bridge \
        --event-handlers console_direct-
COPY sim/swarm/swarm_sim.py sim/swarm/entrypoint.sh /ws/sim/

ENTRYPOINT ["/ws/sim/entrypoint.sh"]
CMD ["ros2", "run", "sar_gcs_bridge", "bridge_node"]
