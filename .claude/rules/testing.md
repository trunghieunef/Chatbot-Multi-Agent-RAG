---
paths:
  - services/backend/tests/**/*
  - services/agent_service/tests/**/*
---
# Testing Guidelines

## Two Separate Suites

### Backend tests (`services/backend/tests/`)
- ~90 test files covering API routes, chat pipeline, RAG, observability, market endpoints.
- Run: `python -m pytest services/backend/tests -q`

### Agent service tests (`services/agent_service/tests/`)
- ~25 test files covering graph nodes, specialist agents, tool registry, evaluation, streaming.
- Run: `python -m pytest services/agent_service/tests -q`

Both suites are configured by the root `pytest.ini` (`pythonpath = .`); run pytest from the
repo root. `python -m pytest -q` runs both.

## Patterns

- **No real LLM calls in tests.** Inject a fake `httpx` transport or stub `LLMClient` — see existing tests in `services/agent_service/tests/` for the pattern.
- **No real Redis/Postgres in unit tests.** Use in-memory fakes or `pytest-asyncio` with a test DB fixture where needed.
- Backend integration tests that need DB use `AsyncSession` from a test engine configured in the test module.
- Agent tests that need a `ToolRegistry` instantiate a fresh `ToolRegistry()` with stub async functions registered — not the production registry.

## File Placement

- Backend tests: `services/backend/tests/test_*.py`
- Agent tests: `services/agent_service/tests/test_*.py`
- Frontend tests: near component or `services/frontend/__tests__/` (ESLint via `npm run lint` is the primary check)

## Lint & Type Checks

```bash
cd services/frontend && npm run lint               # ESLint — required for any frontend change
python -m compileall services/backend/app agent_service pipeline_worker  # syntax check
```

## Coverage Note

No formal coverage thresholds configured. Focus on testing behavior at service boundaries and non-trivial logic paths (retry, quota, routing, synthesis).
