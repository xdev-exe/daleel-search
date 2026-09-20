import json
import httpx
from .config import get_settings
from .normalizer import normalize_text

settings = get_settings()

SYSTEM_PROMPT = """You are Daleel Balady search query parser.
Return ONLY valid JSON. No markdown.
Schema:
{
  "search_query": "short query preserving the user's important meaning",
  "name_query": "person or business name if explicitly present, otherwise empty",
  "category_terms": ["..."],
  "location_terms": ["..."],
  "wants_nearby": true,
  "mode": "NAME|SEMANTIC|HYBRID|HYBRID_GEO"
}
Rules:
- Never invent a name, category, city, or fact.
- Preserve names exactly as much as possible.
- Remove conversational filler.
- Keep the result short.
- Arabic and English are both allowed.
"""


async def rewrite_query(query: str, mode: str) -> dict:
    payload = {
        "model": settings.llama_model,
        "temperature": 0,
        "max_tokens": settings.llama_max_tokens,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Mode: {mode}\nQuery: {query}"},
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=settings.llama_timeout_seconds) as client:
            r = await client.post(f"{settings.llama_url.rstrip('/')}/v1/chat/completions", json=payload)
            r.raise_for_status()
            body = r.json()
            content = body["choices"][0]["message"]["content"]
            # Handle accidental fenced JSON.
            content = content.strip().removeprefix("```json").removesuffix("```").strip()
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                raise ValueError("llama returned non-object JSON")
            parsed["search_query"] = str(parsed.get("search_query") or normalize_text(query))
            parsed["name_query"] = str(parsed.get("name_query") or "")
            parsed["category_terms"] = parsed.get("category_terms") or []
            parsed["location_terms"] = parsed.get("location_terms") or []
            parsed["wants_nearby"] = bool(parsed.get("wants_nearby"))
            parsed["mode"] = str(parsed.get("mode") or mode)
            return parsed
    except Exception:
        # Search must remain functional if llama is unavailable.
        return {
            "search_query": normalize_text(query),
            "name_query": "",
            "category_terms": [],
            "location_terms": [],
            "wants_nearby": mode.endswith("GEO"),
            "mode": mode,
        }
