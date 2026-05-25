# M3 Airflow Orchestration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Orchestrate the M1 + M2 ingestion pipelines as scheduled Apache Airflow DAGs running in their own Docker stack, so sale + rent listings refresh daily, projects and news refresh weekly, with retry, structured logging, and alerting on failure.

**Architecture:** Run Airflow (webserver + scheduler + worker + dedicated metadata Postgres) in a separate docker-compose stack at `airflow/`. DAGs call shared Python helpers in `airflow/plugins/pipeline_runner.py` that wrap the existing crawler CLIs (subprocess) and ingestors (in-process module call). The app PostgreSQL stays the single source of truth for listings/projects/articles; Airflow uses its own metadata DB to avoid coupling.

**Tech Stack:** Apache Airflow 2.10+, Python 3.11, Docker Compose, existing `crawler/` and `data_pipeline/` modules.

---

## Scope And Existing Repo Notes

- M3 assumes M1 + M2 are merged: `crawler/sale|rent|projects|news`, `data_pipeline/ingestors/listings_ingestor|projects_ingestor|news_ingestor.py` all run cleanly when invoked from the repo root.
- Airflow lives in its own `docker-compose.airflow.yml` stack under `airflow/`. It joins the existing app stack via an external Docker network so DAGs can reach `realestate_postgres` by service name.
- Airflow metadata DB is a separate `airflow_postgres` service on port `5433`. Do not reuse `realestate_postgres` for Airflow metadata.
- All DAG schedules use `Asia/Ho_Chi_Minh` timezone. Crawler windows are 02:00–05:00 ICT to avoid peak hours.
- Crawler tasks invoke each `crawler.<source>.crawl_*` module via `subprocess.run` so Playwright + Chromium memory stays isolated from the Airflow worker. Ingestion tasks call `data_pipeline.ingestors.*.ingest_*_rows` directly because they have no browser footprint.
- The original master plan envisions five separate tasks per source (`crawl_urls → crawl_details → clean → enrich → load_db → chunk_and_embed → mark_active`). M3 collapses `clean → enrich → load_db → chunk_and_embed` into a single `ingest_<source>` task because the M2 ingestor already runs all four steps inside one transaction; splitting them would require breaking that transaction. `mark_active` stays as a separate downstream task.
- The `--since` flag added in M1 Task 9 + M2 is the durable mechanism for incremental crawls. Each DAG persists the last successful run timestamp via Airflow Variable `last_<source>_crawl_at`.
- Executor is `LocalExecutor` for now: 3 DAGs/day with at most a handful of parallel tasks fits one machine, and removing Celery + Redis cuts two services. Switch to `CeleryExecutor` only when horizontal scaling is needed.
- Alerting is opt-in via two channels: Airflow's built-in email (set `AIRFLOW__SMTP__*` env + `email_on_failure=True`) and Slack via `SLACK_WEBHOOK_URL`. Either can be left empty without breaking DAGs.
- Legal/PDF DAG is M4. M3 does not include `monthly_legal_kb_dag.py`.

## File Structure

- Create: `airflow/docker-compose.airflow.yml` — webserver + scheduler + airflow_postgres (LocalExecutor; no Celery/Redis worker)
- Create: `airflow/Dockerfile` — base image `apache/airflow:2.10-python3.11` plus Playwright deps and project source mount
- Create: `airflow/.env.example` — fernet key, secret key, app DB URL, Slack webhook placeholder
- Create: `airflow/requirements.txt` — pinned Airflow providers + project deps
- Create: `airflow/dags/daily_listings_dag.py` — sale + rent
- Create: `airflow/dags/weekly_projects_dag.py`
- Create: `airflow/dags/weekly_news_dag.py`
- Create: `airflow/plugins/__init__.py`
- Create: `airflow/plugins/pipeline_runner.py` — shared subprocess wrapper + ingest helpers
- Create: `airflow/plugins/alerting.py` — Slack on-failure callback
- Test: `backend/tests/test_pipeline_runner.py`
- Test: `backend/tests/test_dag_structure.py`

---

### Task 1: Airflow Stack Skeleton

**Files:**
- Create: `airflow/docker-compose.airflow.yml`
- Create: `airflow/Dockerfile`
- Create: `airflow/.env.example`
- Create: `airflow/requirements.txt`

