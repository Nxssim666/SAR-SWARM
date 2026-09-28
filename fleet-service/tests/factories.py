"""Request bodies and API shortcuts used across tests."""

from typing import Any

import httpx

# Zurich area: a realistic mid-latitude base where a lat/lon swap lands in the Indian Ocean.
BASE = {"latitude": 47.3977, "longitude": 8.5456}


def square(
    lat: float = BASE["latitude"], lon: float = BASE["longitude"], half: float = 0.005
) -> dict[str, Any]:
    """A counter-clockwise GeoJSON square centred on (lat, lon); ``half`` in degrees."""
    ring = [
        [lon - half, lat - half],
        [lon + half, lat - half],
        [lon + half, lat + half],
        [lon - half, lat + half],
        [lon - half, lat - half],
    ]
    return {"type": "Polygon", "coordinates": [ring]}


async def create(
    client: httpx.AsyncClient, path: str, headers: dict[str, str], body: dict[str, Any]
) -> dict[str, Any]:
    """POST and return the created resource (asserting 201)."""
    response = await client.post(f"/api/v1/{path}", json=body, headers=headers)
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


async def incident(
    client: httpx.AsyncClient, headers: dict[str, str], **overrides: Any
) -> dict[str, Any]:
    """Create an incident at BASE with a 25 km operating radius."""
    body = {"name": "Missing hiker, Uetliberg", "base": BASE, "operating_radius_m": 25_000.0}
    return await create(client, "incidents", headers, body | overrides)


async def search_area(
    client: httpx.AsyncClient, headers: dict[str, str], incident_id: str, **overrides: Any
) -> dict[str, Any]:
    """Create a search area (a ~1 km square at BASE)."""
    body = {"incident_id": incident_id, "name": "Sector A", "geometry": square()}
    return await create(client, "search-areas", headers, body | overrides)


async def aircraft(
    client: httpx.AsyncClient, headers: dict[str, str], callsign: str, **overrides: Any
) -> dict[str, Any]:
    """Register a hexacopter reachable over MAVLink by default."""
    body: dict[str, Any] = {"callsign": callsign, "airframe": "multirotor_hexa"}
    return await create(client, "aircraft", headers, body | overrides)


async def mission(
    client: httpx.AsyncClient, headers: dict[str, str], incident_id: str, **overrides: Any
) -> dict[str, Any]:
    """Create a draft waypoint mission."""
    body = {
        "incident_id": incident_id,
        "name": "Ridge sweep",
        "kind": "waypoint",
        "default_altitude_relative_m": 60.0,
    }
    return await create(client, "missions", headers, body | overrides)


def waypoint(lat: float, lon: float, alt: float = 60.0) -> dict[str, Any]:
    """A waypoint body."""
    return {"latitude": lat, "longitude": lon, "altitude_relative_m": alt}
