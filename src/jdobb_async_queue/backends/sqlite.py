"""SQLite queue backend for lightweight persistent storage."""

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from urllib.parse import urlparse

from jdobb_async_queue.backends.base import QueueBackend
from jdobb_async_queue.schemas import Job, JobPriority, JobStatus, JobUpdate

try:
    import aiosqlite
except ImportError as e:
    raise ImportError(
        "aiosqlite package required. Install with: pip install aiosqlite"
    ) from e


class SQLiteBackend(QueueBackend):
    """SQLite implementation of queue backend.

    Provides lightweight persistent storage using SQLite. Supports atomic
    claim operations using row locking. Pub/sub is simulated in-memory
    (single process only).
    """

    def __init__(self, url: str = "sqlite:///:memory:") -> None:
        """Initialize SQLite backend.

        Args:
            url: SQLite connection URL (sqlite:///path/to/db.sqlite or sqlite:///:memory:).
        """
        self.url = url
        self._db_path = self._parse_url(url)
        self._db: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()
        self._subscribers: dict[str, list[asyncio.Queue[JobUpdate | None]]] = {}
        self._initialized = False

    def _parse_url(self, url: str) -> str:
        """Parse SQLite URL to database path."""
        parsed = urlparse(url)
        if parsed.scheme != "sqlite":
            raise ValueError(f"Invalid SQLite URL scheme: {parsed.scheme}")
        # Handle sqlite:///path and sqlite:///:memory:
        # URL format: sqlite:///absolute/path or sqlite:///:memory:
        # urlparse gives: path = "/absolute/path" or "/:memory:"
        path = parsed.path
        # Special case for :memory:
        if path == "/:memory:":
            return ":memory:"
        # Remove leading slash for absolute paths on Windows or keep for Unix
        if path.startswith("/"):
            path = path[1:]
        return path or ":memory:"

    async def _ensure_initialized(self) -> None:
        """Ensure database connection and schema are initialized."""
        if self._initialized:
            return

        async with self._lock:
            if self._initialized:
                return

            self._db = await aiosqlite.connect(self._db_path)
            self._db.row_factory = aiosqlite.Row

            # Create schema
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    job_type TEXT NOT NULL,
                    data TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'pending',
                    priority TEXT NOT NULL DEFAULT 'normal',
                    priority_weight INTEGER NOT NULL DEFAULT 5,
                    progress REAL NOT NULL DEFAULT 0.0,
                    message TEXT,
                    results TEXT,
                    error TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    ttl INTEGER,
                    expires_at TEXT
                )
            """)

            # Create indexes for efficient queries
            await self._db.execute("""
                CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)
            """)
            await self._db.execute("""
                CREATE INDEX IF NOT EXISTS idx_jobs_type_status ON jobs(job_type, status)
            """)
            await self._db.execute("""
                CREATE INDEX IF NOT EXISTS idx_jobs_priority ON jobs(priority_weight DESC, created_at ASC)
            """)

            await self._db.commit()
            self._initialized = True

    def _job_to_row(self, job: Job) -> dict:
        """Convert Job to database row dict."""
        expires_at = None
        if job.ttl:
            expires_at = (
                datetime.fromisoformat(job.created_at.isoformat())
                + __import__("datetime").timedelta(seconds=job.ttl)
            ).isoformat()

        return {
            "id": job.id,
            "job_type": job.job_type,
            "data": json.dumps(job.data),
            "status": job.status.value,
            "priority": job.priority.value,
            "priority_weight": job.priority.weight,
            "progress": job.progress,
            "message": job.message,
            "results": json.dumps(job.results) if job.results else None,
            "error": job.error,
            "metadata": json.dumps(job.metadata),
            "created_at": job.created_at.isoformat(),
            "updated_at": job.updated_at.isoformat(),
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "ttl": job.ttl,
            "expires_at": expires_at,
        }

    def _row_to_job(self, row: aiosqlite.Row) -> Job:
        """Convert database row to Job."""
        return Job(
            id=row["id"],
            job_type=row["job_type"],
            data=json.loads(row["data"]),
            status=JobStatus(row["status"]),
            priority=JobPriority(row["priority"]),
            progress=row["progress"],
            message=row["message"],
            results=json.loads(row["results"]) if row["results"] else None,
            error=row["error"],
            metadata=json.loads(row["metadata"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            completed_at=(
                datetime.fromisoformat(row["completed_at"])
                if row["completed_at"]
                else None
            ),
            ttl=row["ttl"],
        )

    async def store_job(self, job: Job) -> None:
        """Store a job in SQLite."""
        await self._ensure_initialized()

        row = self._job_to_row(job)
        async with self._lock:
            await self._db.execute(
                """
                INSERT INTO jobs (id, job_type, data, status, priority, priority_weight,
                                  progress, message, results, error, metadata,
                                  created_at, updated_at, completed_at, ttl, expires_at)
                VALUES (:id, :job_type, :data, :status, :priority, :priority_weight,
                        :progress, :message, :results, :error, :metadata,
                        :created_at, :updated_at, :completed_at, :ttl, :expires_at)
                """,
                row,
            )
            await self._db.commit()

    async def get_job(self, job_id: str) -> Job | None:
        """Retrieve a job by ID from SQLite."""
        await self._ensure_initialized()

        async with self._lock:
            # Check for expired jobs (lazy expiration)
            await self._cleanup_expired()

            cursor = await self._db.execute(
                "SELECT * FROM jobs WHERE id = ?",
                (job_id,),
            )
            row = await cursor.fetchone()

        if row is None:
            return None
        return self._row_to_job(row)

    async def _cleanup_expired(self) -> None:
        """Remove expired jobs (must be called with lock held)."""
        now = datetime.now(UTC).isoformat()
        await self._db.execute(
            "DELETE FROM jobs WHERE expires_at IS NOT NULL AND expires_at < ?",
            (now,),
        )

    async def update_job(self, job: Job) -> None:
        """Update an existing job."""
        await self._ensure_initialized()

        job.updated_at = datetime.now(UTC)
        row = self._job_to_row(job)

        async with self._lock:
            await self._db.execute(
                """
                UPDATE jobs SET
                    data = :data,
                    status = :status,
                    priority = :priority,
                    priority_weight = :priority_weight,
                    progress = :progress,
                    message = :message,
                    results = :results,
                    error = :error,
                    metadata = :metadata,
                    updated_at = :updated_at,
                    completed_at = :completed_at
                WHERE id = :id
                """,
                row,
            )
            await self._db.commit()

    async def delete_job(self, job_id: str) -> bool:
        """Delete a job from SQLite."""
        await self._ensure_initialized()

        async with self._lock:
            cursor = await self._db.execute(
                "DELETE FROM jobs WHERE id = ?",
                (job_id,),
            )
            await self._db.commit()
            return cursor.rowcount > 0

    async def claim_pending_job(self, job_types: list[str] | None = None) -> Job | None:
        """Atomically claim a pending job using SQLite row locking."""
        await self._ensure_initialized()

        async with self._lock:
            # Cleanup expired jobs first
            await self._cleanup_expired()

            # Build query based on job types filter
            if job_types:
                placeholders = ",".join("?" * len(job_types))
                query = f"""
                    SELECT * FROM jobs
                    WHERE status = 'pending'
                    AND job_type IN ({placeholders})
                    ORDER BY priority_weight DESC, created_at ASC
                    LIMIT 1
                """
                cursor = await self._db.execute(query, job_types)
            else:
                cursor = await self._db.execute("""
                    SELECT * FROM jobs
                    WHERE status = 'pending'
                    ORDER BY priority_weight DESC, created_at ASC
                    LIMIT 1
                    """)

            row = await cursor.fetchone()
            if row is None:
                return None

            job = self._row_to_job(row)

            # Update status atomically
            job.status = JobStatus.PROCESSING
            job.updated_at = datetime.now(UTC)

            await self._db.execute(
                """
                UPDATE jobs SET status = ?, updated_at = ?
                WHERE id = ? AND status = 'pending'
                """,
                (job.status.value, job.updated_at.isoformat(), job.id),
            )
            await self._db.commit()

            return job

    async def publish_update(self, update: JobUpdate) -> None:
        """Publish a job update to in-memory subscribers."""
        async with self._lock:
            queues = self._subscribers.get(update.job_id, [])
            for queue in queues:
                await queue.put(update)

            # If job is terminal, signal end to subscribers
            if update.status in (
                JobStatus.COMPLETE,
                JobStatus.FAILED,
                JobStatus.CANCELLED,
            ):
                for queue in queues:
                    await queue.put(None)

    async def subscribe_updates(self, job_id: str) -> AsyncIterator[JobUpdate]:
        """Subscribe to updates for a specific job (in-memory only)."""
        queue: asyncio.Queue[JobUpdate | None] = asyncio.Queue()

        async with self._lock:
            if job_id not in self._subscribers:
                self._subscribers[job_id] = []
            self._subscribers[job_id].append(queue)

        try:
            while True:
                update = await queue.get()
                if update is None:
                    break
                yield update
        finally:
            async with self._lock:
                if job_id in self._subscribers:
                    try:
                        self._subscribers[job_id].remove(queue)
                    except ValueError:
                        pass
                    if not self._subscribers[job_id]:
                        del self._subscribers[job_id]

    async def close(self) -> None:
        """Close SQLite connection and cleanup resources."""
        async with self._lock:
            # Signal all subscribers to stop
            for queues in self._subscribers.values():
                for queue in queues:
                    await queue.put(None)
            self._subscribers.clear()

            if self._db:
                await self._db.close()
                self._db = None
            self._initialized = False
