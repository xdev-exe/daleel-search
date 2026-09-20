import time
from .router import route
from .llama import rewrite_query
from .lexical import lexical_search, exact_like_search
from .bge import embed
from .qdrant import search as vector_search
from .hydrator import hydrate
from .ranker import rank
from .redis_store import set_status
from .config import get_settings

settings = get_settings()


def point_to_candidate(p):
    payload = p.payload or {}
    return {
        "entityType": payload.get("entityType"),
        "entityId": payload.get("entityId"),
        "qdrantId": str(p.id),
        "semanticScore": float(p.score or 0),
        "lexicalScore": 0.0,
        "locationLat": payload.get("locationLat"),
        "locationLon": payload.get("locationLon"),
        "titleAr": payload.get("titleAr"),
        "titleEn": payload.get("titleEn"),
        "subtitleAr": payload.get("subtitleAr"),
        "subtitleEn": payload.get("subtitleEn"),
        "targetUrl": payload.get("targetUrl"),
        "image": payload.get("image"),
        "rating": float(payload.get("rating") or 0),
        "reviewCount": int(payload.get("reviewCount") or 0),
        "isVerified": bool(payload.get("isVerified")),
        "isPermanentPartner": bool(payload.get("isPermanentPartner")),
        "hasDiscount": bool(payload.get("hasDiscount")),
        "partnerLevel": payload.get("partnerLevel"),
        "rank": payload.get("rank"),
        "planSearchPriorityRank": int(payload.get("planSearchPriorityRank") or 0),
        "rankingWeight": float(payload.get("rankingWeight") or 0),
    }


async def execute(job):
    started = time.perf_counter()
    await set_status(job.jobId, "CLASSIFYING", "Understanding the search.", {})

    decision = route(job.query, job.lat, job.lon)
    rewritten = {"search_query": decision.normalized, "name_query": ""}

    if decision.use_llm:
        await set_status(job.jobId, "REWRITING", "Refining the search query.", {})
        rewritten = await rewrite_query(job.query, decision.mode)

    search_query = rewritten.get("search_query") or decision.normalized
    name_query = rewritten.get("name_query") or ""

    lexical = []
    vector_candidates = []

    if decision.use_lexical:
        await set_status(job.jobId, "SEARCHING_DATABASE", "Searching names and database text.", {})
        lexical = await lexical_search(
            name_query or search_query,
            settings.lexical_candidates,
            city_id=job.cityId,
            governorate_id=job.governorateId,
            category_ids=job.categoryIds,
            entity_types=job.entityTypes,
        )

        # For short/name queries, add LIKE fallback and deduplicate.
        if decision.mode == "NAME":
            fallback = await exact_like_search(
                name_query or search_query,
                min(settings.lexical_candidates, 20),
                city_id=job.cityId,
                entity_types=job.entityTypes,
            )
            seen = {(x["entityType"], x["entityId"]) for x in lexical}
            lexical.extend(x for x in fallback if (x["entityType"], x["entityId"]) not in seen)

    if decision.use_semantic:
        await set_status(job.jobId, "EMBEDDING", "Creating the semantic search vector.", {})
        vector = await embed(search_query)

        await set_status(job.jobId, "SEARCHING_VECTOR", "Searching the semantic index.", {})
        points = await vector_search(
            vector,
            settings.vector_candidates,
            city_id=job.cityId,
            governorate_id=job.governorateId,
            category_ids=job.categoryIds,
            entity_types=job.entityTypes,
        )
        vector_candidates = [point_to_candidate(p) for p in points]

    await set_status(job.jobId, "MERGING", "Combining search matches.", {})

    merged = {}
    for row in lexical:
        key = (row["entityType"], row["entityId"])
        merged[key] = {
            **row,
            "semanticScore": 0.0,
            "lexicalScore": float(row.get("lexicalScore") or 0),
            "locationLat": None,
            "locationLon": None,
        }

    for row in vector_candidates:
        key = (row["entityType"], row["entityId"])
        if key in merged:
            merged[key]["semanticScore"] = max(
                float(merged[key].get("semanticScore") or 0),
                float(row.get("semanticScore") or 0),
            )
            merged[key]["locationLat"] = row.get("locationLat")
            merged[key]["locationLon"] = row.get("locationLon")
        else:
            merged[key] = row

    candidates = list(merged.values())

    await set_status(job.jobId, "LOADING_DETAILS", "Loading result details.", {})
    hydrated = await hydrate(candidates)

    # Hydration may overwrite location only if the index does not have it.
    # Extend attach_coordinates with batch Shop/Service SQL if needed.
    await attach_coordinates(hydrated)

    await set_status(job.jobId, "RANKING", "Ranking the results.", {})
    ranked = rank(hydrated, job.lat, job.lon)

    final = []
    for x in ranked[job.offset: job.offset + job.limit]:
        title = x.get("titleAr") or x.get("titleEn") or ""
        subtitle = x.get("subtitleAr") or x.get("subtitleEn")
        final.append({
            "entityType": x["entityType"],
            "entityId": x["entityId"],
            "title": title,
            "titleAr": x.get("titleAr"),
            "titleEn": x.get("titleEn"),
            "subtitle": subtitle,
            "url": x.get("targetUrl"),
            "image": x.get("image"),
            "rating": float(x.get("rating") or 0),
            "reviewCount": int(x.get("reviewCount") or 0),
            "verified": bool(x.get("isVerified")),
            "distanceMeters": x.get("distanceMeters"),
            "score": round(float(x.get("score") or 0), 6),
            "lexicalScore": round(float(x.get("lexicalScore") or 0), 6),
            "semanticScore": round(float(x.get("semanticScore") or 0), 6),
            "geoScore": round(float(x.get("geoScore") or 0), 6),
            "businessScore": round(float(x.get("businessScore") or 0), 6),
            "metadata": {
                "slug": x.get("slug"),
                "partnerLevel": x.get("partnerLevel"),
                "rank": x.get("rank"),
                "hasDiscount": x.get("hasDiscount"),
                "verificationKind": x.get("verificationKind"),
            },
        })

    elapsed = round((time.perf_counter() - started) * 1000, 2)
    return {
        "jobId": job.jobId,
        "query": job.query,
        "normalizedQuery": search_query,
        "mode": decision.mode,
        "results": final,
        "meta": {
            "total": len(ranked),
            "returned": len(final),
            "offset": job.offset,
            "tookMs": elapsed,
            "locationUsed": job.lat is not None and job.lon is not None,
            "cityId": job.cityId,
            "governorateId": job.governorateId,
        },
    }


async def attach_coordinates(items: list[dict]):
    # Exact coordinates are not stored in PublicSearchDocument. Qdrant should
    # contain them after the indexer update. If they are absent, this function
    # intentionally leaves them absent instead of pretending city coordinates
    # are exact. Extend this with batch Shop/Service SQL if needed.
    return items
