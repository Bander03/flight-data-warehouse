"""Geometry helpers: great-circle distance between points and airports."""
from math import asin, cos, radians, sin, sqrt

import pandas as pd

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres between two (lat, lon) points in degrees."""
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = phi2 - phi1
    dlmb = radians(lon2) - radians(lon1)
    h = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(min(1.0, sqrt(h)))


def airport_distance_km(airport: pd.DataFrame, a_id: int, b_id: int) -> float:
    """Distance in km between two airports looked up by AirportID.

    Uses Ariport_y (latitude) and Ariport_X (longitude), as spelled in the source.
    """
    idx = airport.set_index("AirportID")
    a, b = idx.loc[a_id], idx.loc[b_id]
    return haversine_km(
        float(a["Ariport_y"]), float(a["Ariport_X"]),
        float(b["Ariport_y"]), float(b["Ariport_X"]),
    )
