# Session Context Prompt

This document defines the initial context for AI agent sessions working on `jdobb-async-queue`.

## Initial Prompt

Copy this prompt at the start of a new coding session:

```
I am working on jdobb-async-queue, an async Python job queue library.

Key facts:
- Package: jdobb-async-queue (import as jdobb_async_queue)
- Python: 3.10+
- License: Apache-2.0
- Location: C:\Users\jdobb\shared-libs\async-queue

Core components:
- JobQueue: Main facade for queue operations
- Worker: Polling worker with handler decorators
- Broadcaster: Real-time update subscriptions
- Backends: Memory (testing), Redis (production), SQLite (lightweight)

All methods are async. The library follows these patterns:
- Pydantic v2 for schemas
- structlog for logging
- pytest-asyncio for tests
- TDD: write tests first

Please read the architecture docs before making changes:
- docs/architecture/ARCHITECTURE_OVERVIEW.md
- docs/architecture/decisions/README.md
```

## Standards Summary

### Code Style
- Line length: 100 characters (ruff)
- Formatting: black
- All I/O operations must be async
- Type hints throughout
- No emojis in code/comments

### Testing
- TDD cycle: RED -> GREEN -> REFACTOR
- Coverage targets: 95% core, 90% backends
- Use memory backend for unit tests
- Integration tests in tests/integration/

### Commits
Format: `type(scope): description`

Examples:
- `feat(worker): add max_concurrent option`
- `fix(redis): handle WatchError in claim`
- `test(sqlite): add TTL expiration test`
- `docs(adr): add ADR-004 for retry logic`

Co-author tag:
```
Co-Authored-By: Claude <noreply@anthropic.com>
```

### ADR Creation
When making architectural decisions:
1. Copy `docs/architecture/decisions/ADR_TEMPLATE.md`
2. Fill all sections (especially alternatives and trade-offs)
3. Update index in `docs/architecture/decisions/README.md`
4. Foundational (F-series) for core tech, numbered for features

### License Compliance
Allowed: Apache-2.0, MIT, BSD, ISC, CC0
Blocked: GPL, AGPL, CC-BY-NC, SSPL

## Follow-up Prompts

### Before coding
```
Before making changes, please:
1. Read the relevant architecture docs
2. Check existing tests for the area
3. Confirm the approach with me
```

### After completing a task
```
Please verify:
1. All tests pass: python -m pytest tests/ -v
2. Linting passes: python -m black --check src/ tests/ && python -m ruff check src/ tests/
3. New code has tests
```

## Key Files

| File | Purpose |
|------|---------|
| `src/jdobb_async_queue/__init__.py` | Public exports |
| `src/jdobb_async_queue/schemas.py` | Pydantic models |
| `src/jdobb_async_queue/job_queue.py` | Main facade |
| `src/jdobb_async_queue/worker.py` | Worker implementation |
| `src/jdobb_async_queue/broadcaster.py` | Real-time updates |
| `src/jdobb_async_queue/backends/base.py` | Abstract interface |
| `tests/conftest.py` | Shared fixtures |
| `pyproject.toml` | Project config |

## Architecture Quick Reference

```
JobQueue (facade)
    |
    +-- enqueue() -> store in backend
    +-- claim() -> atomic claim from backend
    +-- update/complete/fail() -> update + publish
    |
    v
QueueBackend (abstract)
    |
    +-- MemoryBackend (asyncio.Lock)
    +-- RedisBackend (WATCH/MULTI/EXEC)
    +-- SQLiteBackend (single lock)
```

---

**Update When:** Project structure changes or new standards adopted.
