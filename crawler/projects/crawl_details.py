"""
Crawl detail pages for projects scraped by `crawler.projects.crawl_urls`.

Selectors are fixture-backed and intentionally kept in pure parser helpers so
they can be tested without launching Playwright. The CLI and CSV columns remain
stable for downstream ingestion.

Output CSV columns:
    slug, name, developer, location, district, city,
    total_units, price_range, area_range, status, project_type,
    description, amenities (JSON-encoded list), url
"""

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
from playwright.sync_api import sync_playwright, Browser
from playwright_stealth import Stealth

from crawler.core.csv_writer import append_csv, merge_tmp_files, read_done_ids
from data_pipeline.clean import slugify

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
    "scale",
    "status",
    "project_type",
    "legal",
    "description",
    "amenities",  # JSON-encoded list
    "image_urls",  # JSON-encoded list
    "url",
]

_print_lock = threading.Lock()


def _log(msg: str) -> None:
    with _print_lock:
        print(msg, flush=True)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _text(soup: BeautifulSoup, selector: str) -> str:
    node = soup.select_one(selector)
    return " ".join(node.get_text(" ", strip=True).split()) if node else ""


def _clean_text(value: str) -> str:
    return " ".join((value or "").split())


def _label_key(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value or "")
    without_marks = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return without_marks.replace("đ", "d").replace("Đ", "d").lower().strip()


def _lookup(mapping: dict[str, str], *labels: str) -> str:
    for label in labels:
        value = mapping.get(label.lower()) or mapping.get(_label_key(label))
        if value:
            return value
    return ""


def _extract_value_from_description(description: str, label: str) -> str:
    match = re.search(
        rf"{re.escape(label)}\s*:\s*(.*?)(?=\s+[A-ZÀ-ỸĐ][^:]{1,40}:\s|$)",
        description,
        flags=re.IGNORECASE,
    )
    if not match:
        return ""
    value = _clean_text(match.group(1))
    for boundary in (" Pháp lý:", " Loại hình sản phẩm:", " Số lượng sản phẩm:", " Tổng diện tích sàn:"):
        if boundary in value:
            value = value.split(boundary, 1)[0]
    return _clean_text(value)


def _project_attr_map(soup: BeautifulSoup) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for row in soup.select(".re__project-attr tr"):
        label = _clean_text(row.select_one(".re__attr-item-label").get_text(" ", strip=True)) if row.select_one(".re__attr-item-label") else ""
        value = _clean_text(row.select_one(".re__attr-item-value").get_text(" ", strip=True)) if row.select_one(".re__attr-item-value") else ""
        if label and value:
            attrs[label.lower()] = value
            attrs[_label_key(label)] = value
    return attrs


def _project_box_map(soup: BeautifulSoup) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for item in soup.select(".re__project-box-item"):
        parts = [
            _clean_text(node.get_text(" ", strip=True))
            for node in item.find_all(["span", "div"])
            if node.get_text(strip=True)
        ]
        if len(parts) >= 2:
            attrs[parts[0].lower()] = parts[1]
            attrs[_label_key(parts[0])] = parts[1]
    return attrs


def _project_address(soup: BeautifulSoup) -> str:
    address = _text(soup, ".re__project-address") or _text(
        soup, ".project-location, [data-testid='project-location']"
    )
    return _clean_text(address.replace("Xem bản đồ", ""))


def _location_parts(location: str) -> tuple[str, str]:
    parts = [part.strip(" .") for part in location.split(",") if part.strip(" .")]
    district = parts[-2] if len(parts) >= 2 else ""
    city = parts[-1] if parts else ""
    return district, city


def _project_editor(soup: BeautifulSoup):
    return soup.select_one(
        ".js__prj-detail-content.re__detail-content.re__project-editor, "
        ".re__project-editor, "
        "[data-testid='project-description'], "
        ".project-description"
    )


