import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .mysql import init_mysql, close_mysql
from .redis_store import redis
from .api import router
from .worker import worker_loop

settings = get_settings()
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_mysql()
    stop_event = asyncio.Event()
    workers = [
        asyncio.create_task(worker_loop(i + 1, stop_event))
        for i in range(max(1, settings.search_workers))
    ]
    app.state.stop_event = stop_event
    app.state.workers = workers
    yield
    stop_event.set()
    await asyncio.gather(*workers, return_exceptions=True)
    await close_mysql()
    await redis.aclose()


app = FastAPI(
    title="Daleel Balady Search",
    version="1.0.0",
    lifespan=lifespan,
)

origins = [x.strip() for x in settings.cors_origins.split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins != ["*"] else ["*"],
    allow_credentials=origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
async def root():
    return {
        "service": "daleel-search",
        "version": "1.0.0",
        "docs": "/docs",
    }
