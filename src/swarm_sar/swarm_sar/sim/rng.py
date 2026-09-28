"""
Independent, reproducible random streams for the simulator.

Every consumer of randomness gets its own stream derived from the run seed
and a *stream id* via ``numpy.random.SeedSequence``. Streams are
statistically independent even though they share a seed, so two components
can never produce correlated draws (for example a target spawning exactly
on top of a drone). Stream ids are allocated here, in one place.

The flight code itself uses no randomness at all.
"""

from __future__ import annotations

import numbers

import numpy as np

STREAM_FOREST = 0
STREAM_TARGET = 1
STREAM_DETECTOR = 2
STREAM_RADIO = 3
_DRONE_STREAM_BASE = 1000


def drone_stream(drone_id: int) -> int:
    """Return the stream id reserved for ``drone_id`` (its depth camera noise)."""
    if isinstance(drone_id, bool) or not isinstance(drone_id, numbers.Integral) or drone_id < 0:
        raise ValueError(f'drone_id must be a non-negative integer, got {drone_id!r}')
    return _DRONE_STREAM_BASE + int(drone_id)


def make_rng(seed: int, stream: int) -> np.random.Generator:
    """Return a generator for ``stream`` that is independent of every other stream."""
    for name, value in (('seed', seed), ('stream', stream)):
        if isinstance(value, bool) or not isinstance(value, numbers.Integral) or value < 0:
            raise ValueError(f'{name} must be a non-negative integer, got {value!r}')
    sequence = np.random.SeedSequence(entropy=int(seed), spawn_key=(int(stream),))
    return np.random.default_rng(sequence)
