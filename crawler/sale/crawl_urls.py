"""
Crawl apartment listings from batdongsan.com.vn.

Uses Playwright (headless Chrome) with stealth to bypass bot detection.
Each page is loaded in a fresh browser context. Multiple workers crawl
different page ranges in parallel, each writing to its own temp file.
Results are merged and deduplicated at the end.
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
from crawler.core.parser import text_or_empty

BASE_URL = "https://batdongsan.com.vn/nha-dat-ban"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
BROWSER_RESTART_EVERY = 20  # restart browser every N pages to limit memory growth

FIELDS = [
    "product_id",
    "url",
]

_print_lock = threading.Lock()


def _log(msg: str):
    with _print_lock:
        print(msg, flush=True)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_card(card, page_num: int) -> dict | None:
    """Extract listing data from a single card element."""
    try:
        link = card.query_selector("a.js__product-link-for-product-id")
        if not link:
            return None

        href = link.get_attribute("href") or ""
        url = f"https://batdongsan.com.vn{href}" if href and not href.startswith("http") else href

        location = text_or_empty(card.query_selector(".re__card-location"))
        if location.startswith("·"):
            location = location[1:].strip()

        return {
            "product_id": link.get_attribute("data-product-id") or "",
            "url": url,
        }
    except Exception as e:
        _log(f"  [WARN] parse error: {e}")
        return None


# ---------------------------------------------------------------------------
# Crawling
# ---------------------------------------------------------------------------

def crawl_page(browser: Browser, page_num: int, stealth_obj: Stealth, retries: int = 2) -> list[dict]:
    """Load a single listing page in a fresh context and extract all cards."""
    url = BASE_URL if page_num == 1 else f"{BASE_URL}/p{page_num}"

    for attempt in range(retries + 1):
        ctx = browser.new_context(user_agent=USER_AGENT, viewport={"width": 1920, "height": 1080})
        page = ctx.new_page()
        stealth_obj.apply_stealth_sync(page)
        try:
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            time.sleep(2)
            cards = page.query_selector_all(".js__card")
            if cards:
                return [r for card in cards if (r := parse_card(card, page_num))]
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
    seen_ids: set[str] = set()
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

            new_rows = [r for r in rows if r["product_id"] not in seen_ids]
            seen_ids.update(r["product_id"] for r in new_rows)

            if new_rows:
                append_csv(tmp_path, new_rows, FIELDS)
                total_written += len(new_rows)

            _log(f"  [W{worker_id}] p{pg}: {len(rows)} found, {len(new_rows)} new | total: {total_written}")

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

def main():
    parser = argparse.ArgumentParser(
        description="Crawl apartment listings from batdongsan.com.vn"
    )
    parser.add_argument(
        "--pages", nargs=2, type=int, default=[1, 10223],
        metavar=("START", "END"), help="page range (default: 1 10223)",
    )
    parser.add_argument("--output", default="apartments.csv", help="output CSV file")
    parser.add_argument("--workers", type=int, default=8, help="parallel workers (default: 8)")
    parser.add_argument(
        "--since", default=None,
        help="Only keep rows with post_date >= YYYY-MM-DD when post_date is available "
             "(stored for later use; not applied at URL listing stage)",
    )
    args = parser.parse_args()

    start, end = args.pages
    num_workers = min(args.workers, end - start + 1)
    pages = list(range(start, end + 1))
    chunk_size = (len(pages) + num_workers - 1) // num_workers
    chunks = [pages[i : i + chunk_size] for i in range(0, len(pages), chunk_size)]

    print(f"Crawling pages {start}-{end} ({len(pages)} pages, {num_workers} workers) -> {args.output}")
    if args.since:
        print(f"  --since={args.since} (no-op for URL listing; stored for downstream use)")
    for i, chunk in enumerate(chunks):
        print(f"  W{i}: p{chunk[0]}-p{chunk[-1]} ({len(chunk)} pages)")

    # Clean up stale tmp files from a previous crashed run
    tmp_pattern = f"{args.output}.worker*.tmp"
    for stale in glob.glob(tmp_pattern):
        os.remove(stale)
        print(f"  Removed stale {stale}")

    # Launch workers
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
                print(f"  W{wid} done: {count} listings")
            except Exception as e:
                print(f"  W{wid} failed: {e}")

    # Merge and deduplicate
    final_count = merge_tmp_files(tmp_pattern, args.output, FIELDS)
    # Clean up tmp files after successful merge
    for tmp in glob.glob(tmp_pattern):
        os.remove(tmp)
    print(f"\nDone! {final_count} unique listings saved to {args.output}")


if __name__ == "__main__":
    main()
