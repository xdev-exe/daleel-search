import httpx
from .config import get_settings

settings = get_settings()


async def embed(text: str) -> list[float]:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{settings.bge_url.rstrip('/')}/v1/embeddings",
            json={"input": text, "model": settings.bge_model},
        )
        r.raise_for_status()
        body = r.json()
        return body["data"][0]["embedding"]
