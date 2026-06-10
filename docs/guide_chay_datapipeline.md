# Hướng dẫn chạy Pipeline Crawl — RealEstate Chatbot v2

## Context

Bạn muốn chạy pipeline crawl + ingest local trên máy Windows + bash. Document này là runbook cụ thể để bạn chạy từng stage hoặc full pipeline. Nội dung này phản ánh **trạng thái thực tế của code trên main**, đã verify từng flag bằng cách đọc argparse trong source. Không phải plan thay đổi code.

**Lưu ý quan trọng:** Crawler `projects/` và `news/` now have fixture-backed parser selectors. Keep smoke runs small first because live DOM and anti-bot behavior can still change.

---

## 1. Setup môi trường (chạy 1 lần)

```bash
cd d:/CODE/RealEstate_Chatbot_v2

# Python deps
pip install -r requirements.txt -r backend/requirements.txt

# Playwright browser (bắt buộc cho mọi crawler)
playwright install chromium

# Postgres + pgvector (bắt buộc cho ingest)
docker compose up -d postgres

# Apply migrations tới HEAD (BGE-M3: 20260801_0007)
cd backend && alembic upgrade head && cd ..

# Migration 20260801_0007 đổi chunks.embedding sang vector(1024) cho BGE-M3
# và xóa chunks hiện có. Sau bước này cần re-ingest listings/projects/news/legal KB
# trước khi test chatbot hoặc hybrid search.

# Env vars (ingest cần GEMINI_API_KEY; crawler không cần env nào)
export GEMINI_API_KEY=<your-key>
# Optional:
# export COHERE_API_KEY=<key>           # rerank, không dùng ở ingest
# export INTENT_EXTRACTOR=gemini        # bật LLM intent extraction cho listings
# export GEOCODER_PROVIDER=nominatim    # default; goong = no-op + warn
```

`DATABASE_URL` mặc định trỏ vào container Postgres (`postgresql+asyncpg://admin:realestate_secret_2026@localhost:5432/realestate`) nên không cần set khi chạy local.

---

## 2. Crawler CLI flags (đã verify từ argparse)

### Sale listings

