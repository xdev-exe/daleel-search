"""
Update/rebuild Qdrant from PublicSearchDocument.

This version deliberately keeps the MySQL query simple and enriches SHOP/SERVICE
coordinates from their source tables. For very large databases, convert this to
paged/batched iteration rather than loading every document at once.
"""
import os
import uuid
import asyncio
import aiomysql
import httpx
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

MYSQL = {
    "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
    "user": os.getenv("MYSQL_USER", "daleel_app_user"),
    "password": os.getenv("MYSQL_PASSWORD", ""),
    "db": os.getenv("MYSQL_DATABASE", "daleel_balady"),
}
QDRANT_URL = os.getenv("QDRANT_URL", "http://127.0.0.1:6333")
COLLECTION = os.getenv("QDRANT_COLLECTION", "daleel_search")
BGE_URL = os.getenv("BGE_URL", "http://127.0.0.1:8001")
BATCH = 32


def point_id(entity_type, entity_id):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"daleel:{entity_type}:{entity_id}"))


async def main():
    pool = await aiomysql.create_pool(**MYSQL, minsize=1, maxsize=3, autocommit=True, charset="utf8mb4")
    q = AsyncQdrantClient(url=QDRANT_URL)

    exists = await q.collection_exists(COLLECTION)
    if not exists:
        await q.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
            on_disk_payload=True,
        )

    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT id, entityType, entityId, slug, targetUrl, image,
                       titleAr, titleEn, subtitleAr, subtitleEn,
                       normalizedTitle, searchText, keywordsText,
                       governorateId, cityId, rating, reviewCount,
                       isVerified, isPermanentPartner, hasDiscount,
                       partnerLevel, rank, planSearchPriorityRank,
                       rankingWeight, isVisible, verificationKind
                FROM PublicSearchDocument
                WHERE isVisible = 1
            """)
            docs = await cur.fetchall()

            # Coordinates:
            # SHOP    -> Shop.locationLat/locationLon
            # SERVICE -> Service.locationLat/locationLon, with shop fallback.
            shop_ids = [d["entityId"] for d in docs if d["entityType"] == "SHOP"]
            service_ids = [d["entityId"] for d in docs if d["entityType"] == "SERVICE"]

            shops = {}
            services = {}
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
                    f"""
                    SELECT id, shopId, locationLat, locationLon
                    FROM Service WHERE id IN ({marks})
                    """,
                    service_ids,
                )
                services = {r["id"]: r for r in await cur.fetchall()}

            # Category IDs:
            doc_ids = [d["id"] for d in docs]
            categories = {}
            if doc_ids:
                # Chunk to keep IN clauses reasonable.
                for i in range(0, len(doc_ids), 1000):
                    chunk = doc_ids[i : i + 1000]
                    marks = ",".join(["%s"] * len(chunk))
                    await cur.execute(
                        f"""
                        SELECT documentId, categoryId
                        FROM PublicSearchDocumentCategory
                        WHERE documentId IN ({marks})
                        """,
                        chunk,
                    )
                    for row in await cur.fetchall():
                        categories.setdefault(row["documentId"], []).append(row["categoryId"])

    async with httpx.AsyncClient(timeout=60) as http:
        points = []
        for d in docs:
            entity_type = d["entityType"]
            lat = lon = None
            if entity_type == "SHOP":
                src = shops.get(d["entityId"])
                if src:
                    lat, lon = src.get("locationLat"), src.get("locationLon")
            elif entity_type == "SERVICE":
                src = services.get(d["entityId"])
                if src:
                    lat, lon = src.get("locationLat"), src.get("locationLon")
                    if lat is None or lon is None:
                        shop = shops.get(src.get("shopId"))
                        if shop:
                            lat, lon = shop.get("locationLat"), shop.get("locationLon")

            text = " ".join(
                str(d.get(k) or "")
                for k in ["titleAr", "titleEn", "subtitleAr", "subtitleEn", "searchText", "keywordsText"]
            ).strip()

            emb = await http.post(
                f"{BGE_URL.rstrip('/')}/v1/embeddings",
                json={"input": text, "model": "bge-m3"},
            )
            emb.raise_for_status()
            vector = emb.json()["data"][0]["embedding"]

            payload = {
                "id": d["id"],
                "entityType": entity_type,
                "entityId": d["entityId"],
                "slug": d["slug"],
                "targetUrl": d["targetUrl"],
                "image": d["image"],
                "titleAr": d["titleAr"],
                "titleEn": d["titleEn"],
                "subtitleAr": d["subtitleAr"],
                "subtitleEn": d["subtitleEn"],
                "governorateId": d["governorateId"],
                "cityId": d["cityId"],
                "categoryIds": categories.get(d["id"], []),
                "rating": float(d["rating"] or 0),
                "reviewCount": int(d["reviewCount"] or 0),
                "isVerified": bool(d["isVerified"]),
                "isPermanentPartner": bool(d["isPermanentPartner"]),
                "hasDiscount": bool(d["hasDiscount"]),
                "partnerLevel": d["partnerLevel"],
                "rank": d["rank"],
                "planSearchPriorityRank": int(d["planSearchPriorityRank"] or 0),
                "rankingWeight": float(d["rankingWeight"] or 0),
                "isVisible": bool(d["isVisible"]),
                "verificationKind": d["verificationKind"],
                "locationLat": lat,
                "locationLon": lon,
            }

            points.append(
                PointStruct(
                    id=point_id(entity_type, d["entityId"]),
                    vector=vector,
                    payload=payload,
                )
            )

            if len(points) >= BATCH:
                await q.upsert(collection_name=COLLECTION, points=points)
                print("upserted", len(points))
                points.clear()

        if points:
            await q.upsert(collection_name=COLLECTION, points=points)
            print("upserted", len(points))

    await q.close()
    pool.close()
    await pool.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())
