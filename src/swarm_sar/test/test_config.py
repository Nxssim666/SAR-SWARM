"""Tests for swarm_sar.core.config."""

import dataclasses

import pytest
from swarm_sar.core.config import (braking_limited_speed, config_fields, config_from_mapping,
                                   config_from_text, config_to_parameters, ConfigError,
                                   DroneConfig, format_value, parse_text, SimConfig)

ALL_CONFIGS = (DroneConfig, SimConfig)


@pytest.mark.parametrize('cls', ALL_CONFIGS)
def test_defaults_are_valid_and_quiet(cls):
    assert cls().warnings() == []


@pytest.mark.parametrize('overrides, fragment', [
    ({'control_period': 0.5}, 'control_period'),
    ({'max_speed': 0.0}, 'max_speed'),
    ({'max_speed': True}, 'max_speed'),
    ({'min_altitude': 70.0}, 'min_altitude'),
    ({'reaction_time': 0.05}, 'reaction_time'),
    ({'pose_timeout': 0.1}, 'pose_timeout'),
    ({'depth_timeout': 0.1}, 'depth_timeout'),
    ({'camera_offset': (0.1, 0.0, 1.5)}, 'band'),
    ({'camera_rpy_deg': (0.0, 95.0, 0.0)}, 'pitch'),
    ({'self_clear_radius': 0.5}, 'self_clear_radius'),
    ({'map_resolution': 0.5}, 'map_resolution'),
    ({'map_size': 20.0}, 'map_size'),
    ({'map_resolution': 0.01, 'obstacle_clearance': 0.8}, 'cells'),
    ({'track_standoff': 12.0}, 'track_standoff'),
    ({'recruit_radius': 4.0}, 'recruit_radius'),
    ({'arrival_radius': 12.0}, 'arrival_radius'),
    ({'peer_timeout': 0.3}, 'peer_timeout'),
    ({'coverage_recent_window': 0.5}, 'coverage_recent_window'),
    ({'depth_stride': 0}, 'depth_stride'),
    ({'min_detection_confidence': 1.5}, 'min_detection_confidence'),
    ({'depth_trusted_range': float('nan')}, 'depth_trusted_range'),
])
def test_invalid_drone_values_are_rejected_with_the_field_name(overrides, fragment):
    with pytest.raises(ConfigError, match=fragment):
        DroneConfig(**overrides)


def test_numbers_are_coerced_losslessly():
    config = DroneConfig(max_speed=2, num_trackers=3.0, camera_offset=[0, 0, 0])
    assert isinstance(config.max_speed, float) and config.max_speed == 2.0
    assert isinstance(config.num_trackers, int) and config.num_trackers == 3
    assert config.camera_offset == (0.0, 0.0, 0.0)
    with pytest.raises(ConfigError):
        DroneConfig(num_trackers=2.5)


def test_config_is_immutable():
    with pytest.raises(dataclasses.FrozenInstanceError):
        DroneConfig().max_speed = 1.0


def test_warnings_flag_questionable_but_legal_settings():
    notes = DroneConfig(max_speed=10.0, target_max_speed=12.0, self_clear_radius=4.0).warnings()
    assert any('effective limit' in n for n in notes)
    assert any('target_max_speed' in n for n in notes)
    assert any('self_clear_radius' in n for n in notes)


def test_braking_limited_speed_matches_the_kinematics():
    # v * tau + v^2 / (2 a) = d  with a = 2, tau = 0.5, d = 2.25 + 1.5 = 3.75 gives v = 3.
    assert braking_limited_speed(3.75, 2.0, 0.5) == pytest.approx(3.0)
    assert braking_limited_speed(-1.0, 2.0, 0.5) == 0.0


def test_sim_config_validation():
    with pytest.raises(ConfigError, match='tree_radius'):
        SimConfig(tree_radius=(0.5, 0.2))
    with pytest.raises(ConfigError, match='grid_resolution'):
        SimConfig(area_size=10.0, grid_resolution=8.0)


@pytest.mark.parametrize('cls', ALL_CONFIGS)
def test_every_default_round_trips_through_text(cls):
    defaults = cls()
    text = {spec.name: format_value(spec.default) for spec in config_fields(cls)}
    parsed = config_from_text(cls, text)
    for spec in config_fields(cls):
        assert getattr(parsed, spec.name) == getattr(defaults, spec.name), spec.name


@pytest.mark.parametrize('text', ['__import__("os")', '[1, 2, x]', '', 'nan', '1e999'])
def test_text_parsing_rejects_garbage_without_evaluating_it(text):
    with pytest.raises(ConfigError):
        config_from_text(DroneConfig, {'max_speed': text})


def test_parse_text_bool_int_and_tuples():
    assert parse_text(bool, ' YES ', 'x') is True
    assert parse_text(bool, 'off', 'x') is False
    assert parse_text(int, '12.0', 'x') == 12
    assert config_from_text(DroneConfig, {'camera_rpy_deg': '0, -15, 0'}).camera_rpy_deg == \
        (0.0, -15.0, 0.0)
    with pytest.raises(ConfigError):
        parse_text(bool, 'maybe', 'x')
    with pytest.raises(ConfigError):
        parse_text(int, '12.5', 'x')
    with pytest.raises(ConfigError, match='needs 3'):
        config_from_text(DroneConfig, {'camera_offset': '1, 2'})


def test_mapping_ignores_unknown_keys_and_parameters_are_plain():
    config = config_from_mapping(DroneConfig, {'max_speed': 2.5, 'not_a_field': 1})
    assert config.max_speed == 2.5
    params = config_to_parameters(config)
    assert params['camera_offset'] == [0.1, 0.0, 0.0]
    assert all(isinstance(v, (bool, int, float, str, list)) for v in params.values())


def test_field_descriptions_include_units():
    specs = {spec.name: spec for spec in config_fields(DroneConfig)}
    assert specs['max_speed'].description.endswith('[m/s]')
    assert specs['min_valid_depth_fraction'].description == \
        specs['min_valid_depth_fraction'].help_text
