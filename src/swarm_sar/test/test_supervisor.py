"""Tests for swarm_sar.core.supervisor: fault assessment and escalation to the autopilot."""

import dataclasses
import math

import pytest
from swarm_sar.core.config import DroneConfig
from swarm_sar.core.messages import HealthLevel
from swarm_sar.core.supervisor import (age, assess, ATTENTION_FAULTS, CRITICAL_FAULTS, Fault,
                                       FcRequest, lasting_faults, MOTION_BLOCKING_FAULTS,
                                       Supervisor, SupervisorInputs, TRANSIENT_FAULTS)

CFG = DroneConfig()
HEALTHY = SupervisorInputs(status_age=0.0, pose_age=0.0, pose_usable=True, attitude_age=0.0,
                           depth_age=0.0, depth_valid_fraction=0.5, global_reference=True,
                           outside_geofence=False, altitude_mismatch=False,
                           waypoint_unreachable=False, mission_rejected=False, overrun=False)


def inputs(**overrides):
    return dataclasses.replace(HEALTHY, **overrides)


def test_healthy_inputs_are_ok_and_allow_everything():
    report = assess(CFG, HEALTHY)
    assert report.level is HealthLevel.OK and report.faults == Fault.NONE
    assert report.can_control and report.can_move


@pytest.mark.parametrize('overrides, fault, level', [
    ({'status_age': CFG.fc_timeout + 0.1}, Fault.FC_LINK, HealthLevel.CRITICAL),
    ({'pose_age': math.inf}, Fault.POSE_STALE, HealthLevel.CRITICAL),
    ({'pose_usable': False}, Fault.POSE_INVALID, HealthLevel.CRITICAL),
    ({'attitude_age': 0.5}, Fault.ATTITUDE_STALE, HealthLevel.CRITICAL),
    ({'global_reference': False}, Fault.NO_GLOBAL_REFERENCE, HealthLevel.DEGRADED),
    ({'depth_age': 0.6}, Fault.DEPTH_STALE, HealthLevel.DEGRADED),
    ({'depth_valid_fraction': 0.01}, Fault.DEPTH_BLIND, HealthLevel.DEGRADED),
    ({'outside_geofence': True}, Fault.OUTSIDE_GEOFENCE, HealthLevel.DEGRADED),
    ({'altitude_mismatch': True}, Fault.ALTITUDE_MISMATCH, HealthLevel.DEGRADED),
    ({'waypoint_unreachable': True}, Fault.WAYPOINT_UNREACHABLE, HealthLevel.DEGRADED),
    ({'mission_rejected': True}, Fault.MISSION_REJECTED, HealthLevel.OK),
    ({'overrun': True}, Fault.CONTROL_OVERRUN, HealthLevel.OK),
    ({'radio_silent': True}, Fault.RADIO_SILENT, HealthLevel.DEGRADED),
])
def test_each_input_maps_to_its_fault_and_level(overrides, fault, level):
    report = assess(CFG, inputs(**overrides))
    assert report.faults == fault and report.level is level


def test_what_each_fault_class_allows():
    lost = assess(CFG, inputs(status_age=9.0))
    assert not lost.can_control and not lost.can_move
    blind = assess(CFG, inputs(depth_age=math.inf))
    assert blind.can_control and not blind.can_move
    stuck = assess(CFG, inputs(waypoint_unreachable=True))
    assert stuck.can_move  # the mission logic holds; nothing is wrong with the vehicle
    deaf = assess(CFG, inputs(radio_silent=True))
    assert deaf.can_control and not deaf.can_move  # other drones can no longer be avoided
    assert not (CRITICAL_FAULTS & MOTION_BLOCKING_FAULTS) and not (ATTENTION_FAULTS
                                                                   & MOTION_BLOCKING_FAULTS)
    assert not TRANSIENT_FAULTS & (CRITICAL_FAULTS | MOTION_BLOCKING_FAULTS | ATTENTION_FAULTS)


