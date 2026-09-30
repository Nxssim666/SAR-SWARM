"""Link state with hysteresis (M6): degrade at once, recover only after data holds."""

from datetime import timedelta

import pytest

from fleet_service.domain.enums import LinkState
from fleet_service.domain.links import LinkThresholds, next_link_state

T = LinkThresholds(
    stale_after=timedelta(seconds=3),
    lost_after=timedelta(seconds=15),
    recover_after=timedelta(seconds=2),
)
LIVE, STALE, LOST, OFFLINE = LinkState.LIVE, LinkState.STALE, LinkState.LOST, LinkState.OFFLINE


def s(seconds: float) -> timedelta:
    return timedelta(seconds=seconds)


@pytest.mark.parametrize(
    ("current", "age_s", "recovering_s", "expected"),
    [
        # degrading never waits
        (LIVE, 2.9, None, LIVE),
        (LIVE, 3.1, None, STALE),
        (LIVE, 15.1, None, LOST),  # straight to lost after a long silence
        (STALE, 15.1, 1.0, LOST),
        # first contact is live at once
        (OFFLINE, 0.1, None, LIVE),
        # recovering: fresh data, not yet trusted
        (STALE, 0.1, 0.5, STALE),
        (LOST, 0.1, 0.0, STALE),  # lost -> stale (recovering), never straight to live
        (LOST, 0.1, None, STALE),
        # recovered after data held for 2 s
        (STALE, 0.1, 2.0, LIVE),
        (LOST, 0.1, 5.0, LIVE),
        # a gap during recovery degrades again
        (STALE, 3.5, 1.9, STALE),
    ],
)
def test_link_state_row_by_row(
    current: LinkState, age_s: float, recovering_s: float | None, expected: LinkState
) -> None:
    recovering = None if recovering_s is None else s(recovering_s)
    assert next_link_state(current, s(age_s), recovering, T) is expected
