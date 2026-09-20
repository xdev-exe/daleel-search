from .mysql import fetch_all

MEDIA_TARGETS = {
    "SHOP": "SHOP",
    "SERVICE": "SERVICE",
    "PRODUCT": "PRODUCT",
    "OFFER": "OFFER",
    "PROVIDER": "USER",
    "CARD": "OTHER",
    "CV": "OTHER",
}


async def hydrate(candidates: list[dict]):
    if not candidates:
        return []

    # PublicSearchDocument provides the stable card fields.
    keys = [(x["entityType"], x["entityId"]) for x in candidates]
    conditions = " OR ".join(["(entityType=%s AND entityId=%s)"] * len(keys))
    args = [v for pair in keys for v in pair]

    docs = await fetch_all(
        f"""
        SELECT id, entityType, entityId, slug, targetUrl, image,
               titleAr, titleEn, subtitleAr, subtitleEn,
               governorateId, cityId, rating, reviewCount,
               isVerified, isPermanentPartner, hasDiscount,
               partnerLevel, `rank`, planSearchPriorityRank,
               rankingWeight, verificationKind
        FROM PublicSearchDocument
        WHERE isVisible = 1 AND ({conditions})
        """,
        args,
    )

    doc_map = {(d["entityType"], d["entityId"]): d for d in docs}

    # Media is polymorphic. Fetch all applicable targets in one query.
    media_keys = []
    for c in candidates:
        target = MEDIA_TARGETS.get(c["entityType"])
        if target:
            media_keys.append((target, c["entityId"]))

    media = []
    if media_keys:
        mcond = " OR ".join(["(targetType=%s AND targetId=%s)"] * len(media_keys))
        margs = [v for pair in media_keys for v in pair]
        media = await fetch_all(
            f"""
            SELECT targetType, targetId, url, mediaType, `order`
            FROM Media
            WHERE deletedAt IS NULL AND ({mcond})
            ORDER BY `order` ASC
            """,
            margs,
        )

    media_map = {}
    for m in media:
        media_map.setdefault((m["targetType"], m["targetId"]), []).append(m)

    hydrated = []
    for c in candidates:
        key = (c["entityType"], c["entityId"])
        d = doc_map.get(key)
        if not d:
            continue

        target = MEDIA_TARGETS.get(c["entityType"])
        imgs = media_map.get((target, c["entityId"]), [])
        image = d.get("image") or (imgs[0]["url"] if imgs else None)

        item = dict(c)
        item.update({
            "slug": d.get("slug"),
            "targetUrl": d.get("targetUrl"),
            "image": image,
            "titleAr": d.get("titleAr"),
            "titleEn": d.get("titleEn"),
            "subtitleAr": d.get("subtitleAr"),
            "subtitleEn": d.get("subtitleEn"),
            "rating": float(d.get("rating") or 0),
            "reviewCount": int(d.get("reviewCount") or 0),
            "isVerified": bool(d.get("isVerified")),
            "isPermanentPartner": bool(d.get("isPermanentPartner")),
            "hasDiscount": bool(d.get("hasDiscount")),
            "partnerLevel": d.get("partnerLevel"),
            "rank": d.get("rank"),
            "planSearchPriorityRank": int(d.get("planSearchPriorityRank") or 0),
            "rankingWeight": float(d.get("rankingWeight") or 0),
            "verificationKind": d.get("verificationKind"),
        })
        hydrated.append(item)

    return hydrated
