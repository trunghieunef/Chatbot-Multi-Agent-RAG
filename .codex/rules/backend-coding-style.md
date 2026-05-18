---
paths:
  - backend/**/*
  - data_pipeline/**/*
---
# Backend Coding Style

- Framework: FastAPI with async/await.
- ORM: SQLAlchemy 2.0 async mode (`asyncpg` driver).
- Validation: Pydantic v2 schemas in `backend/app/schemas/`.
- Config: Pydantic Settings loading from `.env`.
- API versioning: all routes prefixed `/api/v1/`.
- Router pattern: one file per resource in `backend/app/routers/`.
- Type hints: required on all function signatures.
- Naming: `snake_case` for files/functions/variables, `PascalCase` for classes.
- Docstrings: write for all modules, classes, and public functions.
- Keep code `async` wherever database or network I/O is involved.
- Database session: use `get_db` dependency from `app.database`.
