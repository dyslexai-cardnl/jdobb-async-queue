# ADR-F001: Python Async-First Design

| Field | Value |
|-------|-------|
| Status | Implemented |
| Date | 2026-02-13 |
| Decision Makers | jdobb |
| Supersedes | N/A |

## Context

### Problem Statement
Job queue libraries must handle concurrent operations efficiently - multiple workers claiming jobs, publishers submitting work, and subscribers receiving updates. The design must support high-throughput scenarios without blocking.

### Current State
This is a new library. The patterns are being extracted from `spatial-vision-app` which already uses async Python throughout.

### Requirements
| Requirement | Priority | Notes |
|-------------|----------|-------|
| Non-blocking I/O | Must Have | Workers should not block while waiting |
| Concurrent operations | Must Have | Multiple workers must operate simultaneously |
| Redis/SQLite compatibility | Must Have | Both backends are async-native |
| Python 3.10+ | Must Have | Target modern Python |
| Simple API | Should Have | Async should feel natural, not complex |

## Decision

**We will use async/await for all I/O operations throughout the library.**

All public methods that perform I/O will be async functions:
- `await queue.enqueue(...)` - Store job
- `await queue.claim(...)` - Atomic job claiming
- `await queue.update(...)` - Progress updates
- `async for update in broadcaster.subscribe(...)` - Real-time updates

Internal backend operations are also async, allowing the library to integrate seamlessly with async web frameworks like FastAPI, Starlette, and aiohttp.

## Alternatives Considered

### Option A: Sync-First with Async Wrappers
**Description:** Implement sync versions and provide async wrappers

**Pros:**
- Works in non-async contexts without `asyncio.run()`
- Simpler mental model for sync-only users

**Cons:**
- Async wrappers add overhead
- Can't use async context managers naturally
- Redis async client would still be blocking in sync mode
- Dual API maintenance burden

### Option B: Async-First (Chosen)
**Description:** Native async throughout, users wrap in sync if needed

**Pros:**
- Native performance with async backends
- Clean API without sync/async variants
- Natural integration with async frameworks
- `async for` works elegantly for subscriptions

**Cons:**
- Requires `asyncio.run()` for sync contexts
- Learning curve for async-unfamiliar users

### Option C: Threading-Based Concurrency
**Description:** Use threads instead of async

**Pros:**
- Works with sync code naturally
- No async/await syntax required

**Cons:**
- Thread overhead for many concurrent operations
- GIL limits true parallelism
- Harder to integrate with async frameworks
- More complex resource management

## Comparison Matrix

| Criteria | Weight | Sync+Wrappers | Async-First | Threading |
|----------|--------|---------------|-------------|-----------|
| Performance | High | 3/5 | 5/5 | 3/5 |
| API Simplicity | High | 2/5 | 5/5 | 4/5 |
| Framework Integration | High | 3/5 | 5/5 | 2/5 |
| Maintenance Burden | Medium | 2/5 | 5/5 | 3/5 |
| Learning Curve | Low | 4/5 | 3/5 | 4/5 |
| **Weighted Total** | | 2.7 | **4.8** | 3.1 |

## Consequences

### Positive
- Optimal performance with async Redis and SQLite clients
- Single, clean API surface
- Natural `async for` iteration for subscriptions
- Seamless FastAPI/Starlette integration
- Efficient resource usage under load

### Negative
- Users in sync contexts must use `asyncio.run()`
- Slightly higher learning curve for async beginners
- All calling code must be async-aware

### Neutral
- Requires Python 3.10+ (acceptable for new library)

## Trade-offs

| We Get | We Give Up |
|--------|------------|
| Native async performance | Simple sync usage |
| Clean single API | Dual sync/async support |
| Framework compatibility | Sync-only framework support |

## When to Reconsider

This decision should be revisited if:
- Python introduces significantly better sync/async interop
- A major target framework requires sync-only APIs
- Performance testing shows async overhead outweighs benefits

## Validation Criteria

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| Concurrent claim throughput | 1000+ ops/sec | Benchmark with 10 workers |
| Memory per worker | <10MB | Profile during load test |
| Integration test coverage | 100% async | All tests use pytest-asyncio |

## Implementation Notes

### Pattern Examples

```python
# All public methods are async
class JobQueue:
    async def enqueue(self, ...) -> str: ...
    async def claim(self, ...) -> Job | None: ...
    async def update(self, ...) -> bool: ...
    async def complete(self, ...) -> bool: ...
    async def close(self) -> None: ...

# Subscriptions use async generators
class Broadcaster:
    async def subscribe(self, job_id: str) -> AsyncIterator[JobUpdate]:
        async for update in self.queue.backend.subscribe_updates(job_id):
            yield update

# Workers use async handlers
@worker.handler("task")
async def handle(ctx: JobContext) -> dict:
    await ctx.update(progress=0.5)
    return {"result": "done"}
```

### Code Locations
- `src/jdobb_async_queue/job_queue.py` - All async methods
- `src/jdobb_async_queue/worker.py` - Async worker loop
- `src/jdobb_async_queue/broadcaster.py` - Async subscriptions
- `src/jdobb_async_queue/backends/*.py` - Async backend interfaces

### Dependencies
- `asyncio` (stdlib)
- `redis.asyncio` (Redis backend)
- `aiosqlite` (SQLite backend)

## References

- [PEP 492 - Coroutines with async and await syntax](https://peps.python.org/pep-0492/)
- [Python asyncio documentation](https://docs.python.org/3/library/asyncio.html)
- [redis-py async documentation](https://redis-py.readthedocs.io/en/stable/examples/asyncio_examples.html)

## Related ADRs

- ADR-F003: Backend Abstraction Layer (async interface)
- ADR-F004: Redis as Primary Backend (async Redis client)

## Decision Record

| Date | Action | By |
|------|--------|-----|
| 2026-02-13 | Proposed | jdobb |
| 2026-02-13 | Accepted | jdobb |
| 2026-02-13 | Implemented | jdobb |
