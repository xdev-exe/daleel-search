"""
update_qdrant_payload.py

Updates Qdrant point *payloads* for all documents in PublicSearchDocument
WITHOUT re-embedding. Use this after schema/data changes to keep Qdrant
payload fields in sync with MySQL.

Only re-embeds if the text content has changed (normalizedTitle + searchText
+ keywordsText hash differs from what is stored in the point payload).

Run:
    source .venv/bin/activate
    python update_qdrant_payload.py

Set env vars or edit the constants below. Uses the same .env as the main app.
"""

import os
import uuid
import asyncio
import hashlib
import aiomysql
import httpx
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, SetPayload, PointIdsList,
)
from dotenv import load_dotenv

load_dotenv()

MYSQL = dict(
    host=os.getenv("MYSQL_HOST", "127.0.0.1"),
    port=int(os.getenv("MYSQL_PORT", "3306")),
    user=os.getenv("MYSQL_USER", "daleel_app_user"),
    password=os.getenv("MYSQL_PASSWORD", ""),
    db=os.getenv("MYSQL_DATABASE", "daleel_balady"),
)
QDRANT_URL  = os.getenv("QDRANT_URL",        "http://127.0.0.1:6333")
COLLECTION  = os.getenv("QDRANT_COLLECTION", "daleel_search")
BGE_URL     = os.getenv("BGE_URL",           "http://127.0.0.1:8091")
BGE_MODEL   = os.getenv("BGE_MODEL",         "bge-m3")

# How many points to update in one Qdrant set_payload call
PAYLOAD_BATCH = 100
# How many points to re-embed + upsert in one Qdrant upsert call
EMBED_BATCH   = 16


def point_id(entity_type: str, entity_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"daleel:{entity_type}:{entity_id}"))


def text_hash(d: dict) -> str:
    text = " ".join(
        str(d.get(k) or "")
        for k in ["titleAr", "titleEn", "subtitleAr", "subtitleEn",
                  "searchText", "keywordsText"]
    )
    return hashlib.sha1(text.encode()).hexdigest()


async def fetch_mysql(pool) -> list[dict]:
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:

            # Main document fields
            await cur.execute("""
                SELECT id, entityType, entityId, slug, targetUrl, image,
                       titleAr, titleEn, subtitleAr, subtitleEn,
                       normalizedTitle, searchText, keywordsText,
                       governorateId, cityId, rating, reviewCount,
                       isVerified, isPermanentPartner, hasDiscount,
                       partnerLevel, `rank`, planSearchPriorityRank,
                       rankingWeight, isVisible, verificationKind
                FROM PublicSearchDocument
                WHERE isVisible = 1
            """)
            docs = list(await cur.fetchall())

            # Coordinates
            shop_ids    = [d["entityId"] for d in docs if d["entityType"] == "SHOP"]
            service_ids = [d["entityId"] for d in docs if d["entityType"] == "SERVICE"]

            shops, services = {}, {}

            if shop_ids:
                marks = ",".join(["%s"] * len(shop_ids))
                await cur.execute(
                    f"SELECT id, locationLat, locationLon FROM Shop WHERE id IN ({marks})",
                    shop_ids,
                )
                shops = {r["id"]: r for r in await cur.fetchall()}

            if service_ids:
                marks = ",".join(["%s"] * len(service_ids))
                await cur.execute(
                    f"""SELECT id, shopId, locationLat, locationLon
                        FROM Service WHERE id IN ({marks})""",
                    service_ids,
                )
                services = {r["id"]: r for r in await cur.fetchall()}

            # Category IDs (chunked)
            doc_ids    = [d["id"] for d in docs]
            categories: dict[str, list] = {}
            for i in range(0, len(doc_ids), 1000):
                chunk = doc_ids[i : i + 1000]
                marks = ",".join(["%s"] * len(chunk))
                await cur.execute(
                    f"""SELECT documentId, categoryId
                        FROM PublicSearchDocumentCategory
                        WHERE documentId IN ({marks})""",
                    chunk,
                )
                for row in await cur.fetchall():
                    categories.setdefault(row["documentId"], []).append(row["categoryId"])

    # Resolve coordinates
    for d in docs:
        lat = lon = None
        et  = d["entityType"]
        if et == "SHOP":
            src = shops.get(d["entityId"])
            if src:
                lat, lon = src.get("locationLat"), src.get("locationLon")
        elif et == "SERVICE":
            src = services.get(d["entityId"])
            if src:
                lat, lon = src.get("locationLat"), src.get("locationLon")
                if lat is None or lon is None:
                    shop = shops.get(src.get("shopId"))
                    if shop:
                        lat, lon = shop.get("locationLat"), shop.get("locationLon")
        d["locationLat"]  = lat
        d["locationLon"]  = lon
        d["categoryIds"]  = categories.get(d["id"], [])

    return docs


