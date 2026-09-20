import asyncio
import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from .models import SearchRequest, SearchJob
from .redis_store import (
    new_job_id, create_job, enqueue, get_status, get_result, queue_length,
)
from .config import get_settings

settings = get_settings()
router = APIRouter(prefix="/v1")


@router.get("/health")
async def health():
    return {"ok": True, "service": "daleel-search"}


@router.post("/search")
async def create_search(request: SearchRequest):
    job = SearchJob(jobId=new_job_id(), **request.model_dump())
    await create_job(job)
    await enqueue(job)
    return {"jobId": job.jobId, "status": "RECEIVED"}


@router.get("/search/{job_id}")
async def search_status(job_id: str):
    result = await get_result(job_id)
    status = await get_status(job_id)
    if result:
        return {"status": "COMPLETED", "result": result}
    if not status:
        raise HTTPException(404, "Search job not found")
    return status


@router.get("/search/{job_id}/events")
async def search_events(job_id: str):
    if not await get_status(job_id):
        raise HTTPException(404, "Search job not found")

    async def stream():
        last_status = None
        while True:
            status = await get_status(job_id)
            result = await get_result(job_id)

            if status:
                signature = json.dumps(status, sort_keys=True, ensure_ascii=False)
                if signature != last_status:
                    yield f"event: status\ndata: {json.dumps(status, ensure_ascii=False)}\n\n"
                    last_status = signature

            if result:
                yield f"event: result\ndata: {json.dumps(result, ensure_ascii=False)}\n\n"
                return

            if status and status.get("status") in {"FAILED", "CANCELLED"}:
                return

            await asyncio.sleep(settings.event_poll_ms / 1000)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/queue")
async def queue_info():
    return {"queued": await queue_length(), "workers": settings.search_workers}
