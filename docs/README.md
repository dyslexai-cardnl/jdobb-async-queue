# Documentation Index

Welcome to the `jdobb-async-queue` documentation.

## Quick Links

| Document | Description |
|----------|-------------|
| [Quick Start](guides/QUICK_START.md) | Get running in 5 minutes |
| [API Reference](api/API_REFERENCE.md) | Complete API documentation |
| [Architecture Overview](architecture/ARCHITECTURE_OVERVIEW.md) | How the library works |
| [Development Setup](guides/DEVELOPMENT_SETUP.md) | Contributing guide |

## Documentation Structure

```
docs/
├── README.md                    # This file
├── SESSION_CONTEXT_PROMPT.md    # AI agent session setup
│
├── api/
│   └── API_REFERENCE.md         # Full API documentation
│
├── architecture/
│   ├── ARCHITECTURE_OVERVIEW.md # System design
│   └── decisions/               # Architecture Decision Records
│       ├── README.md            # ADR index
│       ├── ADR_TEMPLATE.md      # Template for new ADRs
│       ├── foundational/        # Core technology decisions
│       │   ├── ADR-F001-python-async-first.md
│       │   ├── ADR-F002-pydantic-schemas.md
│       │   ├── ADR-F003-backend-abstraction.md
│       │   ├── ADR-F004-redis-primary-backend.md
│       │   └── ADR-F005-structlog-logging.md
│       ├── ADR-001-atomic-job-claiming.md
│       ├── ADR-002-priority-weighted-queuing.md
│       └── ADR-003-pubsub-broadcasting.md
│
├── guides/
│   ├── QUICK_START.md           # 5-minute tutorial
│   └── DEVELOPMENT_SETUP.md     # Dev environment setup
│
└── implementation/
    └── IMPLEMENTATION_CHECKLIST.md  # Build record
```

## For New Users

1. **Install**: `pip install jdobb-async-queue[all]`
2. **Read**: [Quick Start Guide](guides/QUICK_START.md)
3. **Reference**: [API Documentation](api/API_REFERENCE.md)

## For Contributors

1. **Setup**: [Development Setup](guides/DEVELOPMENT_SETUP.md)
2. **Understand**: [Architecture Overview](architecture/ARCHITECTURE_OVERVIEW.md)
3. **Decisions**: [ADR Index](architecture/decisions/README.md)

## For AI Agents

1. **Context**: [Session Context Prompt](SESSION_CONTEXT_PROMPT.md)
2. **Integration**: [SETUP.md](../SETUP.md) (machine-readable section)

## Key Concepts

### Components

| Component | Purpose | Example |
|-----------|---------|---------|
| `JobQueue` | Central facade | `queue = JobQueue(backend="redis")` |
| `Worker` | Process jobs | `@worker.handler("task")` |
| `Broadcaster` | Real-time updates | `async for update in broadcaster.subscribe(id)` |

### Job Lifecycle

```
PENDING -> PROCESSING -> COMPLETE
              |
              +-------> FAILED
              +-------> CANCELLED
```

### Priority Order

```
HIGH (10) > NORMAL (5) > LOW (1)
```

Within same priority: FIFO (oldest first)

### Backend Selection

| Scenario | Backend |
|----------|---------|
| Testing | `memory` |
| Production (distributed) | `redis` |
| Production (single-node) | `sqlite` |

---

**Update When:** New documentation added or structure changes.