def test_lasting_faults_drop_only_the_transient_bits():
    assert lasting_faults(Fault.CONTROL_OVERRUN) == Fault.NONE
    both = int(Fault.CONTROL_OVERRUN | Fault.DEPTH_STALE | Fault.RADIO_SILENT)
    assert lasting_faults(both) == Fault.DEPTH_STALE | Fault.RADIO_SILENT  # plain int from wire


def test_stale_inputs_mask_the_finer_diagnosis():
    assert assess(CFG, inputs(pose_age=1.0, pose_usable=False)).faults == Fault.POSE_STALE
    assert assess(CFG, inputs(depth_age=1.0, depth_valid_fraction=0.0)).faults == \
        Fault.DEPTH_STALE
    assert assess(CFG, inputs(depth_valid_fraction=None)).faults == Fault.NONE


def test_nan_ages_count_as_stale():
    assert assess(CFG, inputs(pose_age=math.nan)).faults & Fault.POSE_STALE


def test_fault_bits_are_stable_wire_values():
    ordered = (Fault.FC_LINK, Fault.POSE_STALE, Fault.POSE_INVALID, Fault.ATTITUDE_STALE,
               Fault.NO_GLOBAL_REFERENCE, Fault.DEPTH_STALE, Fault.DEPTH_BLIND,
               Fault.OUTSIDE_GEOFENCE, Fault.ALTITUDE_MISMATCH, Fault.WAYPOINT_UNREACHABLE,
               Fault.MISSION_REJECTED, Fault.CONTROL_OVERRUN, Fault.RADIO_SILENT)
    assert [int(f) for f in ordered] == [1 << i for i in range(len(ordered))]
    assert set(ordered) == set(Fault.__members__.values()) - {Fault.NONE}  # none unpinned


def test_nothing_is_requested_while_not_engaged():
    s = Supervisor(CFG)
    assert s.update(0.0, inputs(pose_age=math.inf), engaged=False)[1] is None
    assert s.update(20.0, inputs(depth_age=math.inf), engaged=False)[1] is None


def test_critical_while_engaged_requests_hold_at_once():
    report, request = Supervisor(CFG).update(0.0, inputs(pose_age=math.inf), engaged=True)
    assert report.level is HealthLevel.CRITICAL and request is FcRequest.HOLD


def test_degraded_escalates_to_hold_after_the_configured_time():
    s = Supervisor(CFG)
    blind = inputs(depth_age=math.inf)
    assert s.update(0.0, blind, True)[1] is None
    assert s.update(CFG.degraded_escalation_time - 0.1, blind, True)[1] is None
    assert s.update(CFG.degraded_escalation_time, blind, True)[1] is FcRequest.HOLD


def test_recovery_restarts_the_escalation_timer():
    s = Supervisor(CFG)
    blind = inputs(depth_age=math.inf)
    s.update(0.0, blind, True)
    s.update(9.0, HEALTHY, True)
    assert s.update(12.0, blind, True)[1] is None
    assert s.update(12.0 + CFG.degraded_escalation_time, blind, True)[1] is FcRequest.HOLD
    s.reset()
    assert s.update(30.0, blind, True)[1] is None


def test_escalation_timer_follows_a_clock_step():
    s = Supervisor(CFG)
    deaf = inputs(radio_silent=True)
    s.update(100.0, deaf, True)
    s.shift_time(-60.0)  # the companion clock was stepped back by a minute
    assert s.update(40.0 + CFG.degraded_escalation_time - 0.1, deaf, True)[1] is None
    assert s.update(40.0 + CFG.degraded_escalation_time, deaf, True)[1] is FcRequest.HOLD


def test_attention_faults_never_escalate():
    s = Supervisor(CFG)
    stuck = inputs(waypoint_unreachable=True)
    for t in (0.0, 100.0, 1000.0):
        assert s.update(t, stuck, True)[1] is None


def test_age():
    assert age(5.0, None) == math.inf
    assert age(5.0, 4.0) == 1.0
    assert age(5.0, 6.0) == 0.0  # a stamp slightly ahead of the clock is fresh, not negative