- [ ] **Step 1: Write the Dockerfile**

Create `airflow/Dockerfile`:

```dockerfile
FROM apache/airflow:2.10.3-python3.11

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libpango-1.0-0 libcairo2 libasound2 \
    && rm -rf /var/lib/apt/lists/*

USER airflow
COPY airflow/requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt
RUN python -m playwright install chromium
```

- [ ] **Step 2: Write the docker-compose stack**

Create `airflow/docker-compose.airflow.yml`:

```yaml
x-airflow-common: &airflow-common
  build:
    context: ..
    dockerfile: airflow/Dockerfile
  environment:
    AIRFLOW__CORE__EXECUTOR: LocalExecutor
    AIRFLOW__CORE__FERNET_KEY: ${AIRFLOW_FERNET_KEY}
    AIRFLOW__CORE__DEFAULT_TIMEZONE: Asia/Ho_Chi_Minh
    AIRFLOW__CORE__LOAD_EXAMPLES: "false"
    AIRFLOW__CORE__PARALLELISM: "8"
    AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://airflow:airflow@airflow_postgres:5432/airflow
    AIRFLOW__SMTP__SMTP_HOST: ${SMTP_HOST:-}
    AIRFLOW__SMTP__SMTP_USER: ${SMTP_USER:-}
    AIRFLOW__SMTP__SMTP_PASSWORD: ${SMTP_PASSWORD:-}
    AIRFLOW__SMTP__SMTP_MAIL_FROM: ${SMTP_MAIL_FROM:-airflow@example.com}
    AIRFLOW__SMTP__SMTP_PORT: ${SMTP_PORT:-587}
    AIRFLOW__SMTP__SMTP_STARTTLS: "True"
    DATABASE_URL: postgresql+asyncpg://admin:${POSTGRES_PASSWORD:-realestate_secret_2026}@realestate_postgres:5432/realestate
    GEMINI_API_KEY: ${GEMINI_API_KEY}
    COHERE_API_KEY: ${COHERE_API_KEY}
    SLACK_WEBHOOK_URL: ${SLACK_WEBHOOK_URL:-}
    PYTHONPATH: /opt/project:/opt/project/backend
  volumes:
    - ../:/opt/project
    - ./dags:/opt/airflow/dags
    - ./plugins:/opt/airflow/plugins
    - airflow_logs:/opt/airflow/logs
  networks:
    - airflow_net
    - realestate_default

services:
  airflow_postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: airflow
      POSTGRES_PASSWORD: airflow
      POSTGRES_DB: airflow
    volumes:
      - airflow_pgdata:/var/lib/postgresql/data
    networks: [airflow_net]
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "airflow"]
      interval: 10s
      retries: 5

  airflow_init:
    <<: *airflow-common
    entrypoint: /bin/bash
    command:
      - -c
      - "airflow db migrate && airflow users create --username admin --password admin --firstname A --lastname D --role Admin --email admin@example.com || true"
    depends_on:
      airflow_postgres:
        condition: service_healthy

  airflow_webserver:
    <<: *airflow-common
    command: webserver
    ports: ["8080:8080"]
    mem_limit: 2g
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 5
    depends_on:
      airflow_init:
        condition: service_completed_successfully

  airflow_scheduler:
    <<: *airflow-common
    command: scheduler
    mem_limit: 3g
    healthcheck:
      test: ["CMD-SHELL", "airflow jobs check --job-type SchedulerJob --hostname \"$(hostname)\" || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 5
    depends_on:
      airflow_init:
        condition: service_completed_successfully

volumes:
  airflow_pgdata:
  airflow_logs:

networks:
  airflow_net:
  realestate_default:
    external: true
    name: realestate_chatbot_v2_default
```

- [ ] **Step 3: Write requirements**

Create `airflow/requirements.txt`:

```text
apache-airflow-providers-slack>=8.6.0
apache-airflow-providers-postgres>=5.10.0
playwright>=1.58.0
playwright-stealth>=2.0.2
sqlalchemy[asyncio]>=2.0.36
asyncpg>=0.30.0
pgvector>=0.3.6
google-genai>=1.0.0
httpx>=0.28.0
pydantic>=2.10.0
pydantic-settings>=2.7.0
python-dotenv>=1.0.0
```

- [ ] **Step 4: Write env example**

Create `airflow/.env.example`:

