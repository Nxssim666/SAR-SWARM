"""Tests for swarm_sar.core.swarm: peers, the shared target estimate and the tracker election."""

import math

import numpy as np
import pytest
from swarm_sar.core.config import DroneConfig
from swarm_sar.core.coverage import GridGeometry
from swarm_sar.core.geodesy import GeoPoint
from swarm_sar.core.geometry import Bounds
from swarm_sar.core.messages import DroneStatus, HealthLevel, Phase, Receipt
from swarm_sar.core.swarm import (elect_tracker, election_key, extrapolate, MAX_PEERS, PeerTable,
                                  TargetEstimator, TRACK_ADOPTED, TRACK_DROPPED,
                                  TRACK_INITIATED)
from swarm_sar.core.tracking import Detection, TargetEstimate

CFG = DroneConfig()


def status(drone_id, stamp):
    return DroneStatus(drone_id, stamp, GeoPoint(47.0, 8.0), (0.0, 0.0), 0.0, Phase.SEARCH,
                       HealthLevel.OK, 0, 1, 0)


def test_peer_offer_receipts():
    table = PeerTable(0, CFG)
    assert table.offer(status(1, 10.0), 10.0, protocol=1) is Receipt.INCOMPATIBLE
    assert table.offer(status(0, 10.0), 10.0) is Receipt.OWN
    assert table.offer(status(1, 11.0), 10.0) is Receipt.FUTURE
    assert table.offer(status(1, 8.0), 10.0) is Receipt.STALE
    assert table.offer(status(1, 10.0), 10.0) is Receipt.ACCEPTED
    assert table.offer(status(1, 10.0), 10.1) is Receipt.OUT_OF_ORDER
    assert table.offer(status(1, 9.9), 10.1) is Receipt.OUT_OF_ORDER
    assert table.offer(status(1, 10.2), 10.2) is Receipt.ACCEPTED
    assert [s.stamp for s in table.active()] == [10.2]


def test_peer_table_is_bounded():
    table = PeerTable(0, CFG)
    for i in range(1, MAX_PEERS + 1):
        assert table.offer(status(i, 0.0), 0.0) is Receipt.ACCEPTED
    assert table.offer(status(MAX_PEERS + 1, 0.0), 0.0) is Receipt.IGNORED
    assert table.offer(status(1, 0.1), 0.1) is Receipt.ACCEPTED  # known peers still update
    assert len(table) == MAX_PEERS


def test_silent_peers_become_ghosts_and_are_then_forgotten():
    table = PeerTable(0, CFG)
    table.offer(status(1, 0.0), 0.0)
    table.expire(CFG.peer_timeout)
    assert len(table.active()) == 1
    table.expire(CFG.peer_timeout + 0.1)
    assert table.active() == [] and len(table.lost()) == 1  # still avoided
    lost_at = CFG.peer_timeout + 0.1
    table.expire(lost_at + CFG.lost_peer_memory - 0.01)
    assert len(table.lost()) == 1
    table.expire(lost_at + CFG.lost_peer_memory + 0.1)
    assert len(table) == 0
    table.offer(status(2, 20.0), 20.0)
    table.clear()
    assert len(table) == 0


def test_a_lost_peer_that_speaks_again_is_active():
    table = PeerTable(0, CFG)
    table.offer(status(1, 0.0), 0.0)
    table.expire(5.0)
    assert table.offer(status(1, 5.0), 5.0) is Receipt.ACCEPTED
    assert len(table.active()) == 1 and table.lost() == []


def detection(t, x=10.0, y=0.0, std=1.0):
    return Detection.isotropic(t, (x, y), std)


def kinds(events):
    return [kind for kind, _ in events]


def test_first_detection_initiates_a_track_and_later_ones_refine_it():
    est = TargetEstimator(CFG)
    assert kinds(est.update(1.0, (0.0, 0.0), False, [detection(1.0)], [])) == [TRACK_INITIATED]
    first_std = est.estimate.position_std
    est.update(1.5, (0.0, 0.0), False, [detection(1.5)], [])
    assert est.estimate.position_std < first_std + 1.0
    assert est.estimate.stamp == 1.5


def test_old_and_future_detections_are_ignored():
    est = TargetEstimator(CFG)
    est.update(10.0, None, False, [detection(10.0 - CFG.max_detection_age - 0.1),
                                   detection(10.0 + CFG.max_clock_skew + 0.1)], [])
    assert est.estimate is None


