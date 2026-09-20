from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchAny, MatchValue
from .config import get_settings

settings = get_settings()
client = AsyncQdrantClient(url=settings.qdrant_url)


def _filter(
    city_id=None,
    governorate_id=None,
    category_ids=None,
    entity_types=None,
):
    must = [
        FieldCondition(key="isVisible", match=MatchValue(value=True))
    ]
    if city_id:
        must.append(FieldCondition(key="cityId", match=MatchValue(value=city_id)))
    if governorate_id:
        must.append(FieldCondition(key="governorateId", match=MatchValue(value=governorate_id)))
    if category_ids:
        must.append(FieldCondition(key="categoryIds", match=MatchAny(any=category_ids)))
    if entity_types:
        must.append(FieldCondition(key="entityType", match=MatchAny(any=entity_types)))
    return Filter(must=must)


async def search(
    vector,
    limit,
    city_id=None,
    governorate_id=None,
    category_ids=None,
    entity_types=None,
):
    result = await client.query_points(
        collection_name=settings.qdrant_collection,
        query=vector,
        query_filter=_filter(city_id, governorate_id, category_ids, entity_types),
        limit=limit,
        with_payload=True,
        with_vectors=False,
    )
    return result.points