```text
AIRFLOW_FERNET_KEY=GENERATE_WITH_python_-c_'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
POSTGRES_PASSWORD=realestate_secret_2026
GEMINI_API_KEY=
COHERE_API_KEY=
SLACK_WEBHOOK_URL=
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_MAIL_FROM=airflow@example.com
ALERT_EMAIL_RECIPIENTS=
```

Create `airflow/.dockerignore` so the parent volume mount does not pull in heavy local-only directories during the build context copy:

```text
**/.git
**/.venv
**/node_modules
**/__pycache__
**/.pytest_cache
**/.next
data/raw
data/processed
```

- [ ] **Step 5: Verify Docker build**

```powershell
docker compose -f airflow\docker-compose.airflow.yml build
```

Expected: build completes without errors. If it fails, check that the parent docker-compose at the repo root has been brought up at least once so the network `realestate_chatbot_v2_default` exists.

- [ ] **Step 6: Commit**

```powershell
git add airflow/Dockerfile airflow/docker-compose.airflow.yml airflow/requirements.txt airflow/.env.example airflow/.dockerignore
git commit -m "scaffold airflow docker stack"
```

---

### Task 2: Pipeline Runner Helpers

**Files:**
- Create: `airflow/plugins/__init__.py`
- Create: `airflow/plugins/pipeline_runner.py`
- Test: `backend/tests/test_pipeline_runner.py`

The runner exposes one function per stage so DAGs stay declarative. Crawler stages use `subprocess.run`; ingestion stages call ingestors directly.

- [ ] **Step 1: Write failing tests for the subprocess wrapper**

Create `backend/tests/test_pipeline_runner.py`:

```python
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/ "airflow"))

from plugins.pipeline_runner import build_crawler_command, run_crawler


def test_build_crawler_command_assembles_module_and_args():
    cmd = build_crawler_command(
        module="crawler.sale.crawl_urls",
        args={"--pages": ["1", "10"], "--output": "data/raw/sale_urls.csv", "--workers": "4"},
    )

    assert cmd[:3] == [sys.executable, "-m", "crawler.sale.crawl_urls"]
    assert "--pages" in cmd and "1" in cmd and "10" in cmd
    assert "--output" in cmd and "data/raw/sale_urls.csv" in cmd


def test_run_crawler_raises_when_subprocess_fails(monkeypatch):
    class FakeCompleted:
        returncode = 2
        stdout = "boom"
        stderr = "stderr boom"

    def fake_run(cmd, **kwargs):
        return FakeCompleted()

    monkeypatch.setattr("plugins.pipeline_runner.subprocess.run", fake_run)

    with pytest.raises(RuntimeError) as exc:
        run_crawler(module="crawler.sale.crawl_urls", args={})

    assert "exit code 2" in str(exc.value)
```

- [ ] **Step 2: Run the tests and confirm import failure**

```powershell
cd backend
python -m pytest tests/test_pipeline_runner.py -q
```

Expected: fail because `plugins.pipeline_runner` does not exist.

-[] **Step 3: Implement the runner**

Create `airflow/plugins/__init__.py` empty.

Create `airflow/plugins/pipeline_runner.py`:

```python
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(os.environ.get("PROJECT_ROOT", "/opt/project")).resolve()


def build_crawler_command(module: str, args: dict[str, Any]) -> list[str]:
    cmd: list[str] = [sys.executable, "-m", module]
    for flag, value in args.items():
        if isinstance(value, list):
            cmd.append(flag)
            cmd.extend(str(item) for item in value)
        elif value is None or value == "":
            continue
        else:
            cmd.extend([flag, str(value)])
    return cmd


def run_crawler(module: str, args: dict[str, Any], cwd: Path | None = None, timeout: int = 7200) -> str:
    cmd = build_crawler_command(module, args)
    completed = subprocess.run(
        cmd,
        cwd=str(cwd or REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"{module} exit code {completed.returncode}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    return completed.stdout


def run_listings_ingestion(csv_path: str, batch_size: int = 50) -> dict[str, int]:
    sys.path.insert(0, str(REPO_ROOT))
    sys.path.insert(0, str(REPO_ROOT / "backend"))
    import asyncio

    from data_pipeline.ingestors.listings_ingestor import load_csv_to_db

    return asyncio.run(load_csv_to_db(csv_path, batch_size=batch_size))


def run_projects_ingestion(csv_path: str, batch_size: int = 25) -> dict[str, int]:
    sys.path.insert(0, str(REPO_ROOT))
    sys.path.insert(0, str(REPO_ROOT / "backend"))
    import asyncio
    import csv as csvlib

    from data_pipeline.ingestors.projects_ingestor import ingest_project_rows

    with open(csv_path, newline="", encoding="utf-8-sig") as handle:
        rows = list(csvlib.DictReader(handle))
    return asyncio.run(ingest_project_rows(rows, batch_size=batch_size))


def run_news_ingestion(csv_path: str) -> dict[str, int]:
    sys.path.insert(0, str(REPO_ROOT))
    sys.path.insert(0, str(REPO_ROOT / "backend"))
    import asyncio
    import csv as csvlib

    from data_pipeline.ingestors.news_ingestor import ingest_article_rows

    with open(csv_path, newline="", encoding="utf-8-sig") as handle:
        rows = list(csvlib.DictReader(handle))
    return asyncio.run(ingest_article_rows(rows))
```

