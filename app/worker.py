import asyncio
import logging
from .config import get_settings
from .redis_store import redis, get_job, set_status, set_result
from .search_engine import execute

settings = get_settings()
log = logging.getLogger("daleel-search")


async def worker_loop(worker_id: int, stop_event: asyncio.Event):
    log.info("search worker %s started", worker_id)
    while not stop_event.is_set():
        try:
            item = await redis.blpop(settings.search_queue, timeout=1)
            if not item:
                continue
            _, job_id = item
            job = await get_job(job_id)
            if not job:
                continue

            try:
                await set_status(job_id, "RUNNING", f"Worker {worker_id} started.", {})
                result = await execute(job)
                await set_result(job_id, result)
                await set_status(
                    job_id,
                    "COMPLETED",
                    "Search completed.",
                    {"count": len(result.get("results", [])), "tookMs": result["meta"]["tookMs"]},
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.exception("search job %s failed", job_id)
                await set_status(job_id, "FAILED", "Search failed.", {"error": str(exc)[:500]})
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("worker loop error")
            await asyncio.sleep(1)
    log.info("search worker %s stopped", worker_id)
