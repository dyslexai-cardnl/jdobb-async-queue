# ADR-002: Priority-Weighted Queuing

| Field | Value |
|-------|-------|
| Status | Implemented |
| Date | 2026-02-13 |
| Decision Makers | jdobb |
| Supersedes | N/A |

## Context

### Problem Statement
Not all jobs are equally urgent. Some use cases require:
- Urgent jobs processed immediately (user-facing requests)
- Normal jobs processed in order (background tasks)
- Low-priority jobs processed when idle (maintenance)

A simple FIFO queue treats all jobs equally, causing urgent jobs to wait behind less important work.

### Requirements
| Requirement | Priority | Notes |
|-------------|----------|-------|
| Priority levels | Must Have | At least 3 levels |
| FIFO within priority | Must Have | Same-priority jobs in order |
| Simple API | Should Have | Easy to specify priority |

## Decision

**We will implement three priority levels (HIGH, NORMAL, LOW) with weighted scoring.**

Priority weights:
- HIGH: 10
- NORMAL: 5
- LOW: 1

Jobs are claimed in order of:
1. Highest priority weight (descending)
2. Creation time (ascending, FIFO within priority)

### Scoring Formula

For Redis sorted sets:
```
score = -priority_weight * 1e12 + timestamp
```

The large multiplier ensures priority always dominates over time. Lower scores are claimed first.

Example scores:
- HIGH job at t=1000: -10e12 + 1000 = -9999999999000
- NORMAL job at t=500: -5e12 + 500 = -4999999999500
- LOW job at t=100: -1e12 + 100 = -999999999900

HIGH job is claimed first despite being created last.

## Implementation

### Enqueue with Priority

```python
job = await queue.enqueue(
    "process",
    data={"input": "urgent"},
    priority=JobPriority.HIGH
)
```

### Claim by Priority Order

```python
# Memory backend sorting
pending.sort(key=lambda j: (-j.priority.weight, j.created_at))

# Redis uses sorted set scores calculated at store time
score = -job.priority.weight * 1e12 + job.created_at.timestamp()
await self._client.zadd(pending_key, {job.id: score})
```

## Consequences

### Positive
- Urgent jobs processed first
- Starvation-resistant (old low-priority jobs eventually processed)
- Simple three-level model easy to understand

### Negative
- Three levels may be limiting for some use cases
- LOW priority jobs wait indefinitely under constant HIGH load

### Neutral
- Weight values (1, 5, 10) are arbitrary but effective

## Trade-offs

| We Get | We Give Up |
|--------|------------|
| Priority handling | Pure FIFO simplicity |
| Urgent job response | Strict ordering guarantees |

## When to Reconsider

- If three levels prove insufficient
- If starvation becomes a problem in production

## Related ADRs

- ADR-001: Atomic Job Claiming (priority affects claim order)
- ADR-F002: Pydantic Schemas (JobPriority enum)

## Decision Record

| Date | Action | By |
|------|--------|-----|
| 2026-02-13 | Proposed | jdobb |
| 2026-02-13 | Accepted | jdobb |
| 2026-02-13 | Implemented | jdobb |
