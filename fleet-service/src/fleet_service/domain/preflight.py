"""
Preflight safety checks (M6, ADR 0035): an aircraft's own failsafes, read from its
autopilot parameters, compared with the station's policy before it is armed or takes off.

The ground station is not the aircraft's safety net: when the radio link fails, only the
aircraft's failsafes act (ADR 0002, S1). An aircraft that would do nothing on link loss,
or would terminate its flight, must not be launched by accident. Pure functions over the
PX4 parameter values, tested row by row.

Each finding either **blocks** (arm and takeoff are rejected; a supervisor may override,
confirmed and audited) or **warns** (shown in the confirmation). A safety parameter that
could not be read blocks: unknown is never assumed favourable (ADR 0002, S7).
"""

from dataclasses import dataclass
from enum import StrEnum


class ParameterType(StrEnum):
    """How PX4 stores a parameter."""

    INT = "int"
    FLOAT = "float"


# The parameters read before flight, with their PX4 types.
PREFLIGHT_PARAMETERS: dict[str, ParameterType] = {
    "NAV_DLL_ACT": ParameterType.INT,  # action on ground-station link loss
    "COM_DL_LOSS_T": ParameterType.INT,  # seconds without the link before it acts
    "GF_ACTION": ParameterType.INT,  # action on a geofence breach
    "COM_LOW_BAT_ACT": ParameterType.INT,  # action at the battery thresholds
    "BAT_CRIT_THR": ParameterType.FLOAT,  # critical battery level, fraction
    "BAT_EMERGEN_THR": ParameterType.FLOAT,  # emergency battery level, fraction
    "RTL_RETURN_ALT": ParameterType.FLOAT,  # return altitude above home, metres
    "MIS_TKO_LAND_REQ": ParameterType.INT,  # mission takeoff/landing item requirement
}

# PX4 enum values (v1.14-v1.18).
_DLL_ACTIONS = {0: "disabled", 1: "hold", 2: "return", 3: "land", 5: "terminate", 6: "lockdown"}
_GF_ACTIONS = {0: "none", 1: "warning", 2: "hold", 3: "return", 4: "terminate", 5: "land"}
_BAT_ACTIONS = {0: "warning only", 2: "land", 3: "return, then land"}
# MIS_TKO_LAND_REQ: 2 (landing), 3 (takeoff and landing) and 5 (landing, as a VTOL)
# require a landing item; GCS-planned routes end with a return (ADR 0028).
_NEEDS_LANDING_ITEM = {2, 3, 5}


class Severity(StrEnum):
    """What a finding does to arm and takeoff."""

    BLOCK = "block"
    WARN = "warn"


@dataclass(frozen=True)
class PreflightPolicy:
    """The station's expectations (settings)."""

    max_link_loss_s: float  # the aircraft must react to link loss within this
    max_altitude_relative_m: float  # the regulatory ceiling above home
    min_return_altitude_m: float  # below this a return may meet obstacles
    min_critical_battery_pct: float  # the aircraft must act at or above this level


@dataclass(frozen=True)
class Finding:
    """One problem with an aircraft's failsafe configuration."""

    parameter: str
    value: float | None
    severity: Severity
    message: str


