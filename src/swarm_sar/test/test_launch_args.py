"""Tests for swarm_sar.launch_args (the launch files' argument handling, minus ROS)."""

import pytest
from swarm_sar.core.config import config_fields, ConfigError, DroneConfig
from swarm_sar.launch_args import (drone_launch_arguments, monitor_launch_arguments,
                                   resolve_drone_arguments, resolve_monitor_arguments)


def drone_defaults():
    return {arg.name: arg.default for arg in drone_launch_arguments()}


def monitor_defaults():
    return {arg.name: arg.default for arg in monitor_launch_arguments()}


@pytest.mark.parametrize('arguments', [drone_launch_arguments, monitor_launch_arguments])
def test_every_config_field_is_an_argument_with_its_real_default(arguments):
    names = [arg.name for arg in arguments()]
    assert len(names) == len(set(names))
    by_name = {arg.name: arg for arg in arguments()}
    for spec in config_fields(DroneConfig):
        assert spec.name in by_name
        assert by_name[spec.name].description == spec.description


def test_drone_defaults_resolve_to_typed_parameters_in_shadow_mode():
    plan = resolve_drone_arguments(drone_defaults())
    assert plan.namespace == 'drone_0' and plan.log_level == 'info'
    p = plan.parameters
    assert p['control_enabled'] is False  # rollout safety: nothing reaches PX4 by default
    assert p['drone_id'] == 0 and p['px4_system_id'] == 1 and p['px4_namespace'] == ''
    assert isinstance(p['max_speed'], float) and isinstance(p['depth_stride'], int)
    assert p['camera_offset'] == [0.1, 0.0, 0.0] and p['use_sim_time'] is False
    assert p['max_speed'] == DroneConfig().max_speed


def test_integer_text_for_float_parameters_is_coerced():
    # Regression (v1): 'speed:=5' reached a double parameter as an int and crashed the node.
    raw = drone_defaults()
    raw.update({'max_speed': '2', 'drone_id': '12', 'control_enabled': 'True',
                'camera_rpy_deg': '0, -10, 0', 'px4_namespace': '/px4_3', 'namespace': 'uav3',
                'log_level': 'DEBUG'})
    plan = resolve_drone_arguments(raw)
    assert plan.parameters['max_speed'] == 2.0 and isinstance(plan.parameters['max_speed'],
                                                              float)
    assert plan.parameters['control_enabled'] is True
    assert plan.parameters['camera_rpy_deg'] == [0.0, -10.0, 0.0]
    assert plan.namespace == 'uav3' and plan.log_level == 'debug'


@pytest.mark.parametrize('name, value', [
    ('drone_id', '-1'), ('drone_id', 'many'), ('drone_id', str(2 ** 31)),
    ('px4_system_id', '0'), ('px4_system_id', '256'), ('px4_namespace', 'px4_1'),
    ('px4_namespace', '/px4_1/'), ('depth_topic', '  '), ('camera_info_topic', ''),
    ('log_level', 'loud'), ('control_enabled', 'sometimes'), ('max_speed', '-1'),
    ('camera_offset', '0, 0'), ('track_standoff', '50'),
])
def test_invalid_drone_arguments_fail_with_a_config_error(name, value):
    raw = drone_defaults()
    raw[name] = value
    with pytest.raises(ConfigError):
        resolve_drone_arguments(raw)


def test_monitor_arguments():
    plan = resolve_monitor_arguments(monitor_defaults())
    assert plan.namespace == '' and plan.parameters['metrics_csv'] == ''
    assert plan.parameters['publish_period'] == 0.5
    raw = monitor_defaults()
    raw['metrics_csv'] = ' /tmp/run.csv '
    assert resolve_monitor_arguments(raw).parameters['metrics_csv'] == '/tmp/run.csv'
    for name, value in (('publish_period', '0'), ('report_period', 'x'),
                        ('min_separation', '-1')):
        bad = monitor_defaults()
        bad[name] = value
        with pytest.raises(ConfigError):
            resolve_monitor_arguments(bad)


def test_unknown_launch_arguments_are_ignored():
    raw = drone_defaults()
    raw['not_an_argument'] = 'x'
    assert 'not_an_argument' not in resolve_drone_arguments(raw).parameters
