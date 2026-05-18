# Phase 0 — Data Directory + Database Foundation

> **Prerequisite:** None. This is the first phase.
> **Goal:** Create a stable database with migrations and a repeatable data pipeline.
> **Timeline:** Week 1-2

---

## Section 1: Data Directory Structure

**Why:** Data files currently live flat in `data/`. The pipeline needs `data/raw/` (crawler output) and `data/processed/` (cleaned output) separation.

### Tasks

- [ ] Create directories: `data/raw/`, `data/processed/`, `data/logs/`.
- [ ] Move `data/listing_details.csv` → `data/raw/listing_details.csv`.
- [ ] Move `data/listing_url.csv` → `data/raw/listing_url.csv`.
- [ ] Keep `data/apartments.csv` and `data/apartments_cleaned.csv` as legacy reference (do not delete, do not use in pipeline).
- [ ] Update `data_pipeline/load_db.py` default `--csv` path from `../data/listing_details.csv` to `../data/raw/listing_details.csv`.

### Verify

```powershell
Test-Path data\raw\listing_details.csv   # True
Test-Path data\raw\listing_url.csv       # True
Test-Path data\processed                 # True
Test-Path data\logs                      # True
```

---

## Section 2: Fix Crawler Bugs

**Why:** The URL crawler's `_merge_tmp_files` function references `page_num` which is commented out, causing crashes on merge.

### Tasks

- [ ] In `Crawl/01.crawl_listing_url.py`, fix `_merge_tmp_files()` at line ~198: remove the `int(r["page_num"])` sort key. Replace with:
  ```python
  all_rows.sort(key=lambda r: r["product_id"])
  ```
- [ ] Verify that `FIELDS` list (line ~29) contains only `product_id` and `url` (which is the current state — this is correct).

### Verify

```powershell
python Crawl\01.crawl_listing_url.py --pages 1 2 --workers 2 --output data\raw\listing_url_test.csv
# Should complete without KeyError
Remove-Item data\raw\listing_url_test.csv -ErrorAction SilentlyContinue
```

---

## Section 3: Alembic Migration Setup

**Why:** The app currently uses `Base.metadata.create_all()` at startup which is unsafe for production. Alembic provides versioned, repeatable migrations.

### Tasks

