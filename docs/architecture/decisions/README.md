# Architecture Decision Records

This directory contains ADRs documenting the key architectural decisions for `jdobb-async-queue`.

## Structure

```
decisions/
├── ADR_TEMPLATE.md              # Template for new ADRs
├── README.md                    # This file
├── foundational/                # Core, long-lived decisions
│   ├── ADR-F001-python-async-first.md
│   ├── ADR-F002-pydantic-schemas.md
│   ├── ADR-F003-backend-abstraction.md
│   ├── ADR-F004-redis-primary-backend.md
│   └── ADR-F005-structlog-logging.md
├── ADR-001-atomic-job-claiming.md
├── ADR-002-priority-weighted-queuing.md
└── ADR-003-pubsub-broadcasting.md
```

## Index

### Foundational ADRs (Long-lived, technology choices)

| ADR | Title | Status |
|-----|-------|--------|
| [F001](foundational/ADR-F001-python-async-first.md) | Python Async-First Design | Implemented |
| [F002](foundational/ADR-F002-pydantic-schemas.md) | Pydantic for Data Models | Implemented |
| [F003](foundational/ADR-F003-backend-abstraction.md) | Backend Abstraction Layer | Implemented |
| [F004](foundational/ADR-F004-redis-primary-backend.md) | Redis as Primary Backend | Implemented |
| [F005](foundational/ADR-F005-structlog-logging.md) | Structlog for Logging | Implemented |

### Active ADRs (Feature-specific decisions)

| ADR | Title | Status |
|-----|-------|--------|
| [001](ADR-001-atomic-job-claiming.md) | Atomic Job Claiming | Implemented |
| [002](ADR-002-priority-weighted-queuing.md) | Priority-Weighted Queuing | Implemented |
| [003](ADR-003-pubsub-broadcasting.md) | Pub/Sub Broadcasting | Implemented |

## Creating New ADRs

1. Copy `ADR_TEMPLATE.md` to a new file
2. Choose numbering:
   - Foundational: `ADR-FXXX-name.md` (rare, core decisions)
   - Active: `ADR-XXX-name.md` (feature decisions)
3. Fill in all sections
4. Submit for review

## Status Definitions

| Status | Meaning |
|--------|---------|
| Proposed | Under discussion, not yet decided |
| Accepted | Decision made, implementation pending |
| Implemented | Code reflects this decision |
| Deprecated | No longer applies, kept for history |
| Superseded | Replaced by another ADR |
