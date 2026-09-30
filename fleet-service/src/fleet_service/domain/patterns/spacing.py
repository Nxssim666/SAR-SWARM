"""Lane spacing from the camera footprint (ADR 0028)."""

import math

from fleet_service.domain.patterns.route import PatternError

MIN_SPACING_M = 5.0
MAX_SPACING_M = 2000.0


def footprint_width_m(height_agl_m: float, hfov_deg: float) -> float:
    """The ground width a downward camera sees across track: 2 · h · tan(HFOV / 2)."""
    if height_agl_m <= 0.0:
        raise PatternError("invalid-height", "The height above ground must be positive.")
    if not 0.0 < hfov_deg < 180.0:
        raise PatternError("invalid-fov", "The horizontal field of view must be 0-180 degrees.")
    return 2.0 * height_agl_m * math.tan(math.radians(hfov_deg) / 2.0)


def lane_spacing_m(height_agl_m: float, hfov_deg: float, overlap: float) -> float:
    """The distance between lanes so neighbouring footprints overlap by ``overlap`` (0-0.9)."""
    if not 0.0 <= overlap <= 0.9:
        raise PatternError("invalid-overlap", "The overlap must be between 0 and 0.9.")
    return check_spacing(footprint_width_m(height_agl_m, hfov_deg) * (1.0 - overlap))


def check_spacing(spacing_m: float) -> float:
    """Reject spacings no search can use."""
    if not MIN_SPACING_M <= spacing_m <= MAX_SPACING_M:
        raise PatternError(
            "invalid-spacing",
            f"The lane spacing must be {MIN_SPACING_M:g}-{MAX_SPACING_M:g} m "
            f"(got {spacing_m:.1f} m).",
        )
    return spacing_m