def _project_amenities(soup: BeautifulSoup) -> list[str]:
    facilities = [
        _clean_text(item.get_text(" ", strip=True))
        for item in soup.select(".re__prj-facilities .re__toogle-detail span")
        if item.get_text(strip=True)
    ]
    if facilities:
        return facilities

    legacy_items = [
        _clean_text(item.get_text(" ", strip=True))
        for item in soup.select(".amenities li, [data-testid='amenity']")
        if item.get_text(strip=True)
    ]
    if legacy_items:
        return legacy_items

    editor = _project_editor(soup)
    if not editor:
        return []

    amenities: list[str] = []
    in_amenities_section = False
    for node in editor.find_all(["h2", "h3", "h4", "li"]):
        text = _clean_text(node.get_text(" ", strip=True))
        if not text:
            continue
        if node.name in {"h2", "h3", "h4"}:
            normalized = text.lower()
            in_amenities_section = "tiện ích" in normalized or "tien ich" in normalized
            continue
        if in_amenities_section and node.name == "li":
            amenities.append(text)

    return amenities


def _project_images(soup: BeautifulSoup, *, base_url: str) -> list[str]:
    urls: list[str] = []
    for image in soup.select(".re__project-album img, .project-main-container img"):
        src = image.get("data-src") or image.get("src") or ""
        if not src or src.startswith("data:"):
            continue
        absolute = urljoin(base_url, src)
        if absolute not in urls:
            urls.append(absolute)
    return urls


def parse_project_detail(html: str, *, url: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    name = _text(soup, "h1.re__project-name") or _text(soup, "h1") or _text(soup, "[data-testid='project-title']")
    attr_map = _project_attr_map(soup)
    location = _project_address(soup)
    location = _clean_text(location.replace("Xem bản đồ", ""))
    district, city = _location_parts(location)
    editor = _project_editor(soup)
    description = _clean_text(editor.get_text(" ", strip=True)) if editor else ""
    amenities = _project_amenities(soup)
    box_map = _project_box_map(soup)
    total_units = _lookup(attr_map, "Số căn") or _lookup(box_map, "Số căn") or _text(soup, ".total-units, [data-testid='total-units']")
    total_units = re.sub(r"\D+", "", total_units)
    area_range = _lookup(attr_map, "Diện tích") or _lookup(box_map, "Diện tích") or _text(soup, ".area-range, [data-testid='area-range']")
    project_type = (
        _lookup(attr_map, "Loại hình sản phẩm", "Kiểu biệt thự")
        or _lookup(box_map, "Loại hình sản phẩm", "Kiểu biệt thự")
        or _extract_value_from_description(description, "Loại hình sản phẩm")
        or _text(soup, ".project-type, [data-testid='project-type']")
    )
    legal = (
        _lookup(attr_map, "Pháp lý")
        or _lookup(box_map, "Pháp lý")
        or _extract_value_from_description(description, "Pháp lý")
    )
    return {
        "slug": slugify(name) or url.rstrip("/").split("/")[-1],
        "name": name,
        "developer": attr_map.get("chủ đầu tư", "") or _text(soup, ".developer, [data-testid='developer']"),
        "location": location,
        "district": _text(soup, ".district, [data-testid='district']") or district,
        "city": _text(soup, ".city, [data-testid='city']") or city,
        "total_units": _text(soup, ".total-units, [data-testid='total-units']"),
        "price_range": _text(soup, ".price-range, [data-testid='price-range']"),
        "area_range": attr_map.get("diện tích", "") or _text(soup, ".area-range, [data-testid='area-range']"),
        "status": _text(soup, ".status, [data-testid='status']"),
        "project_type": _text(soup, ".project-type, [data-testid='project-type']"),
        "description": description,
        "amenities": json.dumps(amenities, ensure_ascii=False),
        "developer": _lookup(attr_map, "Chủ đầu tư", "Chá»§ Ä‘áº§u tÆ°") or _text(soup, ".developer, [data-testid='developer']"),
        "total_units": total_units,
        "area_range": area_range,
        "scale": _lookup(box_map, "Quy mô") or _lookup(attr_map, "Quy mô"),
        "status": _text(soup, ".project-main-container .re__prj-tag-info, .status, [data-testid='status']"),
        "project_type": project_type,
        "legal": legal,
        "image_urls": json.dumps(_project_images(soup, base_url=url), ensure_ascii=False),
        "url": url,
    }


def parse_detail_page(page, url: str, slug: str) -> dict | None:
    """Extract project detail fields from a loaded Playwright page."""
    row = parse_project_detail(page.content(), url=url)
    row["slug"] = slug
    return row if row.get("name") else None


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