- [ ] **Step 4: Run runner tests**

```powershell
cd backend
python -m pytest tests/test_pipeline_runner.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add airflow/plugins backend/tests/test_pipeline_runner.py
git commit -m "add airflow pipeline runner helpers"
```

---

### Task 3: Slack Failure Alerting

**Files:**
- Create: `airflow/plugins/alerting.py`
- Test: `backend/tests/test_alerting.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_alerting.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "airflow"))

from plugins.alerting import build_failure_payload


def test_build_failure_payload_contains_dag_and_task_ids():
    context = {
        "dag": type("D", (), {"dag_id": "daily_listings_dag"})(),
        "task_instance": type("T", (), {"task_id": "crawl_sale_urls", "log_url": "http://airflow/log"})(),
        "execution_date": "2026-06-02T02:00:00+07:00",
    }

    payload = build_failure_payload(context)

    assert "daily_listings_dag" in payload["text"]
    assert "crawl_sale_urls" in payload["text"]
    assert "http://airflow/log" in payload["text"]
```

- [ ] **Step 2: Run the test and confirm failure**

```powershell
cd backend
python -m pytest tests/test_alerting.py -q
```

Expected: fail because `plugins.alerting` does not exist.

- [ ] **Step 3: Implement alerting**

Create `airflow/plugins/alerting.py`:

```python
from __future__ import annotations

import os
from typing import Any

import httpx


def build_failure_payload(context: dict[str, Any]) -> dict:
    dag_id = context["dag"].dag_id
    task_id = context["task_instance"].task_id
    log_url = getattr(context["task_instance"], "log_url", "")
    execution_date = context.get("execution_date", "?")
    return {
        "text": (
            f":rotating_light: Airflow task failed\n"
            f"DAG: `{dag_id}`\n"
            f"Task: `{task_id}`\n"
            f"Run: `{execution_date}`\n"
            f"Logs: {log_url}"
        )
    }


def slack_failure_callback(context: dict[str, Any]) -> None:
    webhook = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook:
        return
    payload = build_failure_payload(context)
    try:
        httpx.post(webhook, json=payload, timeout=10).raise_for_status()
    except Exception:
        pass
```

- [ ] **Step 4: Run alerting test**

```powershell
cd backend
python -m pytest tests/test_alerting.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add airflow/plugins/alerting.py backend/tests/test_alerting.py
git commit -m "add airflow slack failure callback"
```

---

### Task 4: Daily Listings DAG (sale + rent)

**Files:**
- Create: `airflow/dags/daily_listings_dag.py`

- [ ] **Step 1: Implement the DAG**

