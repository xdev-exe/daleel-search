from math import radians, sin, cos, asin, sqrt
from typing import Optional


def haversine_meters(lat1, lon1, lat2, lon2) -> Optional[float]:
    if None in (lat1, lon1, lat2, lon2):
        return None
    r = 6371000.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r * asin(sqrt(a))


def geo_score(distance: Optional[float], full=500, zero=25000) -> float:
    if distance is None:
        return 0.0
    if distance <= full:
        return 1.0
    if distance >= zero:
        return 0.0
    # Smooth-ish linear decay. Intentionally easy to tune.
    return 1.0 - ((distance - full) / (zero - full))
