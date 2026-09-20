from .geo import haversine_meters, geo_score
from .config import get_settings

settings = get_settings()


def normalize_scores(items: list[dict], key: str):
    vals = [max(0.0, float(x.get(key) or 0)) for x in items]
    mx = max(vals) if vals else 0
    if mx <= 0:
        for x in items:
            x[key] = 0.0
    else:
        for x in items:
            x[key] = max(0.0, float(x.get(key) or 0)) / mx


def business_score(x: dict) -> float:
    # Commercial/ranking signals are bounded so they cannot overpower relevance.
    rating = min(max(float(x.get("rating") or 0), 0), 5) / 5
    reviews = min(max(int(x.get("reviewCount") or 0), 0), 1000) / 1000
    verified = 1.0 if x.get("isVerified") else 0.0
    permanent = 1.0 if x.get("isPermanentPartner") else 0.0
    priority = min(max(int(x.get("planSearchPriorityRank") or 0), 0), 100) / 100
    weight = min(max(float(x.get("rankingWeight") or 0), 0), 100) / 100

    # Relevance still dominates through the external weights.
    return (
        0.30 * rating
        + 0.10 * reviews
        + 0.20 * verified
        + 0.15 * permanent
        + 0.15 * priority
        + 0.10 * weight
    )


def rank(items: list[dict], lat=None, lon=None):
    for x in items:
        if lat is not None and lon is not None:
            d = haversine_meters(lat, lon, x.get("locationLat"), x.get("locationLon"))
            x["distanceMeters"] = d
            x["geoScore"] = geo_score(d, settings.geo_full_score_meters, settings.geo_zero_score_meters)
        else:
            x["distanceMeters"] = None
            x["geoScore"] = 0.0
        x["businessScore"] = business_score(x)

    normalize_scores(items, "lexicalScore")
    normalize_scores(items, "semanticScore")

    for x in items:
        x["score"] = (
            settings.lexical_weight * float(x.get("lexicalScore") or 0)
            + settings.semantic_weight * float(x.get("semanticScore") or 0)
            + settings.geo_weight * float(x.get("geoScore") or 0)
            + settings.business_weight * float(x.get("businessScore") or 0)
        )

    # Stable, relevance-first sort. Distance is a tie-breaker for nearby searches.
    items.sort(
        key=lambda x: (
            float(x.get("score") or 0),
            float(x.get("semanticScore") or 0),
            float(x.get("lexicalScore") or 0),
            float(x.get("businessScore") or 0),
            -(float(x.get("distanceMeters")) if x.get("distanceMeters") is not None else 1e15),
        ),
        reverse=True,
    )
    return items
