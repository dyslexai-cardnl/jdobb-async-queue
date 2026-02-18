"""Queue backend implementations."""

from jdobb_async_queue.backends.base import QueueBackend
from jdobb_async_queue.backends.memory import MemoryBackend

__all__ = ["QueueBackend", "MemoryBackend"]


def get_redis_backend():
    """Lazy import of RedisBackend to avoid requiring redis dependency."""
    from jdobb_async_queue.backends.redis import RedisBackend

    return RedisBackend


def get_sqlite_backend():
    """Lazy import of SQLiteBackend to avoid requiring aiosqlite dependency."""
    from jdobb_async_queue.backends.sqlite import SQLiteBackend

    return SQLiteBackend
