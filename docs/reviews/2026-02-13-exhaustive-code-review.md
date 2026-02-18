# Exhaustive Code Review - async-queue

- Date: 2026-02-13
- Reviewer: Codex (GPT-5)
- Scope: `src/`, `tests/`, and architecture/API docs
- Runtime checks executed:
  - `python -m pytest -q` -> 116 passed, 17 skipped
  - `python -m pytest --cov=src/jdobb_async_queue --cov-report=term-missing -q` -> 77% total (Redis backend 0% in this run)
  - `python -m ruff check .` -> passed
  - `python -m black --check .` -> passed

## Findings (ordered by severity)

### HIGH - AQ-CR-001 - `subscribe_with_timeout()` does not enforce timeout
- Files: `src/jdobb_async_queue/broadcaster.py:105`, `src/jdobb_async_queue/broadcaster.py:127`
- Problem: The method documents timeout behavior but only proxies `subscribe_updates()` and never applies `timeout`.
- Impact: Subscribers can hang indefinitely despite passing a timeout value; this breaks API contract and can stall request handlers.
- Evidence:
  - Static: no `asyncio.wait_for()` or equivalent in method body.
  - Runtime repro: `subscribe_with_timeout(timeout=0.05)` yielded first update after ~0.201s when update was delayed.
- Recommendation: Apply timeout per update wait (for example using `asyncio.wait_for(anext(...), timeout=timeout)` inside generator logic) and add tests for timeout and terminal states.

### HIGH - AQ-CR-002 - Terminal job states can be overwritten by later operations
- Files: `src/jdobb_async_queue/job_queue.py:224`, `src/jdobb_async_queue/job_queue.py:228`, `src/jdobb_async_queue/job_queue.py:257`, `src/jdobb_async_queue/job_queue.py:261`
- Problem: `complete()` and `fail()` do not guard against terminal states (`complete`, `failed`, `cancelled`) and will overwrite existing outcomes.
- Impact: Race conditions (for example cancellation during processing) can produce incorrect final state and audit trail corruption.
- Evidence:
  - Runtime repro: a cancelled job was later marked complete; `complete()` returned `True` and final status became `COMPLETE`.
- Recommendation: Enforce an explicit state transition matrix and reject invalid transitions (`False` or domain-specific exception).

### HIGH - AQ-CR-003 - Redis claim path does not honor global priority across job types
- Files: `src/jdobb_async_queue/backends/redis.py:136`, `src/jdobb_async_queue/backends/redis.py:149`, `src/jdobb_async_queue/backends/redis.py:151`
- Problem: Claim logic iterates pending sets per job type and claims from the first non-empty set; it does not compare top candidates globally.
- Impact: Lower-priority jobs from one type can be claimed before higher-priority jobs from another type, violating advertised priority behavior.
- Evidence:
  - Static: no cross-set score comparison before choosing `job_id`.
- Recommendation: Use a global pending index (single ZSET) or fetch head candidate from each set and choose lowest score globally.

### HIGH - AQ-CR-004 - Redis pending ZSETs can accumulate stale IDs after TTL expiry
- Files: `src/jdobb_async_queue/backends/redis.py:69`, `src/jdobb_async_queue/backends/redis.py:77`, `src/jdobb_async_queue/backends/redis.py:165`
- Problem: Jobs with TTL are added to pending ZSETs, but when the job key expires `claim_pending_job()` just `continue`s when `data is None`; stale IDs are not removed.
- Impact: Unbounded growth of pending sets, extra claim latency, and wasted Redis CPU over time.
- Evidence:
  - Static: no `zrem` in the `data is None` branch.
- Recommendation: Remove stale IDs on miss (`zrem`) and add periodic reconciliation job or Lua-based atomic cleanup.

### MEDIUM - AQ-CR-005 - Progress bounds are documented but not enforced during updates
- Files: `src/jdobb_async_queue/schemas.py:51`, `src/jdobb_async_queue/job_queue.py:193`
- Problem: `Job.progress` has schema bounds, but assignment after fetch is not validated; `update()` can persist values outside `[0.0, 1.0]`.
- Impact: Invalid progress values can break clients/UI assumptions and analytics.
- Evidence:
  - Runtime repro: `queue.update(progress=1.75)` succeeded and stored `1.75`.
- Recommendation: Validate in `JobQueue.update()` (explicit bounds check) or enable assignment validation on models.

### MEDIUM - AQ-CR-006 - Duplicate `job_id` behavior is backend-inconsistent
- Files: `src/jdobb_async_queue/backends/memory.py:26`, `src/jdobb_async_queue/backends/redis.py:72`, `src/jdobb_async_queue/backends/sqlite.py:165`
- Problem: Memory and Redis overwrite existing IDs silently; SQLite raises `IntegrityError`.
- Impact: Behavior changes by backend and may cause silent data loss or backend-specific failures during migration.
- Evidence:
  - Runtime repro: duplicate ID overwrote payload in memory; same operation raised `IntegrityError` in SQLite.
- Recommendation: Define one contract for duplicate IDs (reject or upsert) and enforce it uniformly.

### MEDIUM - AQ-CR-007 - SQLite URL parsing breaks Unix absolute paths
- Files: `src/jdobb_async_queue/backends/sqlite.py:54`, `src/jdobb_async_queue/backends/sqlite.py:55`
- Problem: `_parse_url()` strips leading slash from any path, turning Unix absolute paths into relative paths.
- Impact: Database file may be created/read in unintended location on Unix-like systems.
- Recommendation: Keep leading slash for Unix absolute paths; only normalize Windows drive-prefixed forms.

### MEDIUM - AQ-CR-008 - SQLite claim path can return a job without confirming the status update succeeded
- Files: `src/jdobb_async_queue/backends/sqlite.py:279`, `src/jdobb_async_queue/backends/sqlite.py:288`
- Problem: `claim_pending_job()` does `SELECT` then conditional `UPDATE ... WHERE status='pending'`, but does not check affected row count before returning the selected job.
- Impact: Under multi-connection contention, a stale claimant can return a job it did not actually claim (duplicate processing risk).
- Evidence:
  - Static inference from code path; not deterministically reproduced in this run.
- Recommendation: Check update rowcount and retry when zero; consider transaction strategy (`BEGIN IMMEDIATE`) for stronger claim semantics.

## Test and Coverage Gaps

### MEDIUM - AQ-CR-009 - Redis backend correctness is not exercised in this environment
- Files: `src/jdobb_async_queue/backends/redis.py`
- Gap: Coverage run reported Redis backend at 0% with 17 skipped tests (environment-dependent skips).
- Impact: Production backend risks can ship undetected.
- Recommendation: Add CI job with Redis service container and require Redis test suite + coverage gate.

### LOW - AQ-CR-010 - `subscribe_with_timeout()` lacks direct tests
- Files: `src/jdobb_async_queue/broadcaster.py:105`, `tests/test_broadcaster.py`
- Gap: Timeout branch/behavior is untested; method regression escaped existing tests.
- Recommendation: Add tests for timeout enforcement and timeout reset after each received update.

## Overall Risk Summary
- High: 4
- Medium: 5
- Low: 1

Most critical items are API-contract correctness (`subscribe_with_timeout`), lifecycle integrity (terminal-state overwrites), and Redis queue correctness/performance in production paths.