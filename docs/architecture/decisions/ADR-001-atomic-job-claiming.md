# ADR-001: Atomic Job Claiming

| Field | Value |
|-------|-------|
| Status | Implemented |
| Date | 2026-02-13 |
| Decision Makers | jdobb |
| Supersedes | N/A |

## Context

### Problem Statement
When multiple workers poll for jobs simultaneously, there's a race condition:
1. Worker A reads job X (status=pending)
2. Worker B reads job X (status=pending)
3. Worker A updates job X (status=processing)
4. Worker B updates job X (status=processing) -- Duplicate!

Both workers now think they own the job, leading to duplicate processing, corrupted results, or conflicts.

### Requirements
| Requirement | Priority | Notes |
|-------------|----------|-------|
| No duplicate processing | Must Have | Each job processed exactly once |
| Works under load | Must Have | 10+ concurrent workers |
| Backend agnostic | Should Have | Pattern works in all backends |

## Decision

**We will implement atomic claim operations using optimistic locking patterns specific to each backend.**

- **Redis**: `WATCH/MULTI/EXEC` pattern
- **Memory**: `asyncio.Lock` held during read-modify-write
- **SQLite**: Single lock per connection (serializes all operations)

The `claim_pending_job()` method atomically:
1. Finds a pending job
2. Verifies it's still pending
3. Updates status to processing
4. Returns the claimed job

If another worker claimed the job between steps 1 and 3, the operation retries with a different job.

## Implementation

### Redis Pattern

```python
async def claim_pending_job(self, job_types):
    for pending_key in pending_keys:
        candidates = await self._client.zrange(pending_key, 0, 0)
        if not candidates:
            continue

        job_id = candidates[0]
        job_key = self._job_key(job_id)

        async with self._client.pipeline(transaction=True) as pipe:
            try:
                # Watch for concurrent modifications
                await pipe.watch(job_key)

                # Verify still pending
                data = await self._client.get(job_key)
                job = self._deserialize_job(data)
                if job.status != JobStatus.PENDING:
                    await pipe.unwatch()
                    continue

                # Atomic update
                job.status = JobStatus.PROCESSING
                pipe.multi()
                pipe.set(job_key, self._serialize_job(job))
                pipe.zrem(pending_key, job_id)
                await pipe.execute()

                return job

            except redis.WatchError:
                # Another worker claimed it, try next
                continue

    return None
```

### Memory Pattern

```python
async def claim_pending_job(self, job_types):
    async with self._lock:  # Single lock for all operations
        pending = [j for j in self._jobs.values()
                   if j.status == JobStatus.PENDING
                   and (job_types is None or j.job_type in job_types)]

        if not pending:
            return None

        # Sort by priority, then creation time
        pending.sort(key=lambda j: (-j.priority.weight, j.created_at))

        job = pending[0]
        job.status = JobStatus.PROCESSING
        self._jobs[job.id] = job

        return job.model_copy()
```

## Consequences

### Positive
- Zero duplicate processing under any load
- Workers can scale horizontally
- No external coordination required

### Negative
- Redis pattern may retry under high contention
- Memory backend serializes all claims (bottleneck)

### Neutral
- SQLite naturally serializes due to single-writer

## Validation Criteria

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| Duplicate claims | 0 | Test with 10 concurrent workers |
| Claims per second | 100+ | Benchmark test |

## Test Case

```python
async def test_claim_is_atomic(backend):
    """Concurrent claims don't result in duplicate processing."""
    for i in range(10):
        await backend.store_job(Job(id=f"job-{i}", job_type="test"))

    claimed_ids = []

    async def claim_worker():
        while True:
            job = await backend.claim_pending_job()
            if job is None:
                break
            claimed_ids.append(job.id)

    await asyncio.gather(*[claim_worker() for _ in range(5)])

    # Each job claimed exactly once
    assert len(claimed_ids) == 10
    assert len(set(claimed_ids)) == 10
```

## Related ADRs

- ADR-F003: Backend Abstraction Layer
- ADR-F004: Redis as Primary Backend

## Decision Record

| Date | Action | By |
|------|--------|-----|
| 2026-02-13 | Proposed | jdobb |
| 2026-02-13 | Accepted | jdobb |
| 2026-02-13 | Implemented | jdobb |
