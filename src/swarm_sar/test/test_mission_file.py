"""Tests for mission files and the ROS-free parts of the ground-station CLI."""

import json

import pytest
from swarm_sar.core.config import DroneConfig
from swarm_sar.core.controller import DroneController
from swarm_sar.core.geodesy import GeoPoint
from swarm_sar.core.messages import (CommandKind, DroneStatus, HealthLevel, MissionSpec, Phase,
                                     Receipt, SwarmCommand)
from swarm_sar.mission_file import (EXAMPLE, example_mission, MAX_FILE_BYTES, MissionFileError,
                                    parse_mission)
from swarm_sar.ros import mission_cli


def edited(**changes):
    data = json.loads(example_mission())
    data.update(changes)
    return json.dumps(data)


def test_the_example_is_a_valid_flyable_mission():
    spec = parse_mission(example_mission(), sequence=7)
    assert spec.sequence == 7 and spec.mission_id == EXAMPLE['mission_id']
    assert len(spec.area) == 4 and len(spec.waypoints) == 2
    assert spec.origin == GeoPoint(47.397742, 8.545594)


def test_waypoints_are_optional():
    data = json.loads(example_mission())
    del data['waypoints']
    assert parse_mission(json.dumps(data), 1).waypoints == ()


@pytest.mark.parametrize('text, fragment', [
    ('not json', 'JSON'),
    ('[1, 2]', 'object'),
    (json.dumps({k: v for k, v in EXAMPLE.items() if k != 'area'}), 'missing'),
    (edited(altitdue=4.0), 'unknown'),                                   # a typo
    (edited(altitude='4'), 'number'),
    (edited(altitude=True), 'number'),
    (edited(mission_id=5), 'string'),
    (edited(origin=[47.39, 8.54]), 'latitude'),                          # bare pair
    (edited(origin={'lat': 47.39, 'lon': 8.54}), 'latitude'),
    (edited(area=[EXAMPLE['area'][0], EXAMPLE['area'][2], EXAMPLE['area'][1],
                  EXAMPLE['area'][3]]), 'intersect'),                   # bow tie
    (edited(area=EXAMPLE['area'][:2]), '3'),
    (edited(origin={'latitude': 95.0, 'longitude': 8.5}), 'latitude'),
    (edited(grid_resolution=0), 'grid_resolution'),
])
def test_bad_files_are_rejected_with_a_reason(text, fragment):
    with pytest.raises(MissionFileError, match=fragment):
        parse_mission(text, 1)


def test_oversized_files_are_rejected_before_parsing():
    with pytest.raises(MissionFileError, match='larger'):
        parse_mission(' ' * (MAX_FILE_BYTES + 1), 1)


def test_parse_drone_ids():
    assert mission_cli.parse_drone_ids('1, 2,5,,') == frozenset({1, 2, 5})
    assert mission_cli.parse_drone_ids('') == frozenset()
    for bad in ('a', '-1', '1.5'):
        with pytest.raises(ValueError):
            mission_cli.parse_drone_ids(bad)


def online(**sequences):
    return {int(k[1:]): DroneStatus(int(k[1:]), 0.0, None, (0.0, 0.0), 0.0, Phase.SEARCH,
                                    HealthLevel.OK, 0, mission, command)
            for k, (mission, command) in sequences.items()}


def test_acknowledgement_helpers():
    drones = online(d1=(5, 10), d2=(5, 9), d3=(4, 12))
    everyone = SwarmCommand(10, CommandKind.HOLD, 0.0)
    assert mission_cli.unacknowledged(everyone, drones) == [2]
    some = SwarmCommand(11, CommandKind.RESUME, 0.0, frozenset({1, 3}))
    assert mission_cli.unacknowledged(some, drones) == [1]
    spec = MissionSpec(5, 'm', GeoPoint(0.0, 0.0), 4.0, 5.0, (), (GeoPoint(0.0, 0.0),) * 3)
    assert mission_cli.mission_holdouts(spec, drones) == [3]


def test_sequence_numbers_are_clock_milliseconds():
    assert mission_cli.sequence_at(1_700_000_000.0) == 1_700_000_000_000
    assert mission_cli.sequence_at(0.5) < mission_cli.sequence_at(0.502)
    with pytest.raises(ValueError, match='clock'):
        mission_cli.sequence_at(0.0)  # simulated time before the first /clock message


@pytest.mark.parametrize('clock', [37.5, 1_758_000_000.25])  # /clock (SITL), wall time
def test_what_the_cli_sends_is_accepted_by_a_drone_on_the_same_clock(clock):
    # Regression (v2): sequence numbers were wall-clock milliseconds even when the drones
    # ran on /clock (PX4 SITL with use_sim_time), so every mission and command was refused.
    drone = DroneController(1, DroneConfig())
    spec = mission_cli.mission_at(parse_mission(example_mission(), 1), clock)
    assert drone.on_mission(spec, clock + 0.05) is Receipt.ACCEPTED
    command = mission_cli.command_at(CommandKind.HOLD, frozenset(), clock + 0.1)
    assert drone.on_command(command, clock + 0.15) is Receipt.ACCEPTED


def test_cli_passes_the_clock_choice_through(tmp_path, monkeypatch):
    calls = []

    def serve(spec, use_sim_time):
        calls.append(('send', spec.mission_id, use_sim_time))
        return 0

    def command(kind, targets, timeout, use_sim_time):
        calls.append((kind, targets, use_sim_time))
        return 0

    monkeypatch.setattr(mission_cli, '_serve_mission', serve)
    monkeypatch.setattr(mission_cli, '_send_command', command)
    path = tmp_path / 'mission.json'
    path.write_text(example_mission(), encoding='utf-8')
    assert mission_cli.main(['send', str(path), '--use-sim-time']) == 0
    assert mission_cli.main(['land', '--drones', '4']) == 0
    assert calls == [('send', EXAMPLE['mission_id'], True),
                     (CommandKind.LAND, frozenset({4}), False)]


def test_cli_without_ros(tmp_path, capsys):
    assert mission_cli.main(['example']) == 0
    assert json.loads(capsys.readouterr().out)['mission_id'] == EXAMPLE['mission_id']
    assert mission_cli.main(['send', str(tmp_path / 'missing.json')]) == 2
    broken = tmp_path / 'broken.json'
    broken.write_text(edited(altitdue=3.0), encoding='utf-8')
    assert mission_cli.main(['send', str(broken)]) == 2
    assert mission_cli.main(['hold', '--drones', 'x']) == 2
    assert 'error:' in capsys.readouterr().err