def check(values: dict[str, float | None], policy: PreflightPolicy) -> list[Finding]:
    """Compare the parameters read from an aircraft with ``policy``.

    ``values`` maps each name of ``PREFLIGHT_PARAMETERS`` to its value, or None when it
    could not be read (a missing name counts as unread).
    """
    findings: list[Finding] = []

    def add(name: str, severity: Severity, message: str) -> None:
        findings.append(Finding(name, values.get(name), severity, message))

    def unknown(name: str, what: str) -> bool:
        if values.get(name) is None:
            add(name, Severity.BLOCK, f"{what} is unknown ({name} could not be read).")
            return True
        return False

    if not unknown("NAV_DLL_ACT", "The action on link loss"):
        action = int(values["NAV_DLL_ACT"] or 0)
        name = _DLL_ACTIONS.get(action)
        if action == 0:
            add("NAV_DLL_ACT", Severity.BLOCK, "Nothing happens when the link is lost.")
        elif action in (5, 6):
            add("NAV_DLL_ACT", Severity.BLOCK, f"The aircraft would {name} on link loss.")
        elif name is None:
            add("NAV_DLL_ACT", Severity.BLOCK, f"Unknown link-loss action {action}.")
        elif action == 1:
            add(
                "NAV_DLL_ACT",
                Severity.WARN,
                "The aircraft holds on link loss until its battery failsafe acts.",
            )
    if not unknown("COM_DL_LOSS_T", "The link-loss delay"):
        delay = float(values["COM_DL_LOSS_T"] or 0.0)
        if delay <= 0:
            add("COM_DL_LOSS_T", Severity.BLOCK, "The link-loss delay is not set.")
        elif delay > policy.max_link_loss_s:
            add(
                "COM_DL_LOSS_T",
                Severity.WARN,
                f"The aircraft reacts to link loss after {delay:.0f} s "
                f"(policy: {policy.max_link_loss_s:.0f} s).",
            )
    if not unknown("GF_ACTION", "The geofence action"):
        action = int(values["GF_ACTION"] or 0)
        name = _GF_ACTIONS.get(action)
        if action == 4:
            add("GF_ACTION", Severity.BLOCK, "The aircraft would terminate on a geofence breach.")
        elif name is None:
            add("GF_ACTION", Severity.BLOCK, f"Unknown geofence action {action}.")
        elif action in (0, 1):
            add(
                "GF_ACTION",
                Severity.WARN,
                f"A geofence breach does not stop the aircraft ({name}).",
            )
    if not unknown("COM_LOW_BAT_ACT", "The low-battery action"):
        action = int(values["COM_LOW_BAT_ACT"] or 0)
        if action not in _BAT_ACTIONS:
            add("COM_LOW_BAT_ACT", Severity.BLOCK, f"Unknown low-battery action {action}.")
        elif action == 0:
            add(
                "COM_LOW_BAT_ACT",
                Severity.WARN,
                "A critical battery only warns; the aircraft does not return or land.",
            )
    if not unknown("BAT_CRIT_THR", "The critical battery level"):
        critical = 100.0 * float(values["BAT_CRIT_THR"] or 0.0)
        if critical < policy.min_critical_battery_pct:
            add(
                "BAT_CRIT_THR",
                Severity.WARN,
                f"The aircraft acts at {critical:.0f} % battery "
                f"(policy: at least {policy.min_critical_battery_pct:.0f} %).",
            )
    if not unknown("BAT_EMERGEN_THR", "The emergency battery level"):
        emergency = float(values["BAT_EMERGEN_THR"] or 0.0)
        critical_fraction = values.get("BAT_CRIT_THR")
        if critical_fraction is not None and emergency >= critical_fraction:
            add(
                "BAT_EMERGEN_THR",
                Severity.WARN,
                "The emergency battery level is not below the critical one.",
            )
    if not unknown("RTL_RETURN_ALT", "The return altitude"):
        altitude = float(values["RTL_RETURN_ALT"] or 0.0)
        if altitude > policy.max_altitude_relative_m:
            add(
                "RTL_RETURN_ALT",
                Severity.BLOCK,
                f"A return climbs to {altitude:.0f} m, above the "
                f"{policy.max_altitude_relative_m:.0f} m ceiling.",
            )
        elif altitude < policy.min_return_altitude_m:
            add(
                "RTL_RETURN_ALT",
                Severity.WARN,
                f"A return flies at {altitude:.0f} m, below the "
                f"{policy.min_return_altitude_m:.0f} m obstacle clearance.",
            )
    requirement = values.get("MIS_TKO_LAND_REQ")
    if requirement is None:
        add(
            "MIS_TKO_LAND_REQ",
            Severity.WARN,
            "Unknown whether the aircraft accepts GCS-planned missions (MIS_TKO_LAND_REQ).",
        )
    elif int(requirement) in _NEEDS_LANDING_ITEM:
        add(
            "MIS_TKO_LAND_REQ",
            Severity.WARN,
            "The aircraft requires a landing item: it will refuse GCS-planned missions.",
        )
    return findings


def blocking(findings: list[Finding]) -> list[Finding]:
    """The findings that block arm and takeoff."""
    return [f for f in findings if f.severity is Severity.BLOCK]


def describe(findings: list[Finding]) -> str:
    """One line for a rejection or a confirmation: every finding's message."""
    return " ".join(f.message for f in findings)
