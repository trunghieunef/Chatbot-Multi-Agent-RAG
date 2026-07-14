---
paths:
  - crawler/**/*
  - pipeline_worker/**/*
  - data_pipeline/**/*
---
# Crawler & Pipeline Conventions

## Crawler (`crawler/`)

- Tool: Playwright + playwright-stealth for anti-bot bypass.
- Parallelism: 8 workers for URL crawling, 4 workers for detail crawling.
- Output: CSV files in `data/raw/`.
- Anti-detection: stealth mode, random delays (1-3s), user-agent rotation, browser restart every 15-20 pages.
- Resume support: skips already-crawled `product_id`s from output + `.tmp` files.
- Crash-safe: each worker writes to its own `.tmp` file, merged at end.
- Deduplication: by `product_id` during merge step.

### Crawlers
- `crawler/sale/` — sale listing URL crawl + detail crawl
- `crawler/rent/` — rental listing URL crawl + detail crawl
- `crawler/news/` — news article URL crawl + detail crawl
- `crawler/projects/` — real estate project URL crawl + detail crawl
- `crawler/core/` — shared: `csv_writer.py`, `parser.py`, `listing_detail_parser.py`, `listing_images.py`

### Run examples
```bash
python -m crawler.sale.crawl_urls --pages 1 5 --output data/raw/listing_urls.csv
python -m crawler.sale.crawl_details --input data/raw/listing_urls.csv --output data/raw/listing_details.csv
```

## Data Pipeline (`data_pipeline/`)

Stages: `clean.py` → `chunk.py` → `embed.py` → `ingestors/`

### Ingestors
- `listings_ingestor.py` — ingest listings from CSV into `listings` + `chunks` tables
- `projects_ingestor.py` — ingest projects into `projects` + `chunks` tables
- `news_ingestor.py` — ingest articles into `articles` + `chunks` tables
- `legal_kb_ingestor.py` — ingest legal knowledge base into `chunks` table
- `hf_legal_ingestor.py` — ingest legal KB from HuggingFace datasets
- `market_snapshot_ingestor.py` — aggregate market price snapshots into `market_price_snapshots`

### Run examples
```bash
python -m data_pipeline.ingestors.listings_ingestor --csv data/raw/listing_details.csv --batch-size 50
python -m data_pipeline.ingestors.news_ingestor --csv data/raw/news_details.csv
```

## Pipeline Worker (`pipeline_worker/`)

Standalone FastAPI service (:8200) that exposes `/internal/pipeline/*` endpoints.
Triggers crawler and data_pipeline jobs as subprocess commands.
Job state tracked in `pipeline_runs` table.
