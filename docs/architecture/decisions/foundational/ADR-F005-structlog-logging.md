# ADR-F005: Structlog for Logging

| Field | Value |
|-------|-------|
| Status | Implemented |
| Date | 2026-02-13 |
| Decision Makers | jdobb |
| Supersedes | N/A |

## Context

### Problem Statement
Job queue operations need logging for:
- Debugging issues (job stuck, worker crash)
- Monitoring throughput (jobs/second)
- Auditing (who submitted what job)
- Alerting (failures, queue backlog)

Logs should be structured for easy parsing by log aggregation tools (Datadog, CloudWatch, ELK).

### Current State
The `spatial-vision-app` uses structlog throughout. This library follows the same pattern for consistency.

### Requirements
| Requirement | Priority | Notes |
|-------------|----------|-------|
| Structured output | Must Have | JSON-parseable logs |
| Context binding | Must Have | job_id, worker_id in all logs |
| Performance | Should Have | Minimal overhead |
| stdlib compatibility | Should Have | Works with logging module |
| Human-readable dev mode | Nice to Have | Pretty output for development |

## Decision

**We will use structlog for all logging with bound context (job_id, job_type).**

Structlog provides:
- Structured key-value logging
- Context binding (attach job_id once, included in all logs)
- JSON output for production
- Human-readable output for development
- Integration with stdlib logging

## Alternatives Considered

### Option A: stdlib logging
**Description:** Use Python's built-in logging module

**Pros:**
- No dependencies
- Familiar API
- Works everywhere

**Cons:**
- String formatting only
- No native structured output
- Context binding requires manual work

### Option B: structlog (Chosen)
**Description:** Structured logging library

**Pros:**
- Native structured output
- Context binding built-in
- JSON/console output modes
- Integrates with stdlib

**Cons:**
- External dependency
- Different API from stdlib

### Option C: loguru
**Description:** Modern logging library

**Pros:**
- Simple API
- Colored output
- Automatic rotation

**Cons:**
- Less structured output focus
- Different API than team standard
- Less JSON ecosystem integration

## Comparison Matrix

| Criteria | Weight | stdlib | structlog | loguru |
|----------|--------|--------|-----------|--------|
| Structured Output | High | 2/5 | 5/5 | 3/5 |
| Context Binding | High | 2/5 | 5/5 | 3/5 |
| Performance | Medium | 4/5 | 4/5 | 4/5 |
| Dependencies | Low | 5/5 | 3/5 | 3/5 |
| Familiarity | Low | 5/5 | 4/5 | 3/5 |
| **Weighted Total** | | 3.0 | **4.5** | 3.3 |

## Consequences

### Positive
- Logs are machine-parseable
- Job context automatically included
- Easy integration with log aggregators
- Consistent with spatial-vision-app

### Negative
- structlog is a dependency
- Slightly different API than stdlib

### Neutral
- Can be configured to output to stdlib handlers

## Trade-offs

| We Get | We Give Up |
|--------|------------|
| Structured logs | Zero dependencies |
| Context binding | stdlib familiarity |
| JSON output | Simplicity |

## When to Reconsider

This decision should be revisited if:
- A new stdlib PEP adds structured logging
- Performance profiling shows logging overhead
- Team standardizes on different library

## Validation Criteria

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| JSON parseability | 100% | Parse all log output |
| Context presence | 100% | job_id in relevant logs |
| Performance impact | <1% | Profile with/without logging |

## Implementation Notes

### Logger Setup

```python
import structlog

logger = structlog.get_logger()

# In JobQueue methods
logger.info("Job enqueued", job_id=job.id, job_type=job_type)
logger.debug("Job claimed", job_id=job.id, worker="worker-1")
logger.warning("Job failed", job_id=job.id, error=str(e))
```

### Bound Context Pattern

```python
# Bind context once
log = logger.bind(job_id=job.id, job_type=job.job_type)

# All subsequent logs include context
log.info("Processing started")
log.debug("Step 1 complete", step="validation")
log.info("Processing complete", duration_ms=150)
```

### Production Configuration

```python
import structlog

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.BoundLogger,
    cache_logger_on_first_use=True,
)
```

### Code Locations
- All source files import and use structlog
- Configuration left to consuming application

### Dependencies
- `structlog>=23.0`

## References

- [structlog documentation](https://www.structlog.org/)
- [Structured Logging Best Practices](https://www.structlog.org/en/stable/why.html)

## Related ADRs

- None directly related

## Decision Record

| Date | Action | By |
|------|--------|-----|
| 2026-02-13 | Proposed | jdobb |
| 2026-02-13 | Accepted | jdobb |
| 2026-02-13 | Implemented | jdobb |