```python
from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.models import Variable
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.utils.task_group import TaskGroup

from plugins.alerting import slack_failure_callback
from plugins.pipeline_runner import (
    REPO_ROOT,
    run_crawler,
    run_listings_ingestion,
)


def _alert_emails() -> list[str]:
    raw = os.environ.get("ALERT_EMAIL_RECIPIENTS", "")
    return [item.strip() for item in raw.split(",") if item.strip()]


DEFAULT_ARGS = {
    "owner": "data",
    "depends_on_past": False,
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=30),
    "email": _alert_emails(),
    "email_on_failure": bool(_alert_emails()),
    "email_on_retry": False,
    "on_failure_callback": slack_failure_callback,
}


def _last_crawl_var(source: str) -> str:
    return f"last_{source}_crawl_at"


def _read_since(source: str) -> str | None:
    return Variable.get(_last_crawl_var(source), default_var=None)


def _store_now(source: str, **_) -> None:
    Variable.set(_last_crawl_var(source), datetime.utcnow().date().isoformat())


def _crawl_urls(source: str, base_module: str, **_):
    since = _read_since(source)
    output = str(REPO_ROOT / f"data/raw/{source}_urls.csv")
    args = {"--pages": ["1", "30"], "--output": output, "--workers": "4"}
    if since:
        args["--since"] = since
    run_crawler(module=f"{base_module}.crawl_urls", args=args)


def _crawl_details(source: str, base_module: str, **_):
    input_csv = str(REPO_ROOT / f"data/raw/{source}_urls.csv")
    output_csv = str(REPO_ROOT / f"data/raw/{source}_details.csv")
    run_crawler(
        module=f"{base_module}.crawl_details",
        args={"--input": input_csv, "--output": output_csv, "--workers": "4"},
    )


def _ingest(source: str, **_):
    csv_path = str(REPO_ROOT / f"data/raw/{source}_details.csv")
    return run_listings_ingestion(csv_path, batch_size=50)


with DAG(
    dag_id="daily_listings_dag",
    description="Crawl + ingest sale and rent listings daily, then deactivate expired listings",
    default_args=DEFAULT_ARGS,
    schedule_interval="0 2 * * *",
    start_date=datetime(2026, 5, 25),
    catchup=False,
    max_active_runs=1,
    tags=["realestate", "listings"],
) as dag:
    source_groups = []
    for source, base_module in (("sale", "crawler.sale"), ("rent", "crawler.rent")):
        with TaskGroup(group_id=source) as group:
            crawl_urls = PythonOperator(
                task_id=f"crawl_{source}_urls",
                python_callable=_crawl_urls,
                op_kwargs={"source": source, "base_module": base_module},
            )
            crawl_details = PythonOperator(
                task_id=f"crawl_{source}_details",
                python_callable=_crawl_details,
                op_kwargs={"source": source, "base_module": base_module},
            )
            ingest = PythonOperator(
                task_id=f"ingest_{source}",
                python_callable=_ingest,
                op_kwargs={"source": source},
            )
            mark_done = PythonOperator(
                task_id=f"mark_{source}_done",
                python_callable=_store_now,
                op_kwargs={"source": source},
            )
            crawl_urls >> crawl_details >> ingest >> mark_done
        source_groups.append(group)

    mark_active = PostgresOperator(
        task_id="mark_active",
        postgres_conn_id="realestate_app",
        sql="""
            UPDATE listings
               SET is_active = false,
                   updated_at = NOW()
             WHERE is_active = true
               AND expiry_date IS NOT NULL
               AND expiry_date <> ''
               AND (
                    -- expiry_date stored as 'DD/MM/YYYY'
                    CASE WHEN expiry_date ~ '^\\d{2}/\\d{2}/\\d{4}$'
                         THEN to_date(expiry_date, 'DD/MM/YYYY') < CURRENT_DATE
                         WHEN expiry_date ~ '^\\d{4}-\\d{2}-\\d{2}$'
                         THEN to_date(expiry_date, 'YYYY-MM-DD') < CURRENT_DATE
                         ELSE false
                    END
               );
        """,
    )

    for group in source_groups:
        group >> mark_active
```

The `realestate_app` Postgres connection must be created in the Airflow UI before the first run (Admin → Connections → Add): host `realestate_postgres`, port `5432`, login `admin`, password `${POSTGRES_PASSWORD}`, schema `realestate`. Step 2 below verifies the DAG parses; the connection setup is part of the verification step in Task 8.

- [ ] **Step 2: Verify DAG parses**

```powershell
docker compose -f airflow\docker-compose.airflow.yml run --rm airflow_scheduler python -c "from airflow.models import DagBag; bag = DagBag(); assert 'daily_listings_dag' in bag.dags, bag.import_errors; print('ok')"
```

Expected: prints `ok`.

- [ ] **Step 3: Commit**

```powershell
git add airflow/dags/daily_listings_dag.py
git commit -m "add daily listings dag"
```

