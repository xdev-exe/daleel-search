from .mysql import fetch_all, placeholders
from .normalizer import normalize_text


async def lexical_search(
    query: str,
    limit: int,
    city_id=None,
    governorate_id=None,
    category_ids=None,
    entity_types=None,
):
    # MySQL FULLTEXT is used because PublicSearchDocument already defines
    # a FULLTEXT index over normalizedTitle/searchText/keywordsText.
    terms = normalize_text(query)
    if not terms:
        return []

    where = ["d.isVisible = 1"]
    args = []

    if city_id:
        where.append("d.cityId = %s")
        args.append(city_id)
    if governorate_id:
        where.append("d.governorateId = %s")
        args.append(governorate_id)
    if entity_types:
        where.append("d.entityType IN (" + placeholders(entity_types) + ")")
        args.extend(entity_types)

    # Categories are joined only when requested.
    join = ""
    if category_ids:
        join = """
        INNER JOIN PublicSearchDocumentCategory dc
          ON dc.documentId = d.id
        """
        where.append("dc.categoryId IN (" + placeholders(category_ids) + ")")
        args.extend(category_ids)

    sql = f"""
SELECT
  d.id, d.entityType, d.entityId, d.slug, d.targetUrl,
  d.image, d.titleAr, d.titleEn, d.subtitleAr, d.subtitleEn,
  d.governorateId, d.cityId, d.rating, d.reviewCount,
  d.isVerified, d.isPermanentPartner, d.hasDiscount,
  d.partnerLevel, d.rank, d.planSearchPriorityRank,
  d.rankingWeight, d.verificationKind,
  MATCH(d.normalizedTitle, d.searchText, d.keywordsText)
    AGAINST (%s IN NATURAL LANGUAGE MODE) AS lexicalScore
FROM PublicSearchDocument d
{join}
WHERE {" AND ".join(where)}
  AND MATCH(d.normalizedTitle, d.searchText, d.keywordsText)
    AGAINST (%s IN NATURAL LANGUAGE MODE)
ORDER BY lexicalScore DESC, d.rankingWeight DESC, d.rating DESC
LIMIT %s
"""
    args = [terms] + args + [terms, limit]
    return await fetch_all(sql, args)


async def exact_like_search(query: str, limit: int, city_id=None, entity_types=None):
    # Fallback for very short names where MySQL FULLTEXT can be too aggressive.
    terms = normalize_text(query)
    if not terms:
        return []
    where = ["d.isVisible = 1"]
    args = []
    if city_id:
        where.append("d.cityId = %s")
        args.append(city_id)
    if entity_types:
        where.append("d.entityType IN (" + placeholders(entity_types) + ")")
        args.extend(entity_types)
    pattern = f"%{terms}%"
    sql = f"""
SELECT
  d.id, d.entityType, d.entityId, d.slug, d.targetUrl,
  d.image, d.titleAr, d.titleEn, d.subtitleAr, d.subtitleEn,
  d.governorateId, d.cityId, d.rating, d.reviewCount,
  d.isVerified, d.isPermanentPartner, d.hasDiscount,
  d.partnerLevel, d.rank, d.planSearchPriorityRank,
  d.rankingWeight, d.verificationKind,
  1.0 AS lexicalScore
FROM PublicSearchDocument d
WHERE {" AND ".join(where)}
  AND (
    d.normalizedTitle LIKE %s
    OR LOWER(d.titleAr) LIKE %s
    OR LOWER(d.titleEn) LIKE %s
  )
ORDER BY
  CASE WHEN d.normalizedTitle = %s THEN 1 ELSE 0 END DESC,
  d.rankingWeight DESC,
  d.rating DESC
LIMIT %s
"""
    args += [pattern, pattern, pattern, terms, limit]
    return await fetch_all(sql, args)
