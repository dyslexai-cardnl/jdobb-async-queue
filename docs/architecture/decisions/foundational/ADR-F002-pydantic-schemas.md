# ADR-F002: Pydantic for Data Models

| Field | Value |
|-------|-------|
| Status | Implemented |
| Date | 2026-02-13 |
| Decision Makers | jdobb |
| Supersedes | N/A |

## Context

### Problem Statement
Job queue systems require well-defined data structures for jobs, updates, and status tracking. These structures must support serialization to JSON (for Redis storage), validation of inputs, and type safety for developers.

### Current State
The `spatial-vision-app` uses Pydantic models throughout for request/response schemas. This library extracts and generalizes that pattern.

### Requirements
| Requirement | Priority | Notes |
|-------------|----------|-------|
| JSON serialization | Must Have | Redis stores jobs as JSON strings |
| Input validation | Must Have | Reject invalid job data early |
| Type safety | Must Have | IDE autocomplete, static analysis |
| Python 3.10+ compatibility | Must Have | Use modern type hints |
| Default values | Should Have | Jobs should have sensible defaults |
| Immutability options | Nice to Have | Some models should be frozen |

## Decision

**We will use Pydantic v2 for all data models (Job, JobStatus, JobPriority, JobUpdate).**

Pydantic provides:
- Automatic JSON serialization via `model_dump_json()`
- Automatic JSON deserialization via `model_validate_json()`
- Runtime validation with clear error messages
- Type-safe field access
- Default values and factories
- Enum support for status/priority

## Alternatives Considered

### Option A: Dataclasses
**Description:** Use stdlib `dataclasses` with manual JSON handling

**Pros:**
- No external dependency
- Simple, familiar API
- Lightweight

**Cons:**
- No built-in validation
- Manual JSON serialization code
- No native enum serialization
- No constraint validation (e.g., `progress >= 0`)

### Option B: Pydantic v2 (Chosen)
**Description:** Use Pydantic for schemas with validation

**Pros:**
- Built-in JSON serialization
- Runtime validation
- Constraint support (`ge=0.0, le=1.0`)
- Excellent IDE support
- Industry standard

**Cons:**
- External dependency
- Slightly slower than raw dataclasses
- Learning curve for Pydantic-specific features

### Option C: attrs + cattrs
**Description:** Use attrs for classes and cattrs for serialization

**Pros:**
- Fast
- Flexible
- Good validation via attrs validators

**Cons:**
- Two dependencies instead of one
- Less common, smaller community
- More verbose for JSON handling

### Option D: TypedDict
**Description:** Use TypedDict for type hints without runtime validation

**Pros:**
- No dependencies
- Pure type hints
- Very lightweight

**Cons:**
- No runtime validation at all
- No default values
- No serialization helpers
- Easy to create invalid data

## Comparison Matrix

| Criteria | Weight | Dataclasses | Pydantic | attrs+cattrs | TypedDict |
|----------|--------|-------------|----------|--------------|-----------|
| JSON Support | High | 2/5 | 5/5 | 4/5 | 1/5 |
| Validation | High | 1/5 | 5/5 | 4/5 | 1/5 |
| Type Safety | High | 4/5 | 5/5 | 4/5 | 4/5 |
| Constraints | Medium | 1/5 | 5/5 | 4/5 | 1/5 |
| Dependencies | Low | 5/5 | 3/5 | 3/5 | 5/5 |
| **Weighted Total** | | 2.4 | **4.8** | 4.0 | 2.2 |

## Consequences

### Positive
- Jobs are validated on creation - invalid data fails fast
- JSON serialization is one method call
- Progress field constrained to 0.0-1.0 automatically
- Enums serialize to strings naturally
- Excellent IDE autocomplete and type checking

### Negative
- Pydantic v2 is a required dependency
- Slight runtime overhead vs raw dicts
- Pydantic-specific learning curve

### Neutral
- Models are mutable by default (can be frozen if needed)

## Trade-offs

| We Get | We Give Up |
|--------|------------|
| Automatic validation | Zero dependencies |
| Built-in JSON support | Maximum performance |
| Type safety | Simplicity of plain dicts |

## When to Reconsider

This decision should be revisited if:
- Pydantic v3 introduces breaking changes
- A stdlib solution provides equivalent features
- Performance profiling shows Pydantic as bottleneck

## Validation Criteria

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| Invalid job rejection | 100% | Unit tests with bad data |
| JSON round-trip fidelity | 100% | Serialize/deserialize tests |
| Type coverage | 100% | mypy/pyright checks |

## Implementation Notes

### Schema Definitions

```python
class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"

class JobPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"

class Job(BaseModel):
    id: str
    job_type: str
    data: dict[str, Any] = Field(default_factory=dict)
    status: JobStatus = Field(default=JobStatus.PENDING)
    priority: JobPriority = Field(default=JobPriority.NORMAL)
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    # ... additional fields
```

### Serialization Patterns

```python
# Serialize to JSON for storage
json_str = job.model_dump_json()

# Deserialize from JSON
job = Job.model_validate_json(json_str)

# Serialize to dict
data = job.model_dump()
```

### Code Locations
- `src/jdobb_async_queue/schemas.py` - All Pydantic models

### Dependencies
- `pydantic>=2.0`

## References

- [Pydantic v2 Documentation](https://docs.pydantic.dev/latest/)
- [Pydantic Migration Guide v1 to v2](https://docs.pydantic.dev/latest/migration/)

## Related ADRs

- ADR-F001: Python Async-First (schemas used in async methods)
- ADR-F003: Backend Abstraction (backends serialize via Pydantic)

## Decision Record

| Date | Action | By |
|------|--------|-----|
| 2026-02-13 | Proposed | jdobb |
| 2026-02-13 | Accepted | jdobb |
| 2026-02-13 | Implemented | jdobb |
