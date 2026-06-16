"""
Step 2: Crawl news article details from a URL CSV.

Reads URLs produced by ``crawler.news.crawl_urls`` and writes article content
rows compatible with ``data_pipeline.ingestors.news_ingestor``.
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import random
import re
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.sync_api import Browser, sync_playwright
from playwright_stealth import Stealth

from crawler.core.csv_writer import append_csv, merge_tmp_files, read_done_ids

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
BROWSER_RESTART_EVERY = 20
DATE_TEXT_RE = re.compile(
    r"\b(?:\d{1,2}/\d{1,2}/\d{4}(?:\s+\d{1,2}:\d{2})?|\d{4}-\d{2}-\d{2}(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?)\b"
)
SOURCE_PUBLISH_RE = re.compile(
    r"(?:Thời gian xuất bản|Thoi gian xuat ban)\s*:\s*(?:(\d{1,2})h(\d{2})\s*ngày\s*)?(\d{1,2}/\d{1,2}/\d{4})",
    re.IGNORECASE,
)

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


def _extract_date_text(value: str) -> str:
    text = _clean_text(value)
    if not text or len(text) > 120:
        return ""
    match = DATE_TEXT_RE.search(text)
    return match.group(0) if match else ""


def _extract_source_publish_date(value: str) -> str:
    text = _clean_text(value)
    match = SOURCE_PUBLISH_RE.search(text)
    if not match:
        return ""
    hour, minute, date_text = match.groups()
    if hour and minute:
        return f"{date_text} {int(hour):02d}:{minute}"
    return date_text


def _date_after_text(container, label: str) -> str:
    for node in container.find_all(string=re.compile(re.escape(label), re.IGNORECASE)):
        own_text = _clean_text(str(node))
        if own_text and own_text.lower() != label.lower():
            date_text = _extract_date_text(own_text)
            if date_text:
                return date_text
        current = node.parent
        while current:
            sibling = current.next_sibling
            while sibling:
                if hasattr(sibling, "get_text"):
                    text = _clean_text(sibling.get_text(" ", strip=True))
                else:
                    text = _clean_text(str(sibling))
                date_text = _extract_date_text(text)
                if date_text:
                    return date_text
                sibling = sibling.next_sibling
            current = current.parent if current.parent is not container else None
    return ""


def _article_post_date(soup: BeautifulSoup, container) -> str:
    selectors = [
        "time[datetime]",
        "time",
        "[data-testid='post-date']",
        ".article-date",
        ".post-date",
        ".news-date",
        ".date-post",
        ".re__news-time",
        '[class*="postDate"]',
        '[class*="PostDate"]',
        '[class*="Date"]',
    ]
    for selector in selectors:
        for node in soup.select(selector):
            value = node.get("datetime") or node.get_text(" ", strip=True)
            date_text = _extract_date_text(value)
            if date_text:
                return date_text

    for label in (
        "Cập nhật lần cuối vào",
        "Cáº­p nháº­t láº§n cuá»‘i vÃ o",
    ):
        date_text = _date_after_text(container, label)
        if date_text:
            return date_text

    source_date = _extract_source_publish_date(container.get_text(" ", strip=True))
    if source_date:
        return source_date

    return ""


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
                if text and text not in {"â€¢", "•"}:
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


def _article_body_legacy(container) -> tuple[str, str]:
    pieces: list[str] = []
    for node in container.find_all(["p", "figcaption", "h2", "h3"]):
        text = _clean_text(node.get_text(" ", strip=True))
        if not text:
            continue
        if node.name in {"h2", "h3"} and text.lower() in {
            "chia sẻ bài viết này",
            "chia sáº» bÃ i viáº¿t nÃ y",
            "bài viết được xem nhiều nhất",
            "bÃ i viáº¿t Ä‘Æ°á»£c xem nhiá»u nháº¥t",
            "bài viết khác",
            "bÃ i viáº¿t khÃ¡c",
        }:
            break
        if node.name in {"h2", "h3"}:
            continue
        pieces.append(text)
    summary = pieces[0] if pieces else ""
    return "\n".join(pieces), summary


def _article_body(container) -> tuple[str, str]:
    pieces: list[str] = []
    content = container.select_one(".content-wrapper") or container
    stop_keys = {
        "chia se bai viet nay",
        "bai viet duoc xem nhieu nhat",
        "bai viet khac",
    }

    for node in content.find_all(["p", "div", "figcaption", "h2", "h3"]):
        if content is not container and node.find_parent("figure"):
            continue
        if node.name == "div" and "p" not in (node.get("class") or []):
            continue

        text = _clean_text(node.get_text(" ", strip=True))
        if not text:
            continue

        normalized = _clean_text(
            unicodedata.normalize("NFD", text)
            .encode("ascii", "ignore")
            .decode("ascii")
            .lower()
        )
        if node.name in {"h2", "h3"} and normalized in stop_keys:
            break

        pieces.append(text)

    summary = pieces[0] if pieces else ""
    return "\n".join(pieces), summary


def _category_from_text(category_text: str) -> str:
    lowered = category_text.lower()
    if "phap ly" in lowered or "pháp lý" in lowered or "phÃ¡p lÃ½" in lowered:
        return "legal"
    if "thi truong" in lowered or "thị trường" in lowered or "thá»‹ trÆ°á»ng" in lowered:
        return "market"
    if "huong dan" in lowered or "hướng dẫn" in lowered or "hÆ°á»›ng dáº«n" in lowered:
        return "guide"
    return "news"


def parse_article(html: str, *, url: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    container = _article_main(soup)
    title = _text(container, "h1") or _text(soup, "h1") or _text(soup, "[data-testid='article-title']")
    body, summary = _article_body(container)
    category_text = _text(soup, ".breadcrumb a:last-child, [data-testid='category']")
    post_date = _text(soup, "time, .date, [data-testid='post-date']") or _meta_after_text(container, "Cập nhật lần cuối vào")
    post_date = _article_post_date(soup, container)
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


def parse_article_page(page, url: str) -> dict[str, str] | None:
    row = parse_article(page.content(), url=url)
    return row if row.get("title") and row.get("body") else None


def crawl_article(
    browser: Browser,
    url: str,
    stealth_obj: Stealth,
    retries: int = 2,
) -> dict[str, str] | None:
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
            row = parse_article_page(page, url)
            if row:
                return row
            if attempt < retries:
                _log(f"  [RETRY] {url} invalid/empty article page, attempt {attempt + 1}")
                time.sleep(3 + random.random() * 2)
            else:
                _log(f"  [ERROR] {url} invalid/empty article page after {retries + 1} attempts")
        except Exception as e:
            if attempt < retries:
                _log(f"  [RETRY] {url} error: {e}, attempt {attempt + 1}")
                time.sleep(3 + random.random() * 2)
            else:
                _log(f"  [ERROR] {url} failed after {retries + 1} attempts: {e}")
        finally:
            ctx.close()

    return None


def worker_fn(worker_id: int, url_list: list[dict[str, str]], tmp_path: str) -> int:
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
            row = crawl_article(browser, url, stealth_obj)
            pages_since_restart += 1

            if row:
                append_csv(tmp_path, [row], FIELDS)
                total_written += 1
                consecutive_errors = 0
                _log(
                    f"  [W{worker_id}] {i + 1}/{len(url_list)} "
                    f"url={url} OK | total: {total_written}"
                )
            else:
                consecutive_errors += 1
                _log(
                    f"  [W{worker_id}] {i + 1}/{len(url_list)} "
                    f"url={url} FAILED | errors: {consecutive_errors}"
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


def _read_input_urls(input_file: str) -> list[dict[str, str]]:
    urls: list[dict[str, str]] = []
    with open(input_file, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("url"):
                urls.append({"url": row["url"]})
    return urls


def _read_done_urls_with_tmp(output: str) -> set[str]:
    done = set(read_done_ids(output, key="url"))
    pattern = f"{output}.worker*.tmp"
    for tmp in glob.glob(pattern):
        try:
            with open(tmp, newline="", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    url = row.get("url", "")
                    if url:
                        done.add(url)
        except Exception:
            pass
    return done


def run(*, input_file: str, output: str, workers: int, limit: int = 0) -> int:
    input_path = input_file if os.path.isabs(input_file) else os.path.normpath(os.path.abspath(input_file))
    output_path = output if os.path.isabs(output) else os.path.normpath(os.path.abspath(output))

    if not os.path.exists(input_path):
        print(f"[ERROR] Input file not found: {input_path}")
        return 0

    all_urls = _read_input_urls(input_path)
    print(f"Loaded {len(all_urls)} news URLs from {input_path}")

    done_urls = _read_done_urls_with_tmp(output_path)
    if done_urls:
        print(f"Resuming: {len(done_urls)} already crawled, skipping them")
    pending = [entry for entry in all_urls if entry["url"] not in done_urls]

    if limit > 0:
        pending = pending[:limit]
        print(f"Limited to {limit} URLs")

    if not pending:
        print("Nothing to crawl - all URLs already done!")
        return 0

    print(f"Crawling {len(pending)} articles with {workers} workers -> {output_path}")

    num_workers = min(workers, len(pending))
    chunk_size = (len(pending) + num_workers - 1) // num_workers
    chunks = [pending[i : i + chunk_size] for i in range(0, len(pending), chunk_size)]

    for i, chunk in enumerate(chunks):
        print(f"  W{i}: {len(chunk)} articles")

    if not done_urls:
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
                print(f"  W{wid} done: {count} articles")
            except Exception as e:
                print(f"  W{wid} failed: {e}")

    elapsed = time.time() - t0
    print(f"\nCrawling finished in {elapsed:.0f}s ({total} new articles)")

    tmp_pattern = f"{output_path}.worker*.tmp"
    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        carry_path = f"{output_path}.workerCARRY.tmp"
        os.replace(output_path, carry_path)

    final_count = merge_tmp_files(tmp_pattern, output_path, FIELDS, dedupe_key="url")

    for tmp in glob.glob(tmp_pattern):
        os.remove(tmp)

    print(f"Done! {final_count} total unique articles saved to {output_path}")
    return final_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl news article detail pages")
    parser.add_argument(
        "--input", default="data/raw/news_urls.csv",
        help="Input CSV with url column (default: data/raw/news_urls.csv)",
    )
    parser.add_argument(
        "--output", default="data/raw/news_articles.csv",
        help="Output CSV file (default: data/raw/news_articles.csv)",
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

    run(input_file=args.input, output=args.output, workers=args.workers, limit=args.limit)


if __name__ == "__main__":
    main()
