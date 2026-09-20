from dataclasses import dataclass
from .normalizer import build_mode, normalize_text


@dataclass
class RouteDecision:
    mode: str
    normalized: str
    use_lexical: bool
    use_semantic: bool
    use_geo: bool
    use_llm: bool


def route(query: str, lat=None, lon=None) -> RouteDecision:
    mode = build_mode(query, lat, lon)
    normalized = normalize_text(query)

    if mode == "NAME":
        return RouteDecision(mode, normalized, True, False, False, False)
    if mode == "GEO":
        return RouteDecision(mode, normalized, True, True, True, True)
    if mode == "HYBRID_GEO":
        return RouteDecision(mode, normalized, True, True, True, True)
    return RouteDecision(mode, normalized, True, True, False, True)