| Flag | Default | Note |
|---|---|---|
| `python -m crawler.sale.crawl_urls --pages START END` | `1 10223` | URL listing crawl |
| `--output` | `apartments.csv` | **CWD-relative, NOT data/raw/** — luôn override |
| `--workers` | `8` | |
| `--since YYYY-MM-DD` | none | stored, no-op ở stage URL |

| Flag | Default |
|---|---|
| `python -m crawler.sale.crawl_details --input` | `../listing_url.csv` (CWD-relative) |
| `--output` | `../listing_details.csv` |
| `--workers` | `4` |
| `--limit` | `0` (all) |
| `--since YYYY-MM-DD` | filter post_date ở stage detail |

### Rent listings

| Flag | Default |
|---|---|
| `python -m crawler.rent.crawl_urls --pages START END` | `1 10223` |
| `--output` | `data/raw/rent_urls.csv` |
| `--workers` | `8` |
| `--since YYYY-MM-DD` | stored, no-op |

| Flag | Default |
|---|---|
| `python -m crawler.rent.crawl_details --input` | `data/raw/rent_urls.csv` |
| `--output` | `data/raw/rent_details.csv` |
| `--workers` | `4`, `--limit 0`, `--since` |

### Projects / News

- `python -m crawler.projects.crawl_urls --pages 1 100 --output data/raw/project_urls.csv --workers 4`
- `python -m crawler.projects.crawl_details --input data/raw/project_urls.csv --output data/raw/project_details.csv --workers 4 --limit 0`
- `python -m crawler.news.crawl_articles --pages 1 50 --output data/raw/news_articles.csv --workers 4`

---

## 3. Ingestor CLI flags

```bash
# Listings (sale hoặc rent — cùng entry point, cùng schema)
python -m data_pipeline.ingestors.listings_ingestor --csv data/raw/sale_details.csv --batch-size 50

# Projects (cần GEMINI_API_KEY)
python -m data_pipeline.ingestors.projects_ingestor --csv data/raw/project_details.csv --batch-size 25

# News
python -m data_pipeline.ingestors.news_ingestor --csv data/raw/news_articles.csv --batch-size 25

# Legal KB (đọc dir, không phải CSV)
python -m data_pipeline.ingestors.legal_kb_ingestor
# Optional override:
python -m data_pipeline.ingestors.legal_kb_ingestor --raw-dir data/knowledge/raw --log-dir data/knowledge/ingested
```

Tất cả ingestor đều **idempotent**: upsert key `product_id` (listings), `slug` (projects), `url` (articles); chunks bị delete + re-insert mỗi lần. Legal KB skip qua SHA-256 manifest.

## Unified crawl -> CSV -> publish -> index flow

All crawler stages keep writing CSV artifacts first. Ingestors then publish structured parent rows to PostgreSQL before semantic indexing:

- listings CSV -> `listings` -> `chunks(parent_type='listing')`
- projects CSV -> `projects` -> `chunks(parent_type='project')`
- news CSV -> `articles(category='news')` -> `chunks(parent_type='article')`
- legal documents -> `articles(category='legal')` -> `chunks(parent_type='article')`

The web/API reads parent tables and should not wait for BGE-M3 indexing. Chatbot/RAG reads `chunks` and may lag behind web visibility.

Example projects/news commands:

```bash
python -m crawler.projects.crawl_urls --pages 1 20 --output data/raw/projects_urls.csv --workers 3
python -m crawler.projects.crawl_details --input data/raw/projects_urls.csv --output data/raw/projects_details.csv --workers 3
python -m data_pipeline.ingestors.projects_ingestor --csv data/raw/projects_details.csv --batch-size 25

python -m crawler.news.crawl_articles --pages 1 10 --output data/raw/news_articles.csv --workers 2
python -m data_pipeline.ingestors.news_ingestor --csv data/raw/news_articles.csv --batch-size 25
```

### Crawl -> publish web -> index chatbot

Với listings sale/rent, crawler vẫn chỉ ghi CSV. Bước đẩy dữ liệu lên web nằm ở `data_pipeline.ingestors.listings_ingestor`:

1. Cào URL/detail ra CSV.
2. Ingestor clean/enrich và upsert listing vào bảng `listings` trước.
3. Sau khi publish listing thành công, ingestor mới build semantic chunks, embed bằng BGE-M3 1024 chiều, rồi ghi vào bảng `chunks`.

Ví dụ sale:

```bash
python -m crawler.sale.crawl_urls --pages 1 30 --output data/raw/sale_urls.csv --workers 4
python -m crawler.sale.crawl_details --input data/raw/sale_urls.csv --output data/raw/sale_details.csv --workers 4
python -m data_pipeline.ingestors.listings_ingestor --csv data/raw/sale_details.csv --batch-size 50
```

Nếu embedding/indexing lỗi, listing đã publish vẫn nằm trong `listings` để frontend/API hiển thị. Sau khi sửa lỗi embedding hoặc model, chạy lại cùng lệnh ingestor với cùng CSV; upsert theo `product_id` sẽ cập nhật listing và tái tạo chunks.

Sau migration `20260801_0007`, chạy lại các ingestor theo nguồn dữ liệu bạn
đang có để tái tạo `chunks` bằng embedding BGE-M3 1024 chiều. Tối thiểu với
dữ liệu local hiện tại, hãy re-ingest listings, projects, news, và legal KB khi CSV/source data có sẵn.

---

## 4. Resume / incremental

- **Detail crawlers** đọc output CSV hiện có + worker tmp files → skip product_id / slug đã có. Cứ chạy lại, tự resume.
- **URL crawlers**: `--since` được nhận flag nhưng no-op (chỉ filter ở detail stage).
- **Ingestor**: không có `--since`. Upsert idempotent → chạy lại với cùng CSV không hỏng dữ liệu.

---

## 5. Sample full run (sale + rent)

```bash
# Crawl sale (30 trang đầu)
python -m crawler.sale.crawl_urls --pages 1 30 --output data/raw/sale_urls.csv --workers 4
python -m crawler.sale.crawl_details --input data/raw/sale_urls.csv --output data/raw/sale_details.csv --workers 4
python -m data_pipeline.ingestors.listings_ingestor --csv data/raw/sale_details.csv --batch-size 50

# Crawl rent
python -m crawler.rent.crawl_urls --pages 1 30 --workers 4
python -m crawler.rent.crawl_details --workers 4
python -m data_pipeline.ingestors.listings_ingestor --csv data/raw/rent_details.csv

# Legal KB (drop PDF/HTML vào data/knowledge/raw/<slug>/ trước)
python -m data_pipeline.ingestors.legal_kb_ingestor
```

---

## 6. Alternative: Airflow

**Prereq:** root compose phải up trước để network `realestate_chatbot_v2_default` tồn tại:

```bash
docker compose up -d                    # tạo network + postgres
docker network inspect realestate_chatbot_v2_default
```

Tạo `airflow/.env` từ template:

```bash
cp airflow/.env.example airflow/.env
# Điền AIRFLOW_FERNET_KEY (sinh bằng python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
# GEMINI_API_KEY, POSTGRES_PASSWORD bắt buộc; COHERE/SLACK/SMTP optional
```

Bring up Airflow:

```bash
docker compose -f airflow/docker-compose.airflow.yml up -d
# UI: http://localhost:8080  (admin / admin)
```

Tạo Connection `realestate_app` trong Admin → Connections (host `realestate_postgres`, port 5432, db `realestate`, login `admin`, password = `${POSTGRES_PASSWORD}`).

DAGs có sẵn:

| DAG | Cron | Tasks |
|---|---|---|
| `daily_listings_dag` | `0 2 * * *` ICT | sale + rent groups → mark_active |
| `weekly_projects_dag` | `0 3 * * 0` | crawl + ingest projects |
| `weekly_news_dag` | `0 4 * * 0` | crawl + ingest news |
| `monthly_legal_kb_dag` | `0 5 1 * *` | ingest_legal_kb |

Trigger thủ công:

```bash
docker compose -f airflow/docker-compose.airflow.yml exec airflow_scheduler \
  airflow dags trigger daily_listings_dag
```

Watch run:

```bash
docker compose -f airflow/docker-compose.airflow.yml logs -f airflow_scheduler
```

Mỗi run thành công sẽ ghi 1 row vào bảng `pipeline_runs` (M5).

---

## 7. Verify sau khi chạy

```bash
# Xem listings + chunks count
docker exec realestate_postgres psql -U admin -d realestate -c \
  "SELECT listing_type, count(*) FROM listings GROUP BY listing_type;"

docker exec realestate_postgres psql -U admin -d realestate -c \
  "SELECT parent_type, count(*) FROM chunks GROUP BY parent_type;"

# Xem geocode coverage (chỉ listings)
docker exec realestate_postgres psql -U admin -d realestate -c \
  "SELECT count(*) FILTER (WHERE latitude IS NOT NULL) AS geocoded, count(*) FROM listings;"

# Test hybrid_search end-to-end
python -c "import asyncio; from chatbot.tools.hybrid_search import hybrid_search; \
  print(asyncio.run(hybrid_search('căn hộ 2PN Quận 7 dưới 5 tỷ', filters={'listing_type':'sale','district':'Quận 7'}, parent_type='listing')))"
```

---

## 8. Troubleshooting

- **`playwright` lỗi "Executable doesn't exist"**: chưa chạy `playwright install chromium`.
- **Ingestor lỗi `GEMINI_API_KEY required`**: env var chưa export trong shell hiện tại.
- **`asyncpg.exceptions.InvalidPasswordError`**: postgres container chưa up hoặc `POSTGRES_PASSWORD` lệch với `DATABASE_URL`.
- **Crawler bị batdongsan rate-limit**: giảm `--workers` xuống 2-3, hoặc thêm delay (browser stealth có sẵn nhưng IP cùng range vẫn bị).
- **`projects.crawl_*` / `news.crawl_articles` ra CSV rỗng**: fixture-backed selectors may no longer match live DOM or the site may rate-limit the browser. Run parser tests first, then smoke with low `--workers`.
- **Ingestor warn `goong`**: bạn để `GEOCODER_PROVIDER=goong`. Switch về `nominatim` hoặc unset.

---

## 9. Critical files cheat-sheet

- Crawler entrypoints: `crawler/{sale,rent,projects,news}/crawl_*.py`
- Ingestor entrypoints: `data_pipeline/ingestors/{listings,projects,news,legal_kb}_ingestor.py`
- Config: `backend/app/config.py`, `chatbot/config.py`, `airflow/.env.example`
- Compose: `docker-compose.yml` (root), `airflow/docker-compose.airflow.yml`
- Migrations: `backend/alembic/versions/*.py`
