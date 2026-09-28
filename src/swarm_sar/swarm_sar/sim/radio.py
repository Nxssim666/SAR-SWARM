"""Range-limited, lossy radio used by the simulated transport (never by the flight code)."""

from __future__ import annotations

from dataclasses import dataclass
import enum
import math

import numpy as np

from swarm_sar.core.geometry import Coordinates


class Delivery(enum.Enum):
    """Fate of one broadcast at one receiver."""

    DELIVERED = 'delivered'
    OUT_OF_RANGE = 'out_of_range'
    LOST = 'lost'


@dataclass(frozen=True)
class RadioModel:
    """Disc range plus independent per-receiver packet loss."""

    radio_range: float
    packet_loss: float = 0.0

    def __post_init__(self) -> None:
        if not math.isfinite(self.radio_range) or self.radio_range <= 0:
            raise ValueError(f'radio_range must be positive, got {self.radio_range!r}')
        if not 0.0 <= self.packet_loss < 1.0:
            raise ValueError(f'packet_loss must be in [0, 1), got {self.packet_loss!r}')

    def deliver(self, sender: Coordinates, receiver: Coordinates,
                rng: np.random.Generator) -> Delivery:
        """Decide whether a broadcast from ``sender`` is heard at ``receiver``."""
        if math.hypot(sender[0] - receiver[0], sender[1] - receiver[1]) > self.radio_range:
            return Delivery.OUT_OF_RANGE
        if self.packet_loss > 0.0 and rng.random() < self.packet_loss:
            return Delivery.LOST
        return Delivery.DELIVERED
