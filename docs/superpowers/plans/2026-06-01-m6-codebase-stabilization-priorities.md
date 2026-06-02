# Codebase Stabilization Priorities Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stabilize the current codebase after the RAG/BGE-M3 migration by fixing the environment blocker, syncing stale docs, reducing infrastructure ambiguity, and preparing the remaining crawler/data work.

**Architecture:** Keep the current FastAPI + Next.js + PostgreSQL/pgvector architecture. Treat PostgreSQL + pgvector as the active retrieval path, BGE-M3 1024 as the active embedding contract, and update docs/config/tests around that truth before adding new crawler selectors.

**Tech Stack:** FastAPI, Pydantic Settings, SQLAlchemy async, Alembic, pgvector, Redis, Next.js, ESLint, pytest.

---

## Summary

This plan covers the stabilization items identified in the latest codebase review:

- Make `Settings.DEBUG` tolerant of `release`, `prod`, and `production`, mapping them to `False`.
- Set local `.env` to the boolean value `DEBUG=false`.
- Update `docs/pipeline.md` and `docs/implementation_plan.md` so they describe BGE-M3 1024-dimensional pgvector retrieval.
- Remove ChromaDB from the active Docker Compose topology because no current RAG code uses it.
- Create a separate follow-up plan for projects/news crawler selectors.
- Preserve the existing dirty worktree and avoid reverting unrelated user changes.

---

## Task 1: Fix `DEBUG=release` Environment Blocker

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/tests/test_m2_config.py`
- Modify: `.env`

- [ ] Add `pydantic.field_validator` to parse release-like debug strings.
- [ ] Add tests for `DEBUG="release"`, `DEBUG="false"`, and `DEBUG="true"`.
- [ ] Set `.env` to `DEBUG=false`.
- [ ] Verify with:

```powershell
python -m pytest backend\tests\test_m2_config.py -q
```

Expected: config tests pass without overriding `$env:DEBUG`.

---

## Task 2: Sync Pipeline Docs To Current BGE-M3 Reality

**Files:**
- Modify: `docs/pipeline.md`
- Modify: `docs/implementation_plan.md`

- [ ] Replace active embedding references from Gemini/text-embedding 768-dimensional vectors to BGE-M3 `BAAI/bge-m3` 1024-dimensional vectors.
- [ ] Add a current-state note documenting migration `20260801_0007_bge_m3_embeddings.py`.
- [ ] Keep the projects/news scaffold warning so users do not expect non-empty CSVs from those crawlers yet.
- [ ] Verify stale active claims with:

```powershell
rg "text-embedding-004|Vector\(768\)|vec\(768\)|ChromaDB / Qdrant|Setup ChromaDB" docs\pipeline.md docs\implementation_plan.md
```

Expected: no active stale claims remain.

---

## Task 3: Resolve ChromaDB Architecture Ambiguity

**Files:**
- Modify: `docker-compose.yml`
- Modify: `backend/app/config.py`
- Modify: `chatbot/config.py`
- Modify: `docs/pipeline.md`
- Modify: `docs/implementation_plan.md`

- [ ] Remove the `chromadb` service from root compose.
- [ ] Remove backend `depends_on` and environment references to ChromaDB.
- [ ] Remove unused Chroma config constants.
- [ ] Document PostgreSQL + pgvector as the active vector store.
- [ ] Verify with:

```powershell
docker compose config
rg "CHROMA|chromadb|Chroma" backend data_pipeline chatbot docs\pipeline.md docs\implementation_plan.md docker-compose.yml
```

Expected: compose validates; any remaining Chroma references are historical only.

---

## Task 4: Plan Projects/News Selector Implementation Separately

**Files:**
- Create: `docs/superpowers/plans/2026-06-01-m8-projects-news-crawl-publish-pipeline.md`

- [ ] Create a separate implementation plan for parser selectors and fixture-backed tests.
- [ ] Keep selector implementation out of this stabilization pass.
- [ ] Preserve existing CLI flags documented in `guide_chay_datapipeline.md`.

---

## Task 5: Verify And Preserve Dirty Worktree

**Files:**
- No commit required by this implementation pass.

- [ ] Inspect the worktree before and after edits:

```powershell
git status --short
git diff --stat
```

- [ ] Run final verification:

```powershell
python -m pytest backend\tests -q
python -m compileall backend\app data_pipeline chatbot crawler
cd frontend
npm run lint
```

Expected: backend tests pass, Python syntax check passes, and frontend lint passes.

---

## Public Interfaces And Data Contracts

- No new API endpoints.
- `Settings.DEBUG` accepts release-like strings and maps them to `False`.
- Active embedding contract remains `BAAI/bge-m3`, dense vector size `1024`.
- Active vector retrieval contract remains PostgreSQL `chunks.embedding vector(1024)` via pgvector.
- Projects/news crawler output schemas remain unchanged in this pass.

---

## Assumptions

- PostgreSQL + pgvector is the intended production vector store now.
- `guide_chay_datapipeline.md` is the most current runbook.
- Existing dirty worktree changes belong to the user/current branch and must be preserved.