---

### Task 5: Weekly Projects DAG

**Files:**
- Create: `airflow/dags/weekly_projects_dag.py`

- [ ] **Step 1: Implement the DAG**

```python
from __future__ import annotations

import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

from plugins.alerting import slack_failure_callback
from plugins.pipeline_runner import REPO_ROOT, run_crawler, run_projects_ingestion


def _alert_emails() -> list[str]:
    raw = os.environ.get("ALERT_EMAIL_RECIPIENTS", "")
    return [item.strip() for item in raw.split(",") if item.strip()]


DEFAULT_ARGS = {
    "owner": "data",
    "retries": 3,
    "retry_delay": timedelta(minutes=10),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(hours=1),
    "email": _alert_emails(),
    "email_on_failure": bool(_alert_emails()),
    "email_on_retry": False,
    "on_failure_callback": slack_failure_callback,
}


def _crawl_project_urls(**_):
    output = str(REPO_ROOT / "data/raw/projects_urls.csv")
    run_crawler(
        module="crawler.projects.crawl_urls",
        args={"--pages": ["1", "20"], "--output": output, "--workers": "3"},
    )


def _crawl_project_details(**_):
    run_crawler(
        module="crawler.projects.crawl_details",
        args={
            "--input": str(REPO_ROOT / "data/raw/projects_urls.csv"),
            "--output": str(REPO_ROOT / "data/raw/projects_details.csv"),
            "--workers": "3",
        },
    )


def _ingest_projects(**_):
    return run_projects_ingestion(str(REPO_ROOT / "data/raw/projects_details.csv"))


with DAG(
    dag_id="weekly_projects_dag",
    description="Crawl + ingest real estate projects weekly",
    default_args=DEFAULT_ARGS,
    schedule_interval="0 3 * * 0",
    start_date=datetime(2026, 5, 25),
    catchup=False,
    max_active_runs=1,
    tags=["realestate", "projects"],
) as dag:
    crawl_urls = PythonOperator(task_id="crawl_project_urls", python_callable=_crawl_project_urls)
    crawl_details = PythonOperator(task_id="crawl_project_details", python_callable=_crawl_project_details)
    ingest = PythonOperator(task_id="ingest_projects", python_callable=_ingest_projects)
    crawl_urls >> crawl_details >> ingest
```

- [ ] **Step 2: Verify DAG parses**

```powershell
docker compose -f airflow\docker-compose.airflow.yml run --rm airflow_scheduler python -c "from airflow.models import DagBag; bag = DagBag(); assert 'weekly_projects_dag' in bag.dags, bag.import_errors; print('ok')"
```

Expected: prints `ok`.

- [ ] **Step 3: Commit**

```powershell
git add airflow/dags/weekly_projects_dag.py
git commit -m "add weekly projects dag"
```

---

### Task 6: Weekly News DAG

**Files:**
- Create: `airflow/dags/weekly_news_dag.py`

- [] **Step 1: Implement the DAG**

```python
from __future__ import annotations

import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

from plugins.alerting import slack_failure_callback
from plugins.pipeline_runner import REPO_ROOT, run_crawler, run_news_ingestion


def _alert_emails() -> list[str]:
    raw = os.environ.get("ALERT_EMAIL_RECIPIENTS", "")
    return [item.strip() for item in raw.split(",") if item.strip()]


DEFAULT_ARGS = {
    "owner": "data",
    "retries": 3,
    "retry_delay": timedelta(minutes=10),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(hours=1),
    "email": _alert_emails(),
    "email_on_failure": bool(_alert_emails()),
    "email_on_retry": False,
    "on_failure_callback": slack_failure_callback,
}


def _crawl_news(**_):
    run_crawler(
        module="crawler.news.crawl_articles",
        args={
            "--pages": ["1", "10"],
            "--output": str(REPO_ROOT / "data/raw/news_articles.csv"),
            "--workers": "2",
        },
    )


def _ingest_news(**_):
    return run_news_ingestion(str(REPO_ROOT / "data/raw/news_articles.csv"))


with DAG(
    dag_id="weekly_news_dag",
    description="Crawl + ingest real estate news weekly",
    default_args=DEFAULT_ARGS,
    schedule_interval="0 4 * * 0",
    start_date=datetime(2026, 5, 25),
    catchup=False,
    max_active_runs=1,
    tags=["realestate", "news"],
) as dag:
    crawl = PythonOperator(task_id="crawl_news", python_callable=_crawl_news)
    ingest = PythonOperator(task_id="ingest_news", python_callable=_ingest_news)
    crawl >> ingest
```

