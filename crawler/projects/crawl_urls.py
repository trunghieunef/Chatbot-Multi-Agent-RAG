"""
Crawl real estate project URLs from batdongsan.com.vn/du-an.

Selectors are fixture-backed and intentionally kept in pure parser helpers so
they can be tested without launching Playwright. Live DOM and anti-bot behavior
can still change, so run small smoke crawls before relying on large batches.

Modeled on `crawler/sale/crawl_urls.py`. When selectors are wired up,
keep the same structure: parallel ThreadPoolExecutor workers, each
running its own Chromium with stealth, writing to per-worker tmp files
that are merged + deduplicated at the end.
"""

import argparse
import glob
import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, Browser
from playwright_stealth import Stealth

from crawler.core.csv_writer import append_csv, merge_tmp_files

BASE_URL = "https://batdongsan.com.vn/du-an"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
BROWSER_RESTART_EVERY = 20  # restart browser every N pages to limit memory growth

FIELDS = [
    "slug",
    "name",
    "url",
]

_print_lock = threading.Lock()


def _log(msg: str) -> None:
    with _print_lock:
        print(msg, flush=True)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _slug_from_project_url(url: str) -> str:
    return url.rstrip("/").split("/")[-1]


def extract_project_urls(html: str, *, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    main_left = soup.select_one(".re__project-main-left")
    if main_left is None:
        return []

    urls: list[str] = []
    for anchor in main_left.select("a[href]"):
        href = anchor.get("href") or ""
        if "/du-an/" not in href and "/du-an-" not in href:
            continue
        absolute = urljoin(base_url, href)
        if absolute not in urls:
            urls.append(absolute)
    return urls


def parse_project_listing(html: str, *, base_url: str) -> list[dict]:
    rows: list[dict] = []
    for url in extract_project_urls(html, base_url=base_url):
        rows.append({"slug": _slug_from_project_url(url), "name": "", "url": url})
    return rows


# ---------------------------------------------------------------------------
# Crawling
# ---------------------------------------------------------------------------

def crawl_page(browser: Browser, page_num: int, stealth_obj: Stealth, retries: int = 2) -> list[dict]:
    """Load a single project listing page and extract project URL rows."""
    url = BASE_URL if page_num == 1 else f"{BASE_URL}/p{page_num}"

    for attempt in range(retries + 1):
        ctx = browser.new_context(user_agent=USER_AGENT, viewport={"width": 1920, "height": 1080})
        page = ctx.new_page()
        stealth_obj.apply_stealth_sync(page)
        try:
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            time.sleep(2)
            rows = parse_project_listing(page.content(), base_url=BASE_URL)
            if rows:
                return rows
            if attempt < retries:
                _log(f"  [RETRY] p{page_num} empty, attempt {attempt + 1}")
                time.sleep(3)
        except Exception as e:
            if attempt < retries:
                _log(f"  [RETRY] p{page_num} error: {e}")
                time.sleep(3)
            else:
                _log(f"  [ERROR] p{page_num} failed: {e}")
        finally:
            ctx.close()

    return []


def worker_fn(worker_id: int, page_range: list[int], tmp_path: str) -> int:
    """Crawl assigned pages and append results to a worker-specific temp CSV."""
    stealth_obj = Stealth()
    seen_slugs: set[str] = set()
    total_written = 0
    consecutive_empty = 0

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        pages_since_restart = 0

        for pg in page_range:
            if pages_since_restart >= BROWSER_RESTART_EVERY:
                browser.close()
                browser = pw.chromium.launch(headless=True)
                pages_since_restart = 0

            rows = crawl_page(browser, pg, stealth_obj)
            pages_since_restart += 1

            new_rows = [r for r in rows if r.get("slug") and r["slug"] not in seen_slugs]
            seen_slugs.update(r["slug"] for r in new_rows)

            if new_rows:
                append_csv(tmp_path, new_rows, FIELDS)
                total_written += len(new_rows)

            _log(
                f"  [W{worker_id}] p{pg}: {len(rows)} found, "
                f"{len(new_rows)} new | total: {total_written}"
            )

            if not rows:
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    _log(f"  [W{worker_id}] 3 consecutive empty pages, stopping")
                    break
            else:
                consecutive_empty = 0

            time.sleep(1 + random.random())

        browser.close()

    return total_written


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Crawl project URL listings from batdongsan.com.vn/du-an"
    )
    parser.add_argument(
        "--pages", nargs=2, type=int, default=[1, 100],
        metavar=("START", "END"), help="page range (default: 1 100)",
    )
    parser.add_argument(
        "--output", default="data/raw/project_urls.csv",
        help="output CSV file (default: data/raw/project_urls.csv)",
    )
    parser.add_argument(
        "--workers", type=int, default=4, help="parallel workers (default: 4)",
    )
    args = parser.parse_args()

    start, end = args.pages
    num_workers = min(args.workers, end - start + 1)
    pages = list(range(start, end + 1))
    chunk_size = (len(pages) + num_workers - 1) // num_workers
    chunks = [pages[i : i + chunk_size] for i in range(0, len(pages), chunk_size)]

    print(
        f"Crawling project pages {start}-{end} "
        f"({len(pages)} pages, {num_workers} workers) -> {args.output}"
    )
    for i, chunk in enumerate(chunks):
        print(f"  W{i}: p{chunk[0]}-p{chunk[-1]} ({len(chunk)} pages)")

    # Clean up stale tmp files from a previous crashed run
    tmp_pattern = f"{args.output}.worker*.tmp"
    for stale in glob.glob(tmp_pattern):
        os.remove(stale)
        print(f"  Removed stale {stale}")

    total = 0
    with ThreadPoolExecutor(max_workers=num_workers) as pool:
        futures = {
            pool.submit(worker_fn, i, chunk, f"{args.output}.worker{i}.tmp"): i
            for i, chunk in enumerate(chunks)
        }
        for future in as_completed(futures):
            wid = futures[future]
            try:
                count = future.result()
                total += count
                print(f"  W{wid} done: {count} projects")
            except Exception as e:
                print(f"  W{wid} failed: {e}")

    final_count = merge_tmp_files(tmp_pattern, args.output, FIELDS, dedupe_key="slug")
    for tmp in glob.glob(tmp_pattern):
        os.remove(tmp)
    print(f"\nDone! {final_count} unique projects saved to {args.output}")


if __name__ == "__main__":
    main()
