# Repository Guidelines

## Project Structure & Module Organization

This is a full-stack Vietnamese real estate chatbot platform.

- `backend/`: FastAPI backend. Use `backend/app/main.py` for new development; `backend/main.py` is legacy CSV-based code.
- `backend/app/models`, `schemas`, `routers`: SQLAlchemy models, Pydantic contracts, and API endpoints.
- `frontend/`: Next.js App Router application. Pages live in `frontend/app`, reusable UI in `frontend/components`, API/types in `frontend/lib`.
- `RAG/`: LangGraph multi-agent chatbot scaffold and specialized agents.
- `Crawl/`: Playwright crawler scripts and crawler Docker files.
- `data_pipeline/`: ETL loader from CSV data into PostgreSQL.
- `data/`: local CSV/database assets used for development.

## Build, Test, and Development Commands

- `docker-compose up -d postgres redis chromadb`: start local infrastructure.
- `cd backend; pip install -r requirements.txt`: install backend dependencies.
- `cd backend; uvicorn app.main:app --reload --port 8000`: run the FastAPI v2 app.
- `cd frontend; npm install`: install frontend dependencies.
- `cd frontend; npm run dev`: run Next.js at `http://localhost:3000`.
- `cd frontend; npm run lint`: run ESLint.
- `python -m compileall backend\app RAG data_pipeline`: quick Python syntax/import sanity check.
- `docker-compose up --build`: build and run the full stack.

## Coding Style & Naming Conventions

Use Python type hints for function signatures and keep backend code async where database or network I/O is involved. Python files use `snake_case`; classes use `PascalCase`. Keep API schemas in `backend/app/schemas` and route logic in `backend/app/routers`.

Frontend code uses TypeScript, functional React components, and `PascalCase` component filenames. Keep shared API calls in `frontend/lib/api.ts` and shared types in `frontend/lib/types.ts`. The frontend uses Tailwind CSS v4 and `lucide-react` icons. Read `frontend/AGENTS.md` before changing Next.js behavior.

## Testing Guidelines

No dedicated test suite is configured yet. For now, run ESLint for frontend changes and `compileall` for Python changes. When adding tests, place backend tests under `backend/tests/` with `test_*.py` names and frontend tests near components or under `frontend/__tests__/`.

## Commit & Pull Request Guidelines

Current commit history is brief and does not define a strict convention. Use short, imperative commit messages such as `fix chat router import` or `add listing filter tests`. Pull requests should include a clear summary, commands run, linked issue if available, and screenshots for UI changes.

## Security & Configuration Tips

Keep secrets in `.env`; do not commit real API keys, database passwords, or JWT secrets. `GEMINI_API_KEY`, `DATABASE_URL`, `REDIS_URL`, and `NEXT_PUBLIC_API_URL` must be checked when running services locally or in Docker.