- [ ] **Step 2: Verify DAG parses**

```powershell
docker compose -f airflow\docker-compose.airflow.yml run --rm airflow_scheduler python -c "from airflow.models import DagBag; bag = DagBag(); assert 'weekly_news_dag' in bag.dags, bag.import_errors; print('ok')"
```

Expected: prints `ok`.

- [ ] **Step 3: Commit**

```powershell
git add airflow/dags/weekly_news_dag.py
git commit -m "add weekly news dag"
```

---

### Task 7: DAG Structure Tests

**Files:**
- Test: `backend/tests/test_dag_structure.py`

- [ ] **Step 1: Write the structure test**

Create `backend/tests/test_dag_structure.py`:

```python
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
AIRFLOW_DIR = REPO_ROOT / "airflow"

if str(AIRFLOW_DIR) not in sys.path:
    sys.path.insert(0, str(AIRFLOW_DIR))


@pytest.fixture(scope="module")
def dagbag():
    pytest.importorskip("airflow")

    os.environ.setdefault("AIRFLOW__CORE__LOAD_EXAMPLES", "false")
    os.environ.setdefault("PROJECT_ROOT", str(REPO_ROOT))

    from airflow.models import DagBag

    return DagBag(dag_folder=str(AIRFLOW_DIR / "dags"), include_examples=False)


def test_no_import_errors(dagbag):
    assert dagbag.import_errors == {}, dagbag.import_errors


def test_expected_dags_loaded(dagbag):
    expected = {"daily_listings_dag", "weekly_projects_dag", "weekly_news_dag"}
    assert expected.issubset(dagbag.dags.keys())


def test_daily_listings_has_sale_and_rent_groups(dagbag):
    dag = dagbag.dags["daily_listings_dag"]
    task_ids = {task.task_id for task in dag.tasks}
    assert "sale.crawl_sale_urls" in task_ids
    assert "sale.ingest_sale" in task_ids
    assert "rent.crawl_rent_urls" in task_ids
    assert "rent.ingest_rent" in task_ids
    assert "mark_active" in task_ids


def test_mark_active_runs_after_both_groups(dagbag):
    dag = dagbag.dags["daily_listings_dag"]
    mark_active = dag.get_task("mark_active")
    upstream_ids = {task.task_id for task in mark_active.upstream_list}
    assert "sale.mark_sale_done" in upstream_ids
    assert "rent.mark_rent_done" in upstream_ids


def test_retry_policy_applied(dagbag):
    dag = dagbag.dags["weekly_projects_dag"]
    for task in dag.tasks:
        assert task.retries == 3
        assert task.retry_exponential_backoff is True
```

- [ ] **Step 2: Run the test**

```powershell
cd backend
python -m pytest tests/test_dag_structure.py -q
```

Expected: pass when Airflow is installed in the virtualenv used for tests; skipped otherwise (`pytest.importorskip`).

If running locally without Airflow installed in the host venv, run inside the Airflow container:

```powershell
docker compose -f airflow\docker-compose.airflow.yml run --rm airflow_scheduler python -m pytest /opt/project/backend/tests/test_dag_structure.py -q
```

- [ ] **Step 3: Commit**

```powershell
git add backend/tests/test_dag_structure.py
git commit -m "test dag structure"
```

---

### Task 8: M3 End-To-End Verification

**Files:**
- No required code changes unless a previous task failed verification.

- [ ] **Step 1: Bring up the Airflow stack**

```powershell
cd airflow
copy .env.example .env
# Generate fernet key and paste into AIRFLOW_FERNET_KEY in .env
docker compose -f docker-compose.airflow.yml up -d
```

Expected: `docker compose -f airflow\docker-compose.airflow.yml ps` shows `airflow_webserver`, `airflow_scheduler`, `airflow_worker`, `airflow_postgres`, `airflow_redis` all healthy.

- [ ] **Step 2: Open Airflow UI**

Open `http://localhost:8080`. Login `admin` / `admin`.

