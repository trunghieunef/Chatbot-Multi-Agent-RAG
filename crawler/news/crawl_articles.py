"""
Crawl news articles from batdongsan.com.vn/tin-tuc.

Selectors are fixture-backed and intentionally kept in pure parser helpers so
they can be tested without launching Playwright. Live DOM and anti-bot behavior
can still change, so run small smoke crawls before relying on large batches.

Modeled on ``crawler/projects/crawl_urls.py`` + ``crawl_details.py`` -
parallel ThreadPoolExecutor workers, each running its own Chromium with
stealth, writing to per-worker tmp files that are merged + deduplicated at the
end. Output CSV columns:

    title, body, category, source, post_date, url
"""

import argparse
import glob
import json
import os
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin

from bs4 import BeautifulSoup
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
    "author",
    "source",
    "post_date",
    "reading_time",
    "summary",
    "image_urls",
    "url",
]

_print_lock = threading.Lock()


def _log(msg: str) -> None:
    with _print_lock:
        print(msg, flush=True)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def extract_article_urls(html: str, *, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    for anchor in soup.select("a[href]"):
        href = anchor.get("href") or ""
        if "/tin-tuc/" not in href and "/wiki/" not in href:
            continue
        absolute = urljoin(base_url, href)
        if absolute not in urls:
            urls.append(absolute)
    return urls


def parse_article_listing(html: str, *, base_url: str) -> list[dict]:
    return [{"url": url} for url in extract_article_urls(html, base_url=base_url)]


def _text(soup: BeautifulSoup, selector: str) -> str:
    node = soup.select_one(selector)
    return " ".join(node.get_text(" ", strip=True).split()) if node else ""


def _clean_text(value: str) -> str:
    return " ".join((value or "").split())


def _article_main(soup: BeautifulSoup):
    return soup.select_one("main") or soup.select_one("article") or soup


def _article_images(container, *, base_url: str) -> list[str]:
    urls: list[str] = []
    for image in container.select("img"):
        src = image.get("data-src") or image.get("src") or ""
        if not src or src.startswith("data:"):
            continue
        absolute = urljoin(base_url, src)
        if absolute not in urls:
            urls.append(absolute)
    return urls


def _meta_after_text(container, label: str) -> str:
    for node in container.find_all(string=re.compile(re.escape(label), re.IGNORECASE)):
        own_text = _clean_text(str(node))
        if own_text and own_text.lower() != label.lower():
            return own_text
        current = node.parent
        while current:
            sibling = current.next_sibling
            while sibling:
                if hasattr(sibling, "get_text"):
                    text = _clean_text(sibling.get_text(" ", strip=True))
                else:
                    text = _clean_text(str(sibling))
                if text and text not in {"•"}:
                    return text
                sibling = sibling.next_sibling
            current = current.parent if current.parent is not container else None
    return ""


def _article_author(container) -> str:
    author_links = [
        _clean_text(anchor.get_text(" ", strip=True))
        for anchor in container.select('a[href*="/tac-gia/"]')
        if anchor.get_text(strip=True)
    ]
    return author_links[-1] if author_links else ""


def _article_body(container) -> tuple[str, str]:
    pieces: list[str] = []
    for node in container.find_all(["p", "figcaption", "h2", "h3"]):
        text = _clean_text(node.get_text(" ", strip=True))
        if not text:
            continue
        if node.name in {"h2", "h3"} and text.lower() in {
            "chia sẻ bài viết này",
            "bài viết được xem nhiều nhất",
            "bài viết khác",
        }:
            break
        if node.name in {"h2", "h3"}:
            continue
        pieces.append(text)
    summary = pieces[0] if pieces else ""
    return "\n".join(pieces), summary


def _category_from_text(category_text: str) -> str:
    lowered = category_text.lower()
    if "phap ly" in lowered or "pháp lý" in lowered:
        return "legal"
    if "thi truong" in lowered or "thị trường" in lowered:
        return "market"
    if "huong dan" in lowered or "hướng dẫn" in lowered:
        return "guide"
    return "news"


def parse_article(html: str, *, url: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    container = _article_main(soup)
    title = _text(container, "h1") or _text(soup, "h1") or _text(soup, "[data-testid='article-title']")
    body, summary = _article_body(container)
    category_text = _text(soup, ".breadcrumb a:last-child, [data-testid='category']")
    post_date = _text(soup, "time, .date, [data-testid='post-date']") or _meta_after_text(container, "Cập nhật lần cuối vào")
    return {
        "title": title,
        "body": body,
        "category": _category_from_text(category_text),
        "author": _article_author(container),
        "source": "batdongsan.com",
        "post_date": post_date,
        "reading_time": _meta_after_text(container, "Đọc trong khoảng"),
        "summary": summary,
        "image_urls": json.dumps(_article_images(container, base_url=url), ensure_ascii=False),
        "url": url,
    }


def parse_article_page(page, url: str) -> dict | None:
    """Visit an article URL and extract ``title``, ``body``, ``post_date``."""
    row = parse_article(page.content(), url=url)
    return row if row.get("title") and row.get("body") else None


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
