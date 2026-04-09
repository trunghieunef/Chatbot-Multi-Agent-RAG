"""
Crawl apartment listings from batdongsan.com.vn.

Uses Playwright (headless Chrome) with stealth to bypass bot detection.
Each page is loaded in a fresh browser context. Multiple workers crawl
different page ranges in parallel, each writing to its own temp file.
Results are merged and deduplicated at the end.
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

BASE_URL = "https://batdongsan.com.vn/nha-dat-ban"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
BROWSER_RESTART_EVERY = 20  # restart browser every N pages to limit memory growth

FIELDS = [
    
    "product_id",
    #"title",
    #"price_text",
    #"area_text",
    #"price_per_m2_text",
    #"bedrooms",
    #"bathrooms",
    #"location",
    #"description",
    #post_date",
    #"contact_name",
    "url",
    #"page_num",
]

_print_lock = threading.Lock()


def _log(msg: str):
    with _print_lock:
        print(msg, flush=True)


def _text(el) -> str:
    return el.inner_text().strip() if el else ""


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

        bed_el = card.query_selector(".re__card-config-bedroom")
        bath_el = card.query_selector(".re__card-config-toilet")
        date_el = card.query_selector(".re__card-published-info-published-at")

        location = _text(card.query_selector(".re__card-location"))
        if location.startswith("·"):
            location = location[1:].strip()

        return {
            "product_id": link.get_attribute("data-product-id") or "",
            #"title": (link.get_attribute("title") or "").strip(),
            #"price_text": _text(card.query_selector(".re__card-config-price")),
            #"area_text": _text(card.query_selector(".re__card-config-area")),
            #"price_per_m2_text": _text(card.query_selector(".re__card-config-price_per_m2")),
            #"bedrooms": bed_el.query_selector("span").inner_text().strip() if bed_el else "",
            #"bathrooms": bath_el.query_selector("span").inner_text().strip() if bath_el else "",
            #"location": location,
            #"description": _text(card.query_selector(".re__card-description")),
            #"post_date": (date_el.get_attribute("aria-label") or _text(date_el)) if date_el else "",
            #"contact_name": _text(card.query_selector(".agent-name")),
            "url": url,
            #"page_num": page_num,
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
                _append_csv(tmp_path, new_rows)
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
# CSV helpers
# ---------------------------------------------------------------------------

def _append_csv(path: str, rows: list[dict]):
    """Append rows to a CSV file, writing the header if the file is new."""
    write_header = not os.path.exists(path) or os.path.getsize(path) == 0
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


def _merge_tmp_files(pattern: str, output: str):
    """Read all matching tmp CSVs, deduplicate by product_id, write final output."""
    all_rows = []
    for tmp in sorted(glob.glob(pattern)):
        with open(tmp, newline="", encoding="utf-8") as f:
            all_rows.extend(csv.DictReader(f))

    all_rows.sort(key=lambda r: (int(r["page_num"]), r["product_id"]))

    seen: set[str] = set()
    deduped = []
    for r in all_rows:
        if r["product_id"] not in seen:
            seen.add(r["product_id"])
            deduped.append(r)

    with open(output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(deduped)

    for tmp in glob.glob(pattern):
        os.remove(tmp)

    return len(deduped)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Crawl apartment listings from batdongsan.com.vn"
    )
    parser.add_argument(
        "--pages", nargs=2, type=int, default=[1, 10223],
        metavar=("START", "END"), help="page range (default: 1 204281)",
    )
    parser.add_argument("--output", default="apartments.csv", help="output CSV file")
    parser.add_argument("--workers", type=int, default=8, help="parallel workers (default: 10)")
    args = parser.parse_args()

    start, end = args.pages
    num_workers = min(args.workers, end - start + 1)
    pages = list(range(start, end + 1))
    chunk_size = (len(pages) + num_workers - 1) // num_workers
    chunks = [pages[i : i + chunk_size] for i in range(0, len(pages), chunk_size)]

    print(f"Crawling pages {start}-{end} ({len(pages)} pages, {num_workers} workers) -> {args.output}")
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
    final_count = _merge_tmp_files(tmp_pattern, args.output)
    print(f"\nDone! {final_count} unique listings saved to {args.output}")


if __name__ == "__main__":
    main()
