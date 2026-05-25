"""
Crawl news articles from batdongsan.com.vn/tin-tuc.

NOTE: Selectors below are SCAFFOLDS. The article list page and the per-article
DOM are non-trivial: list pages render headline cards, and each article body
needs to be visited individually to extract title/body/post_date. The actual
selector logic must be verified against the live DOM before this script can be
used to crawl real data. Until that happens, ``parse_article_page`` returns
``None`` and this module exists primarily to fix the package layout, CLI flags,
and CSV columns so the downstream ingestor (``data_pipeline/ingestors/news_ingestor.py``)
can be developed and tested against a stable contract.

Modeled on ``crawler/projects/crawl_urls.py`` + ``crawl_details.py`` -
parallel ThreadPoolExecutor workers, each running its own Chromium with
stealth, writing to per-worker tmp files that are merged + deduplicated at the
end. Output CSV columns:

    title, body, category, post_date, url
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
from crawler.core.parser import text_or_empty  # noqa: F401  re-exported for selector use

BASE_URL = "https://batdongsan.com.vn/tin-tuc"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
BROWSER_RESTART_EVERY = 20  # restart browser every N pages to limit memory growth

FIELDS = [
    "title",
    "body",
    "category",
    "post_date",
    "url",
]

_print_lock = threading.Lock()


def _log(msg: str) -> None:
    with _print_lock:
        print(msg, flush=True)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_article_card(card) -> dict | None:
    """Extract minimal article-card fields (title + url) from a list page.

    TODO: implement article list-card selectors. The /tin-tuc list page does
    not share the listing-card markup used elsewhere on the site.
    """
    # TODO: implement article list-card selectors
    return None


def parse_article_page(page, url: str) -> dict | None:
    """Visit an article URL and extract ``title``, ``body``, ``post_date``.

    TODO: implement article-detail selectors. Returns ``None`` until the
    selectors for ``title``, ``body``, and ``post_date`` are verified against
    the live DOM. Output dict shape (when implemented):

        {
            "title": str,
            "body": str,
            "category": "news",
            "post_date": "YYYY-MM-DD",
            "url": str,
        }
    """
    # TODO: implement article-detail selectors
    return None


# ---------------------------------------------------------------------------
# Crawling
# ---------------------------------------------------------------------------

def crawl_list_page(browser: Browser, page_num: int, stealth_obj: Stealth, retries: int = 2) -> list[dict]:
    """Load a single article list page and extract article-card stubs.

    The Playwright launch + stealth + retry skeleton is wired up so the
    module is runnable; the actual card harvesting is gated on selector
    work (see ``parse_article_card``).
    """
    url = BASE_URL if page_num == 1 else f"{BASE_URL}/p{page_num}"

    for attempt in range(retries + 1):
        ctx = browser.new_context(user_agent=USER_AGENT, viewport={"width": 1920, "height": 1080})
        page = ctx.new_page()
        stealth_obj.apply_stealth_sync(page)
        try:
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            time.sleep(2)
            # TODO: replace with the verified article-card selector.
            cards = page.query_selector_all(".js__card")
            rows = [r for card in cards if (r := parse_article_card(card))]
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


def crawl_article(
    browser: Browser,
    url: str,
    stealth_obj: Stealth,
    retries: int = 2,
) -> dict | None:
    """Load an article detail page and extract title/body/post_date."""
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
            return parse_article_page(page, url)
        except Exception as e:
            if attempt < retries:
                _log(f"  [RETRY] {url} error: {e}, attempt {attempt + 1}")
                time.sleep(3 + random.random() * 2)
            else:
                _log(f"  [ERROR] {url} failed after {retries + 1} attempts: {e}")
        finally:
            ctx.close()

    return None


def worker_fn(worker_id: int, page_range: list[int], tmp_path: str) -> int:
    """Crawl assigned list pages, then visit each article URL, writing to a tmp CSV."""
    stealth_obj = Stealth()
    seen_urls: set[str] = set()
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

            cards = crawl_list_page(browser, pg, stealth_obj)
            pages_since_restart += 1

            new_cards = [c for c in cards if c.get("url") and c["url"] not in seen_urls]
            seen_urls.update(c["url"] for c in new_cards)

            page_written = 0
            for card in new_cards:
                article = crawl_article(browser, card["url"], stealth_obj)
                pages_since_restart += 1
                if article:
                    append_csv(tmp_path, [article], FIELDS)
                    page_written += 1
                time.sleep(1 + random.random())

            total_written += page_written
            _log(
                f"  [W{worker_id}] p{pg}: {len(cards)} cards, "
                f"{page_written} articles | total: {total_written}"
            )

            if not cards:
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
        description="Crawl news articles from batdongsan.com.vn/tin-tuc"
    )
    parser.add_argument(
        "--pages", nargs=2, type=int, default=[1, 50],
        metavar=("START", "END"), help="page range (default: 1 50)",
    )
    parser.add_argument(
        "--output", default="data/raw/news_articles.csv",
        help="output CSV file (default: data/raw/news_articles.csv)",
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
        f"Crawling news pages {start}-{end} "
        f"({len(pages)} pages, {num_workers} workers) -> {args.output}"
    )
    print("[NOTE] Article selectors are TODO. parse_article_page returns None")
    print("       so this run will not write rows until selectors are implemented.")
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
                print(f"  W{wid} done: {count} articles")
            except Exception as e:
                print(f"  W{wid} failed: {e}")

    final_count = merge_tmp_files(tmp_pattern, args.output, FIELDS, dedupe_key="url")
    for tmp in glob.glob(tmp_pattern):
        os.remove(tmp)
    print(f"\nDone! {final_count} unique articles saved to {args.output}")


if __name__ == "__main__":
    main()
