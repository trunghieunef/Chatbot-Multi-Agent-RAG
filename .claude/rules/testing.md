# Testing Guidelines

- No dedicated test suite is configured yet.
- Run ESLint (`cd frontend; npm run lint`) for frontend changes.
- Run `python -m compileall backend\app RAG data_pipeline` for Python changes.
- When adding tests:
  - Place backend tests under `backend/tests/` with `test_*.py` names.
  - Place frontend tests near components or under `frontend/__tests__/`.
