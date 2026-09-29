"""
The swarm bridge's wire format against the station's (ADR 0024), both ways.

``src/sar_gcs_bridge/sar_gcs_bridge/wire.py`` (the bridge, standard library only) and
``fleet_service.drivers.swarm_wire`` (the station, pydantic) describe the same NATS
messages; this test fails as soon as they disagree.
"""

import json

import pytest
from sar_gcs_bridge import wire

from fleet_service.domain.enums import SwarmFault, SwarmHealth, SwarmPhase
from fleet_service.drivers.swarm_wire import (
    SUBJECT_PREFIX,
    BridgeHeartbeat,
    BridgeReply,
    SwarmCommandKind,
    SwarmCommandRequest,
    SwarmMissionRequest,
    SwarmStatus,
    WirePoint,
    subject,
)


def test_the_enumerations_and_subjects_agree() -> None:
    assert tuple(SwarmPhase) == wire.PHASES  # index = DroneState.PHASE_*
    assert tuple(SwarmHealth) == wire.HEALTH
    assert [name for _, name in wire.FAULTS] == list(SwarmFault)  # bit order
    assert list(wire.COMMANDS) == list(SwarmCommandKind)
    assert wire.SUBJECT_PREFIX == SUBJECT_PREFIX
    assert wire.subject("blue", "status") == subject("blue", "status")


@pytest.mark.parametrize(
    "fields",
    [
        {
            "position": (47.3977, 8.5456),
            "heading_deg": 271.5,
            "nearest_obstacle": 3.5,
            "sighting": (47.3980, 8.5460, 4.0, 1_790_000_000.0),
        },
        {"position": None, "heading_deg": None, "nearest_obstacle": float("inf"), "sighting": None},
    ],
)
def test_the_bridge_s_status_is_a_valid_station_status(fields: dict[str, object]) -> None:
    message = wire.status(
        drone_id=3,
        stamp=1_790_000_000.0,
        received_at=1_790_000_000.1,
        phase=4,
        health=1,
        faults=(1 << 5) | (1 << 10),
        mission_sequence=12,
        command_sequence=2**40,
        velocity_north=4.0,
        velocity_east=3.0,
        **fields,  # type: ignore[arg-type]
    )

    status = SwarmStatus.model_validate_json(wire.encode(message))

    assert status.phase is SwarmPhase.HOLD
    assert status.health is SwarmHealth.DEGRADED
    assert status.faults == [SwarmFault.DEPTH_STALE, SwarmFault.MISSION_REJECTED]
    assert status.groundspeed_mps == 5.0


def test_the_bridge_s_replies_and_heartbeat_are_valid() -> None:
    assert BridgeReply.model_validate_json(wire.encode(wire.reply(sequence=5))).sequence == 5
    assert BridgeReply.model_validate_json(wire.encode(wire.reply(error="no"))).error == "no"
    heartbeat = wire.heartbeat("default", 1_790_000_000.0, [2, 1])
    assert BridgeHeartbeat.model_validate_json(wire.encode(heartbeat)).drones_heard == [1, 2]


def test_the_station_s_requests_parse_in_the_bridge() -> None:
    command = SwarmCommandRequest(kind=SwarmCommandKind.RETURN_TO_LAUNCH, drone_ids=[4, 5])
    point = WirePoint(latitude=47.3977, longitude=8.5456)
    mission = SwarmMissionRequest(
        mission_id="01a0ef5c-70a0-7a29-90ca-1503ffc02b4a",
        origin=point,
        altitude_relative_m=30.0,
        grid_resolution_m=5.0,
        waypoints=[point],
        area=[point, WirePoint(latitude=47.40, longitude=8.55), point],
    )

    assert wire.parse_command(command.model_dump_json().encode()) == ("return_to_launch", [4, 5])
    parsed = wire.parse_mission(mission.model_dump_json().encode())
    assert parsed["origin"] == (47.3977, 8.5456)
    assert parsed["area"][1] == (47.40, 8.55)
    assert parsed["altitude_relative_m"] == 30.0


def test_a_request_with_a_field_the_bridge_does_not_know_is_refused() -> None:
    body = json.dumps({"kind": "hold", "drone_ids": [1], "priority": "high"}).encode()
    with pytest.raises(wire.WireError):
        wire.parse_command(body)