def build_payload(d: dict) -> dict:
    return {
        "id":                   d["id"],
        "entityType":           d["entityType"],
        "entityId":             d["entityId"],
        "slug":                 d["slug"],
        "targetUrl":            d["targetUrl"],
        "image":                d["image"],
        "titleAr":              d["titleAr"],
        "titleEn":              d["titleEn"],
        "subtitleAr":           d["subtitleAr"],
        "subtitleEn":           d["subtitleEn"],
        "governorateId":        d["governorateId"],
        "cityId":               d["cityId"],
        "categoryIds":          d["categoryIds"],
        "rating":               float(d["rating"] or 0),
        "reviewCount":          int(d["reviewCount"] or 0),
        "isVerified":           bool(d["isVerified"]),
        "isPermanentPartner":   bool(d["isPermanentPartner"]),
        "hasDiscount":          bool(d["hasDiscount"]),
        "partnerLevel":         d["partnerLevel"],
        "rank":                 d["rank"],
        "planSearchPriorityRank": int(d["planSearchPriorityRank"] or 0),
        "rankingWeight":        float(d["rankingWeight"] or 0),
        "isVisible":            bool(d["isVisible"]),
        "verificationKind":     d["verificationKind"],
        "locationLat":          d["locationLat"],
        "locationLon":          d["locationLon"],
        "_textHash":            text_hash(d),
    }


async def fetch_existing_hashes(q: AsyncQdrantClient, ids: list[str]) -> dict[str, str]:
    """Fetch _textHash from existing Qdrant points in batches."""
    hashes: dict[str, str] = {}
    batch_size = 100
    for i in range(0, len(ids), batch_size):
        chunk = ids[i : i + batch_size]
        records = await q.retrieve(
            collection_name=COLLECTION,
            ids=chunk,
            with_payload=["_textHash"],
            with_vectors=False,
        )
        for r in records:
            h = (r.payload or {}).get("_textHash")
            if h:
                hashes[r.id] = h
    return hashes


async def embed(http: httpx.AsyncClient, text: str) -> list[float]:
    r = await http.post(
        f"{BGE_URL.rstrip('/')}/v1/embeddings",
        json={"input": text, "model": BGE_MODEL},
    )
    r.raise_for_status()
    return r.json()["data"][0]["embedding"]


async def main():
    pool = await aiomysql.create_pool(
        **MYSQL, minsize=1, maxsize=4, autocommit=True, charset="utf8mb4"
    )
    q = AsyncQdrantClient(url=QDRANT_URL)

    # Ensure collection exists
    if not await q.collection_exists(COLLECTION):
        print(f"Collection '{COLLECTION}' does not exist — creating it.")
        await q.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
            on_disk_payload=True,
        )

    print("Fetching documents from MySQL …")
    docs = await fetch_mysql(pool)
    print(f"  {len(docs)} visible documents")

    # Map point_id -> doc
    id_map = {point_id(d["entityType"], d["entityId"]): d for d in docs}
    all_ids = list(id_map.keys())

    print("Fetching existing text hashes from Qdrant …")
    existing_hashes = await fetch_existing_hashes(q, all_ids)
    print(f"  {len(existing_hashes)} points already in Qdrant")

    # Split into: payload-only update vs full re-embed
    need_embed   = []   # new or text changed
    payload_only = []   # exists and text unchanged

    for pid, d in id_map.items():
        new_hash = text_hash(d)
        if pid not in existing_hashes or existing_hashes[pid] != new_hash:
            need_embed.append((pid, d))
        else:
            payload_only.append((pid, d))

    print(f"  {len(need_embed)} points need re-embedding")
    print(f"  {len(payload_only)} points need payload update only")

    # ── 1. Payload-only updates (fast, no embedding) ─────────────────────────
    updated_payload = 0
    for i in range(0, len(payload_only), PAYLOAD_BATCH):
        chunk = payload_only[i : i + PAYLOAD_BATCH]
        for pid, d in chunk:
            await q.set_payload(
                collection_name=COLLECTION,
                payload=build_payload(d),
                points=[pid],
            )
        updated_payload += len(chunk)
        print(f"  payload updated {updated_payload}/{len(payload_only)}", end="\r")
    if payload_only:
        print()

    # ── 2. Re-embed + upsert (slower) ────────────────────────────────────────
    upserted = 0
    async with httpx.AsyncClient(timeout=60) as http:
        batch_points: list[PointStruct] = []

        for pid, d in need_embed:
            text = " ".join(
                str(d.get(k) or "")
                for k in ["titleAr", "titleEn", "subtitleAr", "subtitleEn",
                           "searchText", "keywordsText"]
            ).strip()

            vector = await embed(http, text)
            batch_points.append(
                PointStruct(id=pid, vector=vector, payload=build_payload(d))
            )

            if len(batch_points) >= EMBED_BATCH:
                await q.upsert(collection_name=COLLECTION, points=batch_points)
                upserted += len(batch_points)
                print(f"  upserted {upserted}/{len(need_embed)}", end="\r")
                batch_points.clear()

        if batch_points:
            await q.upsert(collection_name=COLLECTION, points=batch_points)
            upserted += len(batch_points)

    if need_embed:
        print(f"  upserted {upserted}/{len(need_embed)}")

    # ── 3. Delete points no longer in MySQL ──────────────────────────────────
    existing_ids = set(existing_hashes.keys())
    mysql_ids    = set(id_map.keys())
    stale_ids    = existing_ids - mysql_ids
    if stale_ids:
        print(f"Deleting {len(stale_ids)} stale points …")
        await q.delete(
            collection_name=COLLECTION,
            points_selector=PointIdsList(points=list(stale_ids)),
        )

    await q.close()
    pool.close()
    await pool.wait_closed()

    print(
        f"\nDone. "
        f"{updated_payload} payload-only, "
        f"{upserted} re-embedded, "
        f"{len(stale_ids)} deleted."
    )


if __name__ == "__main__":
    asyncio.run(main())
