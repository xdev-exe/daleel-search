from typing import Optional, Any
from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    userId: Optional[str] = None
    sessionId: Optional[str] = None
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lon: Optional[float] = Field(default=None, ge=-180, le=180)
    cityId: Optional[str] = None
    governorateId: Optional[str] = None
    categoryIds: list[str] = Field(default_factory=list)
    entityTypes: list[str] = Field(default_factory=list)
    limit: int = Field(default=10, ge=1, le=30)
    offset: int = Field(default=0, ge=0)


class SearchJob(BaseModel):
    jobId: str
    query: str
    userId: Optional[str] = None
    sessionId: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    cityId: Optional[str] = None
    governorateId: Optional[str] = None
    categoryIds: list[str] = Field(default_factory=list)
    entityTypes: list[str] = Field(default_factory=list)
    limit: int = 10
    offset: int = 0


class SearchResult(BaseModel):
    entityType: str
    entityId: str
    title: str
    titleAr: Optional[str] = None
    titleEn: Optional[str] = None
    subtitle: Optional[str] = None
    url: Optional[str] = None
    image: Optional[str] = None
    rating: float = 0
    reviewCount: int = 0
    verified: bool = False
    distanceMeters: Optional[float] = None
    score: float = 0
    lexicalScore: float = 0
    semanticScore: float = 0
    geoScore: float = 0
    businessScore: float = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    jobId: str
    query: str
    normalizedQuery: str
    mode: str
    results: list[SearchResult]
    meta: dict[str, Any] = Field(default_factory=dict)
