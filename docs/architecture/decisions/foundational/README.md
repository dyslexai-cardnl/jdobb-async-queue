# Foundational Architecture Decision Records

This directory contains **foundational ADRs** - core technology and design decisions that define the fundamental architecture of `jdobb-async-queue`. These decisions are expected to remain stable for years and changing them would require significant refactoring.

## Index

| ADR | Title | Status | Summary |
|-----|-------|--------|---------|
| [ADR-F001](ADR-F001-python-async-first.md) | Python Async-First Design | Implemented | All I/O operations use async/await |
| [ADR-F002](ADR-F002-pydantic-schemas.md) | Pydantic for Data Models | Implemented | Use Pydantic v2 for all job schemas |
| [ADR-F003](ADR-F003-backend-abstraction.md) | Backend Abstraction Layer | Implemented | Abstract interface for storage backends |
| [ADR-F004](ADR-F004-redis-primary-backend.md) | Redis as Primary Backend | Implemented | Redis for production, memory for testing |
| [ADR-F005](ADR-F005-structlog-logging.md) | Structlog for Logging | Implemented | Structured logging throughout |

## Relationship to Active ADRs

Foundational ADRs (F-series) establish the unchanging core:
- Technology stack choices
- Architectural patterns
- Design principles

Active ADRs (numbered series) build on this foundation:
- Feature implementations
- Behavioral decisions
- Optimization strategies

## Stability Expectations

| Category | Expected Lifetime | Change Process |
|----------|-------------------|----------------|
| Foundational | 3-5 years | Requires major version bump |
| Active | 6-18 months | Standard ADR process |

## When to Create a Foundational ADR

Create a foundational ADR when:
1. Choosing a core technology (language, framework, database)
2. Establishing a design pattern used throughout the codebase
3. Making a decision that would require rewriting >50% of code to change

## Update Policy

Foundational ADRs should only be updated to:
- Fix typos or clarify wording
- Add implementation notes after the fact
- Mark as superseded when replaced

**Never** change the decision or rationale of an implemented foundational ADR. Create a new ADR that supersedes it instead.
