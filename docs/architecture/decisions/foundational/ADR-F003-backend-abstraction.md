# ADR-F003: Backend Abstraction Layer

| Field | Value |
|-------|-------|
| Status | Implemented |
| Date | 2026-02-13 |
| Decision Makers | jdobb |
| Supersedes | N/A |

## Context

### Problem Statement
The job queue must support multiple storage backends:
- **Redis** for production (distributed, persistent, pub/sub native)
- **Memory** for testing (fast, no external dependencies)
- **SQLite** for lightweight deployments (persistent, single-file)

Without abstraction, the `JobQueue` class would need backend-specific code paths, making it harder to maintain and extend.

### Current State
The `spatial-vision-app` has Redis-specific code in `job_manager.py`. This library extracts and generalizes those patterns behind an abstract interface.

### Requirements
| Requirement | Priority | Notes |
|-------------|----------|-------|
| Multiple backends | Must Have | Redis, Memory, SQLite |
| Consistent API | Must Have | Same methods across backends |
| Backend-specific optimizations | Should Have | WATCH/MULTI/EXEC for Redis |
| Easy to add new backends | Should Have | Clear interface contract |
| Type safety | Must Have | Abstract base class with type hints |

## Decision

**We will define an abstract `QueueBackend` class that all backends must implement.**

The abstract interface defines:
- `store_job(job)` - Persist a job
- `get_job(job_id)` - Retrieve by ID
- `update_job(job)` - Modify existing job
- `delete_job(job_id)` - Remove a job
- `claim_pending_job(job_types)` - Atomic claim operation
- `publish_update(update)` - Send real-time notification
- `subscribe_updates(job_id)` - Receive real-time notifications
- `close()` - Cleanup resources

`JobQueue` depends only on this interface, not on concrete implementations.

## Alternatives Considered

### Option A: Duck Typing
**Description:** No formal interface, rely on method names matching

**Pros:**
- Pythonic, flexible
- No base class required

**Cons:**
- No IDE autocomplete for implementers
- No type checking for missing methods
- Easy to have subtle incompatibilities

### Option B: Abstract Base Class (Chosen)
**Description:** Formal ABC with abstract methods

**Pros:**
- Type checker catches missing implementations
- IDE shows required methods
- Clear contract documentation
- Runtime error if abstract method not implemented

**Cons:**
- Slightly more verbose
- Inheritance required

### Option C: Protocol (Structural Subtyping)
**Description:** Use `typing.Protocol` for interface

**Pros:**
- No inheritance required
- Structural typing - any matching class works
- Modern Python pattern

**Cons:**
- Less clear to implementers what's required
- No runtime enforcement
- Newer pattern, less familiar

## Comparison Matrix

| Criteria | Weight | Duck Typing | ABC | Protocol |
|----------|--------|-------------|-----|----------|
| Type Safety | High | 2/5 | 5/5 | 4/5 |
| Discoverability | High | 2/5 | 5/5 | 3/5 |
| Flexibility | Medium | 5/5 | 3/5 | 5/5 |
| Runtime Safety | Medium | 2/5 | 5/5 | 2/5 |
| Familiarity | Low | 4/5 | 5/5 | 3/5 |
| **Weighted Total** | | 2.8 | **4.6** | 3.4 |

## Consequences

### Positive
- Clear contract for backend implementers
- `JobQueue` is testable with mock backends
- New backends can be added without modifying core
- Type checkers catch implementation errors
- IDE provides autocomplete for required methods

### Negative
- Backends must inherit from ABC
- Some method signatures are more complex than needed for simple backends

### Neutral
- Memory backend shows minimal implementation example

## Trade-offs

| We Get | We Give Up |
|--------|------------|
| Type safety | Duck typing flexibility |
| Clear contracts | Implicit interface patterns |
| IDE support | Minimal boilerplate |

## When to Reconsider

This decision should be revisited if:
- Python Protocols become the dominant pattern
- The interface needs to support backends with fundamentally different capabilities
- Performance profiling shows method dispatch overhead

## Validation Criteria

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| Backend test coverage | 90%+ each | pytest-cov per backend |
| Interface completeness | 100% | All backends implement all methods |
| Substitutability | 100% | Same tests pass with any backend |

## Implementation Notes

### Abstract Interface

```python
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

class QueueBackend(ABC):
    @abstractmethod
    async def store_job(self, job: Job) -> None: ...

    @abstractmethod
    async def get_job(self, job_id: str) -> Job | None: ...

    @abstractmethod
    async def update_job(self, job: Job) -> None: ...

    @abstractmethod
    async def delete_job(self, job_id: str) -> bool: ...

    @abstractmethod
    async def claim_pending_job(
        self, job_types: list[str] | None = None
    ) -> Job | None: ...

    @abstractmethod
    async def publish_update(self, update: JobUpdate) -> None: ...

    @abstractmethod
    def subscribe_updates(self, job_id: str) -> AsyncIterator[JobUpdate]: ...

    @abstractmethod
    async def close(self) -> None: ...
```

### Backend Selection in JobQueue

```python
class JobQueue:
    def __init__(self, backend: QueueBackend | str = "memory", ...):
        if isinstance(backend, QueueBackend):
            self._backend = backend
        elif backend == "memory":
            self._backend = MemoryBackend()
        elif backend == "redis":
            from .backends.redis import RedisBackend
            self._backend = RedisBackend(url=url, namespace=namespace)
        elif backend == "sqlite":
            from .backends.sqlite import SQLiteBackend
            self._backend = SQLiteBackend(url=url)
```

### Code Locations
- `src/jdobb_async_queue/backends/base.py` - Abstract interface
- `src/jdobb_async_queue/backends/memory.py` - Memory implementation
- `src/jdobb_async_queue/backends/redis.py` - Redis implementation
- `src/jdobb_async_queue/backends/sqlite.py` - SQLite implementation

### Dependencies
- None for interface
- Backend-specific dependencies are optional

## References

- [Python ABC Documentation](https://docs.python.org/3/library/abc.html)
- [Dependency Inversion Principle](https://en.wikipedia.org/wiki/Dependency_inversion_principle)

## Related ADRs

- ADR-F001: Python Async-First (async methods in interface)
- ADR-F004: Redis as Primary Backend (primary implementation)
- ADR-001: Atomic Job Claiming (key interface method)

## Decision Record

| Date | Action | By |
|------|--------|-----|
| 2026-02-13 | Proposed | jdobb |
| 2026-02-13 | Accepted | jdobb |
| 2026-02-13 | Implemented | jdobb |
