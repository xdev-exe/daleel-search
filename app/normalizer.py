import re
import unicodedata

ARABIC_DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")


def normalize_text(value: str) -> str:
    value = value or ""
    value = unicodedata.normalize("NFKC", value)
    value = ARABIC_DIACRITICS.sub("", value)

    # Arabic letter normalization; deliberately conservative.
    value = value.replace("\u0623", "\u0627").replace("\u0625", "\u0627").replace("\u0622", "\u0627")
    value = value.replace("\u0671", "\u0627")
    value = value.replace("\u0649", "\u064a")
    value = value.replace("\u0624", "\u0648").replace("\u0626", "\u064a")

    value = value.lower()
    value = re.sub(r"[\u200b-\u200f\u202a-\u202e]", " ", value)
    value = re.sub(r"[_\-./,:;!?()\[\]{}|]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


NAME_PREFIXES = {
    "dr", "doctor", "doc", "mr", "mrs", "ms",
    "\u062f", "\u062f\u0643\u062a\u0648\u0631", "\u062f\u0643\u062a\u0648\u0631\u0629",
    "\u0627\u0644\u062f\u0643\u062a\u0648\u0631", "\u0627\u0644\u062f\u0643\u062a\u0648\u0631\u0629",
    "\u0627\u0633\u062a\u0627\u0630", "\u0623\u0633\u062a\u0627\u0630", "\u0645",
    "\u0645\u0647\u0646\u062f\u0633", "\u0627\u0644\u0645\u0647\u0646\u062f\u0633",
}

SEMANTIC_HINTS = {
    "\u0639\u0627\u064a\u0632", "\u0627\u0631\u064a\u062f", "\u0645\u062d\u062a\u0627\u062c",
    "\u0645\u062d\u062a\u0627\u062c\u0647", "\u0641\u064a\u0646", "\u0627\u0641\u0636\u0644",
    "\u0642\u0631\u064a\u0628",
    "near", "nearby", "looking", "need", "want", "best",
    "recommend", "recommendation", "\u062e\u062f\u0645\u0629", "\u062e\u062f\u0645\u0627\u062a",
    "\u064a\u0639\u0627\u0644\u062c", "\u0628\u064a\u0639\u0627\u0644\u062c",
    "\u0645\u0646\u0627\u0633\u0628", "\u0645\u062a\u062e\u0635\u0635", "specialist", "service",
}

LOCATION_HINTS = {
    "\u0642\u0631\u064a\u0628", "\u0642\u0631\u064a\u0628 \u0645\u0646\u064a",
    "\u0628\u0627\u0644\u0642\u0631\u0628", "\u062c\u0646\u0628", "\u0646\u0627\u062d\u064a\u0629",
    "\u062d\u0648\u0644",
    "near", "nearby", "close", "closest", "around",
}


def tokens(text: str) -> list[str]:
    return [x for x in normalize_text(text).split() if x]


def looks_like_name_query(query: str) -> bool:
    t = tokens(query)
    if not t or len(t) > 7:
        return False
    # Remove common title words, leaving likely person/business name tokens.
    meaningful = [x for x in t if x not in {normalize_text(y) for y in NAME_PREFIXES}]
    if not meaningful:
        return False
    if any(x in {normalize_text(y) for y in SEMANTIC_HINTS} for x in t):
        return False
    # A short 1-4 token query without obvious intent words is treated as lexical/name.
    return len(meaningful) <= 5


def has_location_intent(query: str, lat: float | None, lon: float | None) -> bool:
    t = normalize_text(query)
    return (lat is not None and lon is not None) or any(h in t for h in LOCATION_HINTS)


def has_semantic_intent(query: str) -> bool:
    t = normalize_text(query)
    return any(h in t.split() or h in t for h in SEMANTIC_HINTS)


def build_mode(query: str, lat: float | None, lon: float | None) -> str:
    geo = has_location_intent(query, lat, lon)
    name = looks_like_name_query(query)
    semantic = has_semantic_intent(query)
    if name and not semantic and not geo:
        return "NAME"
    if geo and semantic:
        return "HYBRID_GEO"
    if geo:
        return "GEO"
    if semantic:
        return "HYBRID"
    return "NAME"
