"""
Launch the ground-station monitor (metrics, alerts, RViz2 markers).

Examples::

    ros2 launch swarm_sar monitor.launch.py
    ros2 launch swarm_sar monitor.launch.py metrics_csv:=/tmp/run.csv
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from swarm_sar.launch_args import monitor_launch_arguments, resolve_monitor_arguments


def generate_launch_description():
    """Declare every argument and defer setup."""
    declared = [DeclareLaunchArgument(arg.name, default_value=arg.default,
                                      description=arg.description)
                for arg in monitor_launch_arguments()]
    return LaunchDescription(declared + [OpaqueFunction(function=_launch_setup)])


def _launch_setup(context, *args, **kwargs):
    raw = {arg.name: LaunchConfiguration(arg.name).perform(context)
           for arg in monitor_launch_arguments()}
    plan = resolve_monitor_arguments(raw)
    return [Node(package='swarm_sar', executable='monitor_node', name='monitor',
                 output='screen', parameters=[plan.parameters],
                 ros_arguments=['--log-level', plan.log_level])]
