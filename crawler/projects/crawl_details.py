"""
Crawl detail pages for projects scraped by `crawler.projects.crawl_urls`.

NOTE: Selectors are SCAFFOLDS. The project detail DOM differs from the
listing detail DOM, so the field extraction logic in ``parse_detail_page``
is intentionally left as a TODO. The CLI, CSV columns, and Playwright
boilerplate ARE finalized so that other parts of the pipeline (CSV
shape, ingestor input contract) can rely on them today.

Output CSV columns:
    slug, name, developer, location, district, city,
    total_units, price_range, area_range, status, project_type,
    description, amenities (JSON-encoded list), url
"""

import argparse
import csv
import glob
import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from playwright.sync_api import sync_playwright, Browser
from playwright_stealth import Stealth

from crawler.core.csv_writer import append_csv, merge_tmp_files, read_done_ids

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
BROWSER_RESTART_EVERY = 15

DETAIL_FIELDS = [
    "slug",
    "name",
    "developer",
    "location",
    "district",
    "city",
    "total_units",
    "price_range",
    "area_range",
    "status",
    "project_type",
    "description",
    "amenities",  # JSON-encoded list
    "url",
]

_print_lock = threading.Lock()


def _log(msg: str) -> None:
    with _print_lock:
        print(msg, flush=True)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_detail_page(page, url: str, slug: str) -> dict | None:
    """Extract project detail fields.

    TODO: implement project detail selectors. Until then, this returns
    ``None`` so workers don't write empty rows. The CSV column contract is
    fixed by ``DETAIL_FIELDS`` above; future selector work should populate
    that shape and return the dict.
    """
    return None  # signal "not implemented" so workers don't write empty rows


# ---------------------------------------------------------------------------
# Crawling
# ---------------------------------------------------------------------------

def crawl_detail(
    browser: Browser,
    url: str,
    slug: str,
    stealth_obj: Stealth,
    retries: int = 2,
) -> dict | None:
    """Load a project detail page and extract data."""
    for attempt in range(retries + 1):
        ctx = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1920, "height": 1080},
        )
        page = ctx.new_page()
        stealth_obj.apply_stealth_sync(page)
        try:
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            time.sleep(2 + random.random())
            return parse_detail_page(page, url, slug)
        except Exception as e:
            if attempt < retries:
                _log(f"  [RETRY] {slug} error: {e}, attempt {attempt + 1}")
                time.sleep(3 + random.random() * 2)
            else:
                _log(f"  [ERROR] {slug} failed after {retries + 1} attempts: {e}")
        finally:
            ctx.close()

    return None


def worker_fn(
    worker_id: int,
    url_list: list[dict],
    tmp_path: str,
) -> int:
    stealth_obj = Stealth()
    total_written = 0
    consecutive_errors = 0

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        pages_since_restart = 0

        for i, entry in enumerate(url_list):
            if pages_since_restart >= BROWSER_RESTART_EVERY:
                browser.close()
                browser = pw.chromium.launch(headless=True)
                pages_since_restart = 0

            url = entry["url"]
            slug = entry["slug"]

            row = crawl_detail(browser, url, slug, stealth_obj)
            pages_since_restart += 1

            if row:
                append_csv(tmp_path, [row], DETAIL_FIELDS)
                total_written += 1
                consecutive_errors = 0
                _log(
                    f"  [W{worker_id}] {i + 1}/{len(url_list)} "
                    f"slug={slug} OK | total: {total_written}"
                )
            else:
                consecutive_errors += 1
                _log(
                    f"  [W{worker_id}] {i + 1}/{len(url_list)} "
                    f"slug={slug} FAILED | errors: {consecutive_errors}"
                )

            if consecutive_errors >= 5:
                _log(f"  [W{worker_id}] {consecutive_errors} consecutive errors, pausing 30s...")
                time.sleep(30)
                browser.close()
                browser = pw.chromium.launch(headless=True)
                pages_since_restart = 0
                consecutive_errors = 0

            time.sleep(1.5 + random.random() * 1.5)

        browser.close()

    return total_written


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def _read_input_urls(input_file: str) -> list[dict]:
    urls: list[dict] = []
    with open(input_file, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("url") and row.get("slug"):
                urls.append({"slug": row["slug"], "url": row["url"]})
    return urls


def _read_done_slugs_with_tmp(output: str) -> set[str]:
    done = set(read_done_ids(output, key="slug"))
    pattern = f"{output}.worker*.tmp"
    for tmp in glob.glob(pattern):
        try:
            with open(tmp, newline="", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    slug = row.get("slug", "")
                    if slug:
                        done.add(slug)
        except Exception:
            pass
    return done


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Crawl project detail pages from batdongsan.com.vn/du-an"
    )
    parser.add_argument(
        "--input", default="data/raw/project_urls.csv",
        help="Input CSV with slug,url columns (default: data/raw/project_urls.csv)",
    )
    parser.add_argument(
        "--output", default="data/raw/project_details.csv",
        help="Output CSV file (default: data/raw/project_details.csv)",
    )
    parser.add_argument(
        "--workers", type=int, default=4,
        help="Parallel workers (default: 4, each runs its own browser)",
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Max URLs to crawl (0 = all). Useful for testing.",
    )
    args = parser.parse_args()

    input_path = args.input if os.path.isabs(args.input) else os.path.normpath(os.path.abspath(args.input))
    output_path = args.output if os.path.isabs(args.output) else os.path.normpath(os.path.abspath(args.output))

    if not os.path.exists(input_path):
        print(f"[ERROR] Input file not found: {input_path}")
        return

    print("[NOTE] Project detail selectors are TODO. parse_detail_page returns None")
    print("       so this run will not write rows until selectors are implemented.")

    all_urls = _read_input_urls(input_path)
    print(f"Loaded {len(all_urls)} project URLs from {input_path}")

    done_slugs = _read_done_slugs_with_tmp(output_path)
    if done_slugs:
        print(f"Resuming: {len(done_slugs)} already crawled, skipping them")
    pending = [u for u in all_urls if u["slug"] not in done_slugs]

    if args.limit > 0:
        pending = pending[: args.limit]
        print(f"Limited to {args.limit} URLs")

    if not pending:
        print("Nothing to crawl - all URLs already done!")
        return

    print(f"Crawling {len(pending)} projects with {args.workers} workers -> {output_path}")

    num_workers = min(args.workers, len(pending))
    chunk_size = (len(pending) + num_workers - 1) // num_workers
    chunks = [pending[i : i + chunk_size] for i in range(0, len(pending), chunk_size)]

    for i, chunk in enumerate(chunks):
        print(f"  W{i}: {len(chunk)} projects")

    if not done_slugs:
        tmp_pattern = f"{output_path}.worker*.tmp"
        for stale in glob.glob(tmp_pattern):
            os.remove(stale)
            print(f"  Removed stale {stale}")

    total = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=num_workers) as pool:
        futures = {
            pool.submit(worker_fn, i, chunk, f"{output_path}.worker{i}.tmp"): i
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

    elapsed = time.time() - t0
    print(f"\nCrawling finished in {elapsed:.0f}s ({total} new projects)")

    tmp_pattern = f"{output_path}.worker*.tmp"
    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        carry_path = f"{output_path}.workerCARRY.tmp"
        os.replace(output_path, carry_path)

    final_count = merge_tmp_files(tmp_pattern, output_path, DETAIL_FIELDS, dedupe_key="slug")

    for tmp in glob.glob(tmp_pattern):
        os.remove(tmp)

    print(f"Done! {final_count} total unique projects saved to {output_path}")


if __name__ == "__main__":
    main()