Expected: three DAGs visible — `daily_listings_dag`, `weekly_projects_dag`, `weekly_news_dag` — all paused.

- [ ] **Step 3: Create the `realestate_app` Postgres connection**

In Airflow UI: Admin → Connections → Add a new record:

- Conn Id: `realestate_app`
- Conn Type: `Postgres`
- Host: `realestate_postgres`
- Schema: `realestate`
- Login: `admin`
- Password: value of `${POSTGRES_PASSWORD}` from `.env`
- Port: `5432`

Click Save. The `mark_active` task in `daily_listings_dag` uses this connection.

- [ ] **Step 4: Trigger daily_listings_dag manually**

In the UI, unpause `daily_listings_dag` and click Trigger DAG.

Expected: 9 tasks (4 per source × 2 sources + `mark_active`) all turn green within their timeouts. Watch `crawl_sale_urls` logs to confirm the Playwright subprocess runs.

- [ ] **Step 5: Verify data landed and expired listings deactivated**

```powershell
docker exec -it realestate_postgres psql -U admin -d realestate -c "SELECT listing_type, is_active, COUNT(*) FROM listings GROUP BY listing_type, is_active;"
```

Expected: counts include `sale` and `rent` greater than zero, with non-zero `is_active=false` rows when any sample listings have expired `expiry_date`.

- [ ] **Step 6: Trigger weekly_projects_dag and weekly_news_dag manually**

For each weekly DAG, unpause and trigger once. Confirm tasks turn green and the corresponding tables (`projects`, `articles`) gain rows.

- [ ] **Step 7: Confirm Airflow Variable was written**

```powershell
docker compose -f airflow\docker-compose.airflow.yml exec airflow_scheduler airflow variables list
```

Expected: `last_sale_crawl_at`, `last_rent_crawl_at` present with today's date.

- [ ] **Step 8: Force a failure to test alerting (optional)**

Temporarily break `crawler.sale.crawl_urls` (e.g. inject `raise SystemExit(2)` at the top of `main`). Trigger the DAG. Confirm Slack receives the failure card if `SLACK_WEBHOOK_URL` is set, that an email arrives if `ALERT_EMAIL_RECIPIENTS` and `SMTP_*` are configured, otherwise just confirm the failure shows up in UI with retry attempts.

Revert the change before committing.

- [ ] **Step 9: Commit verification fixes**

If any verification step required code changes:

```powershell
git add <changed-files>
git commit -m "fix m3 verification issues"
```

---

## Self-Review

- Spec coverage: M3 ships the Airflow Docker stack with LocalExecutor (Task 1), shared subprocess + ingestion runner (Task 2), Slack failure callback plus Airflow native email alerts (Task 3), the three production DAGs with `mark_active` deactivating expired listings after both source groups complete (Tasks 4–6), structural DAG tests including the `mark_active` wiring (Task 7), and end-to-end verification covering the new Postgres connection setup (Task 8). Master plan items left for later milestones: legal/PDF DAG (M4), monitoring dashboards and Celery scale-out (M5).
- Placeholder scan: every step lists concrete commands and code blocks. The fernet key in `.env.example` is intentionally an instruction string, not a real key — operators must generate one. The Slack webhook URL and SMTP/email recipients default empty so both alert channels are safe no-ops when unset.
- Type consistency: pipeline runner returns `dict[str, int]` for ingestion tasks (matching M1 ingestor return type); DAG retry config is identical across DAGs by reusing `DEFAULT_ARGS` plus the shared `_alert_emails()` helper; `mark_active` reuses the existing `realestate_app` Postgres connection instead of opening a new SQLAlchemy session.
- Pipeline pattern note: master plan calls for `crawl_urls → crawl_details → clean → enrich → load_db → chunk_and_embed → mark_active`. M3 collapses `clean → enrich → load_db → chunk_and_embed` into one `ingest_<source>` task because the M2 ingestor runs them in a single transaction; `mark_active` is preserved as its own downstream task gated on every source group finishing.
- Known limits accepted in M3: Playwright still runs inside the scheduler container under LocalExecutor with a 3 GB memory limit — adjust if scaling pages > 30/day. The structure test relies on `pytest.importorskip("airflow")`, so without Airflow installed the test is skipped rather than failing CI. Switching to CeleryExecutor + a worker container is a deliberate future change once daily volume warrants horizontal scaling.