def test_peer_estimate_is_adopted_and_fused():
    est = TargetEstimator(CFG)
    heard = TargetEstimate(np.array([5.0, 5.0, 0.0, 0.0]), np.eye(4), 1.0, 1.0)
    assert kinds(est.update(1.0, None, False, [], [(7, heard)])) == [TRACK_ADOPTED]
    assert est.estimate.position == pytest.approx((5.0, 5.0))
    too_vague = TargetEstimate(np.zeros(4), np.eye(4) * 400.0, 1.0, 1.0)
    fresh = TargetEstimator(CFG)
    fresh.update(1.0, None, False, [], [(7, too_vague)])
    assert fresh.estimate is None


def test_track_is_dropped_when_too_uncertain_and_leaves_a_datum_for_involved_drones():
    est = TargetEstimator(CFG)
    est.update(0.0, (10.0, 0.0), True, [detection(0.0)], [])
    events = est.update(200.0, (10.0, 0.0), True, [], [])
    assert TRACK_DROPPED in kinds(events)
    assert est.estimate is None and est.datum is not None
    assert est.datum.position == pytest.approx((10.0, 0.0))


def test_far_relay_does_not_get_a_datum():
    est = TargetEstimator(CFG)
    est.update(0.0, (500.0, 0.0), False, [detection(0.0)], [])
    est.update(200.0, (500.0, 0.0), False, [], [])
    assert est.estimate is None and est.datum is None


def test_dropped_track_is_not_revived_by_stale_gossip():
    # Regression (v1): peers echoing an old estimate back resurrected a dropped track.
    est = TargetEstimator(CFG)
    est.update(0.0, (10.0, 0.0), True, [detection(0.0)], [])
    est.update(200.0, (10.0, 0.0), True, [], [])
    echo = TargetEstimate(np.array([10.0, 0.0, 0.0, 0.0]), np.eye(4), 200.0, 0.0)
    assert est.update(200.1, (10.0, 0.0), True, [], [(4, echo)]) == []
    assert est.estimate is None
    newer = TargetEstimate(np.array([12.0, 0.0, 0.0, 0.0]), np.eye(4), 200.1, 200.1)
    assert kinds(est.update(200.2, (10.0, 0.0), True, [], [(4, newer)])) == [TRACK_ADOPTED]


def test_datum_boost_concentrates_search_and_expires():
    geometry = GridGeometry(Bounds(0.0, -50.0, 100.0, 50.0), 5.0)
    est = TargetEstimator(CFG)
    assert est.datum_boost(0.0, geometry) is None
    est.update(0.0, (10.0, 0.0), True, [detection(0.0)], [])
    est.update(100.0, (10.0, 0.0), True, [], [])
    boost = est.datum_boost(100.0, geometry)
    near = boost[geometry.index_of((10.0, 0.0))]
    far = boost[geometry.index_of((95.0, 45.0))]
    assert near > far >= 1.0 and near <= 1.0 + CFG.datum_gain
    assert est.datum_boost(100.0 + CFG.datum_ttl + 1.0, geometry) is None
    assert est.datum is None
    est.reset()
    assert est.estimate is None


def test_election_key_bands_ties_and_hysteresis():
    assert election_key(3.0, 5, False, 6.0) == ((0, 5), 3.0)
    assert election_key(13.0, 5, False, 6.0)[0] == (1, 5)
    assert election_key(13.0, 5, True, 6.0) == ((0, 5), 10.0)  # incumbent bonus
    assert election_key(1.0, 5, True, 6.0)[1] == 0.0


def test_the_nearest_drones_track():
    target = (0.0, 0.0)
    peers = [(1, (5.0, 0.0), False), (2, (25.0, 0.0), False)]
    assert elect_tracker(3, (6.0, 0.0), False, target, peers, CFG)  # band 0 with id 1
    assert not elect_tracker(3, (26.0, 0.0), False, target, peers, CFG)  # third in line
    far = [(1, (100.0, 0.0), False)]
    assert not elect_tracker(3, (40.0, 0.0), False, target, far, CFG)  # beyond recruit radius


def test_ties_break_by_id_so_roles_do_not_flap():
    target = (0.0, 0.0)
    ring = [(1, (6.0, 0.0), True), (2, (0.0, 6.0), True)]
    assert not elect_tracker(5, (-6.0, 0.0), False, target, ring, CFG)
    assert elect_tracker(0, (-6.0, 0.0), False, target, ring, CFG)


def test_extrapolate_is_capped_and_never_backwards():
    assert extrapolate((0.0, 0.0), (2.0, 0.0), 10.0, 10.5) == (1.0, 0.0)
    assert extrapolate((0.0, 0.0), (2.0, 0.0), 10.0, 20.0) == (2.0, 0.0)
    assert extrapolate((0.0, 0.0), (2.0, 0.0), 10.0, 9.0) == (0.0, 0.0)
    assert math.isfinite(extrapolate((0.0, 0.0), (1e3, 1e3), 0.0, 1e9)[0])
