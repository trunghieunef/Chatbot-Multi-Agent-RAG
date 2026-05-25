"""
Crawl real estate project URLs from batdongsan.com.vn/du-an.

NOTE: Selectors below are SCAFFOLDS. The project listing pages have a
different DOM than the regular listing pages and the field extraction
logic must be verified against the live DOM before this script is used
to crawl real data. Until that happens, the parser returns no rows
and this module exists primarily to fix the package layout, CLI flags,
and CSV columns.

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

def parse_card(card) -> dict | None:
    """Extract project card data.

    TODO: implement project listing card selectors. The /du-an pages do not
    share the `.js__card` / `.js__product-link-for-product-id` markup used
    by listing pages, so reuse from sale/crawl_urls is not safe.
    """
    # TODO: implement project selectors
    return None


# ---------------------------------------------------------------------------
# Crawling
# ---------------------------------------------------------------------------

def crawl_page(browser: Browser, page_num: int, stealth_obj: Stealth, retries: int = 2) -> list[dict]:
    """Load a single project listing page and extract cards.

    The Playwright launch + stealth + retry skeleton is wired up so the
    module is runnable; the actual card harvesting is gated on selector
    work (see ``parse_card``).
    """
    url = BASE_URL if page_num == 1 else f"{BASE_URL}/p{page_num}"

    for attempt in range(retries + 1):
        ctx = browser.new_context(user_agent=USER_AGENT, viewport={"width": 1920, "height": 1080})
        page = ctx.new_page()
        stealth_obj.apply_stealth_sync(page)
        try:
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            time.sleep(2)
            # TODO: replace with the verified project-card selector.
            cards = page.query_selector_all(".js__card")
            rows = [r for card in cards if (r := parse_card(card))]
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
    print("[NOTE] Project page selectors are TODO. This run will produce empty CSVs")
    print("       until parse_card / project listing markup is verified.")
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
