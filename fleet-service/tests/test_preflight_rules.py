"""Preflight rules (M6, ADR 0035): the aircraft's failsafe parameters, row by row."""

import pytest

from fleet_service.domain.preflight import (
    PREFLIGHT_PARAMETERS,
    PreflightPolicy,
    Severity,
    blocking,
    check,
)

POLICY = PreflightPolicy(
    max_link_loss_s=30.0,
    max_altitude_relative_m=120.0,
    min_return_altitude_m=30.0,
    min_critical_battery_pct=7.0,
)
# A field-ready PX4: return on link loss after 10 s, return on a geofence breach, return then
# land on a low battery, 60 m return altitude, no mission landing requirement.
GOOD: dict[str, float | None] = {
    "NAV_DLL_ACT": 2,
    "COM_DL_LOSS_T": 10,
    "GF_ACTION": 3,
    "COM_LOW_BAT_ACT": 3,
    "BAT_CRIT_THR": 0.07,
    "BAT_EMERGEN_THR": 0.05,
    "RTL_RETURN_ALT": 60.0,
    "MIS_TKO_LAND_REQ": 0,
}


def test_a_field_ready_configuration_has_no_findings() -> None:
    assert set(GOOD) == set(PREFLIGHT_PARAMETERS)
    assert check(GOOD, POLICY) == []


@pytest.mark.parametrize(
    ("parameter", "value", "expected"),
    [
        # link loss (ADR 0002 S1: only the aircraft acts when the link is gone)
        ("NAV_DLL_ACT", 0, Severity.BLOCK),  # nothing happens
        ("NAV_DLL_ACT", 1, Severity.WARN),  # holds until the battery failsafe
        ("NAV_DLL_ACT", 3, None),  # land
        ("NAV_DLL_ACT", 5, Severity.BLOCK),  # terminate: the GCS never offers it (S6)
        ("NAV_DLL_ACT", 6, Severity.BLOCK),  # lockdown
        ("NAV_DLL_ACT", 4, Severity.BLOCK),  # not a PX4 value
        ("NAV_DLL_ACT", None, Severity.BLOCK),  # unread: never assumed favourable (S7)
        ("COM_DL_LOSS_T", 0, Severity.BLOCK),
        ("COM_DL_LOSS_T", 30, None),
        ("COM_DL_LOSS_T", 31, Severity.WARN),
        ("COM_DL_LOSS_T", None, Severity.BLOCK),
        # geofence
        ("GF_ACTION", 0, Severity.WARN),
        ("GF_ACTION", 1, Severity.WARN),
        ("GF_ACTION", 2, None),
        ("GF_ACTION", 5, None),
        ("GF_ACTION", 4, Severity.BLOCK),  # terminate
        ("GF_ACTION", 9, Severity.BLOCK),
        ("GF_ACTION", None, Severity.BLOCK),
        # battery
        ("COM_LOW_BAT_ACT", 0, Severity.WARN),
        ("COM_LOW_BAT_ACT", 2, None),
        ("COM_LOW_BAT_ACT", 1, Severity.BLOCK),  # not a PX4 value (any more)
        ("COM_LOW_BAT_ACT", None, Severity.BLOCK),
        ("BAT_CRIT_THR", 0.06, Severity.WARN),
        ("BAT_CRIT_THR", 0.07, None),
        ("BAT_CRIT_THR", None, Severity.BLOCK),
        ("BAT_EMERGEN_THR", 0.07, Severity.WARN),  # not below the critical level
        ("BAT_EMERGEN_THR", None, Severity.BLOCK),
        # return altitude
        ("RTL_RETURN_ALT", 121.0, Severity.BLOCK),  # climbs above the ceiling
        ("RTL_RETURN_ALT", 120.0, None),
        ("RTL_RETURN_ALT", 29.0, Severity.WARN),
        ("RTL_RETURN_ALT", None, Severity.BLOCK),
        # GCS missions (ADR 0028): not a failsafe, so never blocking
        ("MIS_TKO_LAND_REQ", 1, None),
        ("MIS_TKO_LAND_REQ", 4, None),
        ("MIS_TKO_LAND_REQ", 2, Severity.WARN),
        ("MIS_TKO_LAND_REQ", 3, Severity.WARN),
        ("MIS_TKO_LAND_REQ", None, Severity.WARN),
    ],
)
def test_preflight_row_by_row(
    parameter: str, value: float | None, expected: Severity | None
) -> None:
    findings = check(GOOD | {parameter: value}, POLICY)

    assert [f.severity for f in findings] == ([] if expected is None else [expected])
    assert all(f.parameter == parameter and f.value == value for f in findings)


def test_nothing_read_blocks_on_every_failsafe() -> None:
    findings = check({}, POLICY)

    assert {f.parameter for f in blocking(findings)} == set(PREFLIGHT_PARAMETERS) - {
        "MIS_TKO_LAND_REQ"
    }
    assert all("could not be read" in f.message for f in blocking(findings))
