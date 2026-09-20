import aiomysql
from typing import Any
from .config import get_settings

settings = get_settings()
_pool = None


async def init_mysql():
    global _pool
    _pool = await aiomysql.create_pool(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        db=settings.mysql_database,
        minsize=settings.mysql_pool_min,
        maxsize=settings.mysql_pool_max,
        autocommit=True,
        charset="utf8mb4",
    )


async def close_mysql():
    global _pool
    if _pool:
        _pool.close()
        await _pool.wait_closed()
        _pool = None


def pool():
    if _pool is None:
        raise RuntimeError("MySQL pool not initialized")
    return _pool


async def fetch_all(sql: str, args: tuple | list = ()):
    async with pool().acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(sql, args)
            return await cur.fetchall()


async def fetch_one(sql: str, args: tuple | list = ()):
    async with pool().acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(sql, args)
            return await cur.fetchone()


def placeholders(items: list[Any]) -> str:
    return ",".join(["%s"] * len(items))
