"""
Step 1: Crawl news article URLs from batdongsan.com.vn/tin-tuc.

This mirrors the listing/project crawler shape: list pages produce a durable
URL CSV first, then the detail crawler reads that artifact.
"""

from __future__ import annotations

import argparse
import glob
import os
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from playwright.sync_api import Browser, sync_playwright
from playwright_stealth import Stealth

from crawler.core.csv_writer import append_csv, merge_tmp_files

BASE_URL = "https://batdongsan.com.vn/tin-tuc"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
BROWSER_RESTART_EVERY = 20

FIELDS = ["url"]

NEWS_CATEGORY_SLUGS = {
    "thi-truong",
    "phan-tich-nhan-dinh",
    "thong-tin-quy-hoach",
    "chinh-sach-quan-ly",
    "bds-the-gioi",
    "tai-chinh-chung-khoan-bds",
    "loi-khuyen",
    "phong-thuy",
    "xay-dung",
    "kien-thuc",
}

_print_lock = threading.Lock()


def _log(msg: str) -> None:
    with _print_lock:
        print(msg, flush=True)


def _is_article_url(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    if not path:
        return False

    lowered_path = path.lower()
    if lowered_path in {"/tin-tuc", "/wiki"}:
        return False
    if "/tac-gia/" in lowered_path or "/tag/" in lowered_path:
        return False

    parts = [part for part in lowered_path.split("/") if part]
    if not parts:
        return False

    if parts[0] == "tin-tuc":
        if len(parts) < 2:
            return False
        if len(parts) == 2 and not re.search(r"-\d+$", parts[-1]):
            return False
        if len(parts) == 2 and parts[-1] in NEWS_CATEGORY_SLUGS:
            return False
        return True

    if parts[0] == "wiki":
        return len(parts) >= 2

    return False


def extract_article_urls(html: str, *, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    containers = soup.select(
        "main, article, .news-list, .re__news-list, .re__left-main-content, "
        "[data-testid='article-list']"
    )
    if not containers:
        containers = [soup]

    urls: list[str] = []
    for container in containers:
        for anchor in container.select("a[href]"):
            href = anchor.get("href") or ""
            absolute = urljoin(base_url, href)
            if not _is_article_url(absolute):
                continue
            if absolute not in urls:
                urls.append(absolute)
    return urls


def parse_article_listing(html: str, *, base_url: str) -> list[dict[str, str]]:
    return [{"url": url} for url in extract_article_urls(html, base_url=base_url)]


def crawl_page(browser: Browser, page_num: int, stealth_obj: Stealth, retries: int = 2) -> list[dict[str, str]]:
    url = BASE_URL if page_num == 1 else f"{BASE_URL}/p{page_num}"

    for attempt in range(retries + 1):
        ctx = browser.new_context(user_agent=USER_AGENT, viewport={"width": 1920, "height": 1080})
        page = ctx.new_page()
        stealth_obj.apply_stealth_sync(page)
        try:
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            time.sleep(2)
            rows = parse_article_listing(page.content(), base_url=BASE_URL)
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

            rows = crawl_page(browser, pg, stealth_obj)
            pages_since_restart += 1

            new_rows = [row for row in rows if row.get("url") and row["url"] not in seen_urls]
            seen_urls.update(row["url"] for row in new_rows)

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


def run(*, pages: tuple[int, int], output: str, workers: int) -> int:
    start, end = pages
    num_workers = min(workers, end - start + 1)
    page_nums = list(range(start, end + 1))
    chunk_size = (len(page_nums) + num_workers - 1) // num_workers
    chunks = [page_nums[i : i + chunk_size] for i in range(0, len(page_nums), chunk_size)]

    print(
        f"Crawling news URL pages {start}-{end} "
        f"({len(page_nums)} pages, {num_workers} workers) -> {output}"
    )
    for i, chunk in enumerate(chunks):
        print(f"  W{i}: p{chunk[0]}-p{chunk[-1]} ({len(chunk)} pages)")

    tmp_pattern = f"{output}.worker*.tmp"
    for stale in glob.glob(tmp_pattern):
        os.remove(stale)
        print(f"  Removed stale {stale}")

    total = 0
    with ThreadPoolExecutor(max_workers=num_workers) as pool:
        futures = {
            pool.submit(worker_fn, i, chunk, f"{output}.worker{i}.tmp"): i
            for i, chunk in enumerate(chunks)
        }
        for future in as_completed(futures):
            wid = futures[future]
            try:
                count = future.result()
                total += count
                print(f"  W{wid} done: {count} article URLs")
            except Exception as e:
                print(f"  W{wid} failed: {e}")

    final_count = merge_tmp_files(tmp_pattern, output, FIELDS, dedupe_key="url")
    for tmp in glob.glob(tmp_pattern):
        os.remove(tmp)
    print(f"\nDone! {final_count} unique article URLs saved to {output}")
    return final_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl news article URLs from batdongsan.com.vn/tin-tuc")
    parser.add_argument(
        "--pages", nargs=2, type=int, default=[1, 50],
        metavar=("START", "END"), help="page range (default: 1 50)",
    )
    parser.add_argument(
        "--output", default="data/raw/news_urls.csv",
        help="output CSV file (default: data/raw/news_urls.csv)",
    )
    parser.add_argument("--workers", type=int, default=4, help="parallel workers (default: 4)")
    args = parser.parse_args()

    run(pages=(args.pages[0], args.pages[1]), output=args.output, workers=args.workers)


if __name__ == "__main__":
    main()