- [ ] Install Alembic: `pip install alembic` (add to `backend/requirements.txt`).
- [ ] Run `cd backend; alembic init alembic` to create Alembic scaffold.
- [ ] Edit `backend/alembic.ini`: set `sqlalchemy.url` to read from env or leave blank (we'll configure in `env.py`).
- [ ] Edit `backend/alembic/env.py`:
  - Import `from app.database import Base` and `from app.models import *` so all models are discovered.
  - Set `target_metadata = Base.metadata`.
  - Configure async engine support (use `run_async_migrations` pattern for asyncpg).
- [ ] Generate initial migration: `cd backend; alembic revision --autogenerate -m "initial schema"`.
- [ ] Manually verify the generated migration includes `CREATE EXTENSION IF NOT EXISTS vector` before any vector column.
- [ ] Test: `cd backend; alembic upgrade head` against a clean database.
- [ ] In `backend/app/database.py` function `init_db()`: wrap `create_all` behind `if settings.DEV_CREATE_TABLES:` (default False).
- [ ] Add `DEV_CREATE_TABLES: bool = False` to `backend/app/config.py` Settings class.

### Verify

```powershell
cd backend
alembic upgrade head
# Should succeed, tables created
alembic current
# Should show the migration hash
```

---

## Section 4: Add Listing Freshness Field

**Why:** Pipeline needs to track when each listing was last processed.

### Tasks

- [ ] Add to `backend/app/models/listing.py` class `Listing`:
  ```python
  last_crawled_at = Column(DateTime, nullable=True)
  ```
- [ ] Generate migration: `cd backend; alembic revision --autogenerate -m "add last_crawled_at"`.
- [ ] Apply: `cd backend; alembic upgrade head`.

### Verify

```powershell
cd backend
alembic upgrade head
python -c "from app.models.listing import Listing; print([c.name for c in Listing.__table__.columns if 'crawl' in c.name])"
# Should print: ['last_crawled_at']
```

---

## Section 5: Cleaning Module

**Why:** Parsing logic currently lives inside `data_pipeline/load_db.py` mixed with DB operations. Extract it into a standalone cleaning module.

### Tasks

- [ ] Create `data_pipeline/clean.py`.
- [ ] Move these functions from `load_db.py` into `clean.py` (keep them importable):
  - `parse_price_billion(text) -> float | None`
  - `parse_area(text) -> float | None`
  - `parse_int_safe(text) -> int | None`
  - `parse_price_per_m2(text) -> float | None`
  - `determine_listing_type(row) -> str`
  - `determine_property_type(row) -> str`
  - `extract_location(row) -> tuple[str, str, str]`
- [ ] Add function `clean_csv(input_path: str, output_path: str) -> dict`:
  - Read raw CSV from `input_path`.
  - Apply all parse functions to each row.
  - Map CSV column `legal` → model field `legal_status`.
  - Map CSV column `listing_type` → model field `listing_type_label` (derive actual `listing_type` from title/url/price using `determine_listing_type`).
  - Drop rows without `product_id` or `title`.
  - Deduplicate by `product_id`.
  - Write cleaned CSV to `output_path`.
  - Return `{"total": N, "valid": N, "dropped": N, "deduped": N}`.
- [ ] Default input: `data/raw/listing_details.csv`.
- [ ] Default output: `data/processed/listings_clean.csv`.

### Verify

```powershell
python -c "from data_pipeline.clean import clean_csv; r = clean_csv('data/raw/listing_details.csv', 'data/processed/listings_clean.csv'); print(r)"
# Should print counts dict
Test-Path data\processed\listings_clean.csv   # True
```

---

## Section 6: Validation Module

**Why:** Need to report data quality before loading into the database.

### Tasks

- [ ] Create `data_pipeline/validate.py`.
- [ ] Add function `validate_csv(csv_path: str, report_path: str) -> dict`:
  - Count total rows, valid rows, invalid rows.
  - Check: missing `product_id`, missing `title`, `price <= 0`, `area <= 0`, suspicious values (`price < 0.1`, `area > 10000`).
  - Write JSON report to `report_path`.
  - Return summary dict.
- [ ] Default report path: `data/processed/validation_report.json`.

### Verify

```powershell
python -c "from data_pipeline.validate import validate_csv; r = validate_csv('data/processed/listings_clean.csv', 'data/processed/validation_report.json'); print(r)"
Get-Content data\processed\validation_report.json | ConvertFrom-Json
```

---

## Section 7: Loader Rewrite (Insert → Upsert)

> **Prerequisite:** Section 3 (Alembic) must be done. Loader will no longer call `create_all`.

**Why:** Current loader only inserts new rows and skips existing ones. We need upsert to update changed fields.

### Tasks

- [ ] Rewrite `data_pipeline/load_db.py`:
  - **Remove** `Base.metadata.create_all` and `CREATE EXTENSION` calls (Alembic handles this now).
  - Accept cleaned CSV as input (default: `data/processed/listings_clean.csv`).
  - Use SQLAlchemy `insert(...).on_conflict_do_update(index_elements=["product_id"], set_={...})` for upsert.
  - Update `last_crawled_at = func.now()` for every processed row.
  - Track and print counts: `inserted`, `updated`, `unchanged`, `skipped`, `errors`.
- [ ] Keep `--csv` and `--batch-size` CLI arguments.

### Verify

```powershell
# First load
python -m data_pipeline.load_db --csv data\processed\listings_clean.csv
# Second load (same data) — should show 0 inserted, all unchanged
python -m data_pipeline.load_db --csv data\processed\listings_clean.csv
```

---

## Section 8: Pipeline Runner

**Why:** Single command to run the full pipeline: clean → validate → load.

### Tasks

- [ ] Create `data_pipeline/run_pipeline.py`.
- [ ] CLI arguments:
  - `--input` (default: `data/raw/listing_details.csv`)
  - `--skip-crawl` (skip crawl steps, use existing raw CSV)
  - `--dry-run` (validate and report only, no DB write)
  - `--batch-size` (for loader, default 200)
- [ ] Pipeline steps (with `--skip-crawl`):
  1. Clean: `clean_csv(input, "data/processed/listings_clean.csv")`
  2. Validate: `validate_csv("data/processed/listings_clean.csv", "data/processed/validation_report.json")`
  3. Load (unless `--dry-run`): `load_csv_to_db("data/processed/listings_clean.csv")`
- [ ] Write logs to `data/logs/pipeline_YYYY-MM-DD.log` (Python `logging` module).
- [ ] Do NOT integrate crawler scripts into the runner in this phase.
- [ ] Do NOT add scheduler in this phase.

### Verify

```powershell
python -m data_pipeline.run_pipeline --skip-crawl --input data\raw\listing_details.csv --dry-run
# Should print clean + validate counts, NO db writes
python -m data_pipeline.run_pipeline --skip-crawl --input data\raw\listing_details.csv
# Should clean, validate, load into DB
Test-Path data\logs\pipeline_*.log   # True
```

---

## Out Of Scope (do NOT implement in Phase 0)

- Crawler for rent / project / news
- Scheduled crawling (APScheduler / cron)
- Redis cache
- Price history tracking
- ML / forecast data preparation
- ChromaDB embeddings
