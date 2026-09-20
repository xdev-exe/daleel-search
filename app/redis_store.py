import json
import time
import uuid
from redis.asyncio import Redis
from .config import get_settings
from .models import SearchJob

settings = get_settings()
redis = Redis.from_url(settings.redis_url, decode_responses=True)


def job_key(job_id: str) -> str:
    return f"daleel:search:job:{job_id}"


def status_key(job_id: str) -> str:
    return f"daleel:search:status:{job_id}"


async def create_job(job: SearchJob):
    payload = job.model_dump()
    await redis.set(job_key(job.jobId), json.dumps(payload, ensure_ascii=False), ex=settings.job_ttl_seconds)
    await set_status(job.jobId, "RECEIVED", "Search received.", {"queuePosition": None})


async def enqueue(job: SearchJob):
    await redis.rpush(settings.search_queue, job.jobId)
    await set_status(job.jobId, "QUEUED", "Search queued.", {})


async def get_job(job_id: str) -> SearchJob | None:
    raw = await redis.get(job_key(job_id))
    return SearchJob.model_validate(json.loads(raw)) if raw else None


async def set_status(job_id: str, status: str, message: str, data: dict):
    body = {
        "jobId": job_id,
        "status": status,
        "message": message,
        "data": data,
        "timestamp": time.time(),
    }
    await redis.set(status_key(job_id), json.dumps(body, ensure_ascii=False), ex=settings.job_ttl_seconds)
    # Append to a short event stream. Trim aggressively.
    stream = f"daleel:search:events:{job_id}"
    await redis.xadd(stream, {"json": json.dumps(body, ensure_ascii=False)}, maxlen=100, approximate=True)
    await redis.expire(stream, settings.job_ttl_seconds)


async def get_status(job_id: str):
    raw = await redis.get(status_key(job_id))
    return json.loads(raw) if raw else None


async def set_result(job_id: str, result: dict):
    await redis.set(
        f"daleel:search:result:{job_id}",
        json.dumps(result, ensure_ascii=False),
        ex=settings.job_ttl_seconds,
    )


async def get_result(job_id: str):
    raw = await redis.get(f"daleel:search:result:{job_id}")
    return json.loads(raw) if raw else None


def new_job_id() -> str:
    return "search_" + uuid.uuid4().hex


async def queue_length() -> int:
    return await redis.llen(settings.search_queue)
