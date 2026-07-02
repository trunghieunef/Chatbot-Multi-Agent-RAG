---
paths:
  - backend/tests/**/*
  - agent_service/tests/**/*
---
# Testing Guidelines

## Two Separate Suites

### Backend tests (`backend/tests/`)
- ~90 test files covering API routes, chat pipeline, RAG, observability, market endpoints.
- `backend/tests/conftest.py` — adds repo root to `sys.path`.
- Run: `cd backend && python -m pytest tests -q`

### Agent service tests (`agent_service/tests/`)
- ~25 test files covering graph nodes, specialist agents, tool registry, evaluation, streaming.
- `agent_service/tests/conftest.py` — adds root + backend dirs to `sys.path`.
- Run from repo root: `python -m pytest agent_service/tests -q`

## Patterns

- **No real LLM calls in tests.** Inject a fake `httpx` transport or stub `LLMClient` — see existing tests in `agent_service/tests/` for the pattern.
- **No real Redis/Postgres in unit tests.** Use in-memory fakes or `pytest-asyncio` with a test DB fixture where needed.
- Backend integration tests that need DB use `AsyncSession` from a test engine configured in `conftest.py`.
- Agent tests that need a `ToolRegistry` instantiate a fresh `ToolRegistry()` with stub async functions registered — not the production registry.

## File Placement

- Backend tests: `backend/tests/test_*.py`
- Agent tests: `agent_service/tests/test_*.py`
- Frontend tests: near component or `frontend/__tests__/` (ESLint via `npm run lint` is the primary check)

## Lint & Type Checks

```bash
cd frontend && npm run lint               # ESLint — required for any frontend change
python -m compileall backend/app agent_service pipeline_worker  # syntax check
```

## Coverage Note

No formal coverage thresholds configured. Focus on testing behavior at service boundaries and non-trivial logic paths (retry, quota, routing, synthesis).
