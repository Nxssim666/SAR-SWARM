"""
Link state with hysteresis (M6). Pure: the registry applies it.

A link degrades at once, by the age of the newest sample: live, then stale after
``stale_after``, then lost after ``lost_after`` (safety never waits). It recovers only once
samples have kept arriving, without a gap longer than ``stale_after``, for
``recover_after``: a radio at the edge of its range that delivers a sample now and then
must not make the aircraft look live, re-enable its commands and clear its alerts, only to
lose it again a second later. Fresh data after a loss shows as stale (recovering) until
then; first contact is live at once.
"""

from dataclasses import dataclass
from datetime import timedelta

from fleet_service.domain.enums import LinkState


@dataclass(frozen=True)
class LinkThresholds:
    """When a link degrades, and how long it must hold to recover."""

    stale_after: timedelta
    lost_after: timedelta
    recover_after: timedelta


def next_link_state(
    current: LinkState,
    age: timedelta,
    recovering_for: timedelta | None,
    thresholds: LinkThresholds,
) -> LinkState:
    """The link state for a sample ``age`` old.

    ``recovering_for``: how long samples have flowed without a gap since the link was last
    degraded (None when they have not).
    """
    if age > thresholds.lost_after:
        return LinkState.LOST
    if age > thresholds.stale_after:
        return LinkState.STALE
    if current in (LinkState.LIVE, LinkState.OFFLINE):
        return LinkState.LIVE
    if recovering_for is not None and recovering_for >= thresholds.recover_after:
        return LinkState.LIVE
    return LinkState.STALE  # data again, not yet trusted
