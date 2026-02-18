# Development Setup Guide

This guide covers setting up a development environment for `jdobb-async-queue`.

## Prerequisites

- Python 3.10 or higher
- pip (Python package manager)
- Git
- Redis (optional, for Redis backend testing)

## Quick Start

```bash
# Clone the repository
git clone <repository-url>
cd async-queue

# Create virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# or
.venv\Scripts\activate     # Windows

# Install with all dependencies
pip install -e ".[all,dev]"

# Run tests
python -m pytest tests/ -v

# Verify installation
python -c "from jdobb_async_queue import JobQueue, Job, Worker, Broadcaster; print('OK')"
```

## Installation Options

### Minimal (Memory backend only)
```bash
pip install -e .
```

### With Redis backend
```bash
pip install -e ".[redis]"
```

### With SQLite backend
```bash
pip install -e ".[sqlite]"
```

### With all backends
```bash
pip install -e ".[all]"
```

### With development tools
```bash
pip install -e ".[all,dev]"
```

## Running Tests

### All tests (except integration)
```bash
python -m pytest tests/ -v --ignore=tests/integration
```

### Integration tests only
```bash
python -m pytest tests/integration/ -v
```

### With coverage report
```bash
python -m pytest tests/ --cov=jdobb_async_queue --cov-report=term-missing
```

### Specific test file
```bash
python -m pytest tests/test_job_queue.py -v
```

### Specific test
```bash
python -m pytest tests/test_job_queue.py::TestJobQueueEnqueue::test_enqueue_returns_job_id -v
```

## Redis Setup (Optional)

### Using Docker
```bash
docker run -d --name redis -p 6379:6379 redis:7
```

### Using local installation
Follow Redis installation guide for your OS.

### Running Redis tests
```bash
# Ensure Redis is running
redis-cli ping  # Should return PONG

# Run Redis tests
python -m pytest tests/test_backends/test_redis.py -v

# Or run all tests (Redis tests auto-skip if unavailable)
python -m pytest tests/ -v
```

## Linting

### Check formatting
```bash
python -m black --check src/ tests/
```

### Auto-format
```bash
python -m black src/ tests/
```

### Run ruff
```bash
python -m ruff check src/ tests/
```

### Auto-fix ruff issues
```bash
python -m ruff check src/ tests/ --fix
```

## Project Structure

```
async-queue/
├── src/jdobb_async_queue/      # Source code
│   ├── __init__.py             # Public exports
│   ├── schemas.py              # Pydantic models
│   ├── job_queue.py            # Main JobQueue class
│   ├── worker.py               # Worker implementation
│   ├── broadcaster.py          # Real-time updates
│   └── backends/               # Storage backends
│       ├── base.py             # Abstract interface
│       ├── memory.py           # In-memory (testing)
│       ├── redis.py            # Redis (production)
│       └── sqlite.py           # SQLite (lightweight)
├── tests/                      # Test suite
│   ├── conftest.py             # Shared fixtures
│   ├── test_*.py               # Unit tests
│   ├── test_backends/          # Backend-specific tests
│   └── integration/            # End-to-end tests
├── docs/                       # Documentation
│   ├── architecture/           # Architecture docs + ADRs
│   ├── guides/                 # How-to guides
│   └── implementation/         # Implementation records
├── pyproject.toml              # Project configuration
└── README.md                   # Project overview
```

## Common Tasks

### Adding a new backend
1. Create `src/jdobb_async_queue/backends/mybackend.py`
2. Implement all methods from `QueueBackend` abstract class
3. Add lazy import in `backends/__init__.py`
4. Add backend selection in `job_queue.py`
5. Create `tests/test_backends/test_mybackend.py`

### Adding a new job field
1. Update `Job` model in `schemas.py`
2. Update serialization in all backends
3. Add tests in `test_schemas.py`

### Creating an ADR
1. Copy `docs/architecture/decisions/ADR_TEMPLATE.md`
2. Fill in all sections
3. Update `docs/architecture/decisions/README.md` index

## Troubleshooting

### "ModuleNotFoundError: No module named 'jdobb_async_queue'"
```bash
# Ensure you installed in editable mode
pip install -e ".[all,dev]"
```

### Redis tests skipped
```bash
# Check if Redis is running
redis-cli ping

# If not, start Redis
docker start redis  # If using Docker
```

### Async test errors
```bash
# Ensure pytest-asyncio is installed
pip install pytest-asyncio

# Check pyproject.toml has asyncio_mode = "auto"
```

---

**Update When:** Development workflow changes or new tools added.
