"""
Step 2: Crawl detailed listing information from batdongsan.com.vn.

Reads listing URLs from listing_url.csv (output of Step 1: crawl_urls.py),
visits each listing page with headless Chrome + stealth, and extracts detailed
property information.

Features:
  - Resume support: skips already-crawled product_ids (from output + tmp files)
  - Parallel workers with separate Chromium instances
  - Browser restart every N pages to limit memory growth
  - Crash-safe: each worker writes to its own .tmp file
  - Auto-merge and deduplication at the end
  - Optional --since YYYY-MM-DD filter on post_date

Usage:
    python -m crawler.sale.crawl_details
    python -m crawler.sale.crawl_details --input ../listing_url.csv --output ../listing_details.csv --workers 4
    python -m crawler.sale.crawl_details --since 2026-01-01
"""

import argparse
import csv
import glob
import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime

from playwright.sync_api import sync_playwright, Browser
from playwright_stealth import Stealth

from crawler.core.csv_writer import append_csv, merge_tmp_files, read_done_ids
from crawler.core.listing_detail_parser import normalize_listing_detail
from crawler.core.parser import text_or_empty

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
BROWSER_RESTART_EVERY = 15  # restart browser every N pages to limit memory

DETAIL_FIELDS = [
    "product_id",
    "title",
    "price_text",
    "price_unit",
    "area_text",
    "price_per_m2_text",
    "bedrooms",
    "bathrooms",
    "direction",
    "balcony_direction",
    "floors",
    "frontage",         # mặt tiền
    "road_width",       # đường vào
    "legal",
    "furniture",
    "property_type",
    "address",
    "description",
    "post_date",
    "expiry_date",
    "listing_type",     # loại tin
    "contact_name",
    "url",
]

# Map Vietnamese spec labels → field names
SPEC_LABEL_MAP = {
    "Khoảng giá":                 "price_text",
    "Mức giá":                    "price_text",
    "Giá":                        "price_text",
    "Diện tích":                  "area_text",
    "Số phòng ngủ":               "bedrooms",
    "Phòng ngủ":                  "bedrooms",
    "Số phòng tắm, vệ sinh":     "bathrooms",
    "Phòng tắm":                  "bathrooms",
    "Hướng nhà":                  "direction",
    "Hướng cửa chính":            "direction",
    "Hướng ban công":             "balcony_direction",
    "Số tầng":                    "floors",
    "Mặt tiền":                   "frontage",
    "Đường vào":                  "road_width",
    "Pháp lý":                    "legal",
    "Nội thất":                   "furniture",
    "Loại hình nhà ở":            "property_type",
    "Loại hình":                  "property_type",
}

SHORT_INFO_LABEL_MAP = {
    "Khoảng giá":      "price_text",
    "Mức giá":         "price_text",
    "Diện tích":       "area_text",
    "Phòng ngủ":       "bedrooms",
    "Phòng tắm":       "bathrooms",
    "Ngày đăng":       "post_date",
    "Ngày hết hạn":    "expiry_date",
    "Loại tin":        "listing_type",
}

_print_lock = threading.Lock()


def _log(msg: str):
    with _print_lock:
        print(msg, flush=True)


def _text(el) -> str:
    """Backwards-compat thin wrapper kept for parse_detail_page logic.

    Uses crawler.core.parser.text_or_empty under the hood, but also
    preserves the simple ``inner_text().strip()`` semantics that the original
    spec/short-info parsing relies on (it splits multi-line text on newlines).
    """
    if el is None:
        return ""
    try:
        return el.inner_text().strip()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Parsing a single detail page
# ---------------------------------------------------------------------------

def parse_detail_page(page, url: str, product_id: str) -> dict | None:
    """Extract all available info from a listing detail page."""
    try:
        data = {field: "" for field in DETAIL_FIELDS}
        data["url"] = url
        data["product_id"] = product_id

        # --- Title ---
        title_el = (
            page.query_selector("h1.re__pr-title")
            or page.query_selector("h1.pr-title")
            or page.query_selector("h1")
        )
        data["title"] = text_or_empty(title_el)

        # --- Short info bar (price, area, bedrooms, dates) ---
        short_items = page.query_selector_all(
            ".re__pr-short-info-item.js__pr-short-info-item"
        )
        if not short_items:
            short_items = page.query_selector_all(".re__pr-short-info-item")

        for item in short_items:
            title_span = item.query_selector(".title")
            value_span = item.query_selector(".value")
            if not title_span or not value_span:
                continue
            label = _text(title_span)
            value = _text(value_span)
            field_key = SHORT_INFO_LABEL_MAP.get(label)
            if field_key:
                data[field_key] = value

        # --- Extract price_per_m2 from the price short-info item ---
        # The price item has structure: "2,95 tỷ\n~68,6 triệu/m²"
        if not data["price_per_m2_text"]:
            for item in short_items:
                title_span = item.query_selector(".title")
                if title_span and "giá" in _text(title_span).lower():
                    full_text = _text(item)
                    lines = full_text.split("\n")
                    for line in lines:
                        line = line.strip()
                        if "m²" in line and "/" in line:
                            # Remove leading ~ character
                            data["price_per_m2_text"] = line.lstrip("~").strip()
                            break
                    break

        # --- Specs section (detailed attributes table) ---
        spec_items = page.query_selector_all(".re__pr-specs-content-item")
        for item in spec_items:
            title_el = item.query_selector(".re__pr-specs-content-item-title")
            value_el = item.query_selector(".re__pr-specs-content-item-value")
            if not title_el or not value_el:
                continue
            label = _text(title_el)
            value = _text(value_el)
            field_key = SPEC_LABEL_MAP.get(label)
            if field_key and not data[field_key]:
                # Don't overwrite values already set from short info
                data[field_key] = value

        # --- Config section at bottom (post_date, expiry, listing_type) ---
        # These items are in ".re__pr-config .js__pr-config-item"
        # Structure: raw text like "Ngày đăng\n02/04/2026"
        config_label_map = {
            "Ngày đăng":     "post_date",
            "Ngày hết hạn":  "expiry_date",
            "Loại tin":      "listing_type",
        }
        config_items = page.query_selector_all(".js__pr-config-item")
        for item in config_items:
            full = _text(item)
            lines = [ln.strip() for ln in full.split("\n") if ln.strip()]
            if len(lines) >= 2:
                label = lines[0]
                value = lines[1]
                field_key = config_label_map.get(label)
                if field_key and not data[field_key]:
                    data[field_key] = value

        # --- Address (from breadcrumb) ---
        breadcrumb = page.query_selector(".re__breadcrumb")
        if breadcrumb:
            # Breadcrumb text like: "Bán/Hồ Chí Minh/Quận 7/Nhà riêng tại đường Lâm Văn Bền"
            crumbs = breadcrumb.query_selector_all("a")
            if crumbs:
                parts = [text_or_empty(c) for c in crumbs if text_or_empty(c)]
                data["address"] = ", ".join(parts)
            else:
                data["address"] = _text(breadcrumb).replace("\n", ", ")

        # If breadcrumb didn't work, try other selectors
        if not data["address"]:
            addr_el = (
                page.query_selector(".re__pr-short-description--address")
                or page.query_selector(".js__pr-address")
            )
            data["address"] = text_or_empty(addr_el)

        # --- Description ---
        desc_el = (
            page.query_selector(".re__detail-content")
            or page.query_selector(".re__section-body--content")
        )
        desc_text = _text(desc_el)
        # Truncate extremely long descriptions to save space
        if len(desc_text) > 2000:
            desc_text = desc_text[:2000] + "..."
        # Clean up newlines for CSV
        data["description"] = desc_text.replace("\r\n", "\n").replace("\n", " | ")

        # --- Contact name ---
        contact_el = (
            page.query_selector(".re__contact-name")
            or page.query_selector(".js__agent-name")
            or page.query_selector(".re__agent-info .agent-name")
        )
        data["contact_name"] = text_or_empty(contact_el)

        # Apply shared normalization (sets listing_type + price_unit)
        data = normalize_listing_detail(data, source="sale")

        return data

    except Exception as e:
        _log(f"  [WARN] parse error on {url}: {e}")
        return None


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

def _passes_since_filter(row: dict, since: date | None) -> bool:
    """Return True if the row should be kept under --since.

    If ``since`` is None or row has no parseable post_date, keep it (don't drop).
    """
    if since is None:
        return True
    raw = (row.get("post_date") or "").strip()
    if not raw:
        return True
    parsed = None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            parsed = datetime.strptime(raw, fmt).date()
            break
        except ValueError:
            continue
    if parsed is None:
        return True
    return parsed >= since


def _parse_since_arg(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        _log(f"  [WARN] invalid --since value '{value}', expected YYYY-MM-DD; ignoring")
        return None


# ---------------------------------------------------------------------------
# Crawling
# ---------------------------------------------------------------------------

def crawl_detail(
    browser: Browser,
    url: str,
    product_id: str,
    stealth_obj: Stealth,
    retries: int = 2,
) -> dict | None:
    """Load a single listing detail page and extract all data."""
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

            # Check if we actually loaded a detail page (not a block/error page)
            title_el = page.query_selector("h1.re__pr-title") or page.query_selector("h1")
            if title_el and _text(title_el):
                return parse_detail_page(page, url, product_id)

            if attempt < retries:
                _log(f"  [RETRY] {product_id} no title found, attempt {attempt + 1}")
                time.sleep(3 + random.random() * 2)
        except Exception as e:
            if attempt < retries:
                _log(f"  [RETRY] {product_id} error: {e}, attempt {attempt + 1}")
                time.sleep(3 + random.random() * 2)
            else:
                _log(f"  [ERROR] {product_id} failed after {retries + 1} attempts: {e}")
        finally:
            ctx.close()

    return None


def worker_fn(
    worker_id: int,
    url_list: list[dict],
    tmp_path: str,
    since: date | None = None,
) -> int:
    """Crawl a batch of listing detail pages. Write results to a tmp CSV."""
    stealth_obj = Stealth()
    total_written = 0
    consecutive_errors = 0

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        pages_since_restart = 0

        for i, entry in enumerate(url_list):
            # Restart browser periodically to prevent memory leaks
            if pages_since_restart >= BROWSER_RESTART_EVERY:
                browser.close()
                browser = pw.chromium.launch(headless=True)
                pages_since_restart = 0

            url = entry["url"]
            product_id = entry["product_id"]

            row = crawl_detail(browser, url, product_id, stealth_obj)
            pages_since_restart += 1

            if row and not _passes_since_filter(row, since):
                _log(
                    f"  [W{worker_id}] {i + 1}/{len(url_list)} "
                    f"pid={product_id} SKIP (post_date {row.get('post_date')!r} < since)"
                )
                row = None

            if row:
                append_csv(tmp_path, [row], DETAIL_FIELDS)
                total_written += 1
                consecutive_errors = 0
                _log(
                    f"  [W{worker_id}] {i + 1}/{len(url_list)} "
                    f"pid={product_id} OK | total: {total_written}"
                )
            else:
                consecutive_errors += 1
                _log(
                    f"  [W{worker_id}] {i + 1}/{len(url_list)} "
                    f"pid={product_id} FAILED | errors: {consecutive_errors}"
                )

            # If too many consecutive errors, likely blocked — slow down
            if consecutive_errors >= 5:
                _log(f"  [W{worker_id}] {consecutive_errors} consecutive errors, pausing 30s...")
                time.sleep(30)
                # Restart browser after cooldown
                browser.close()
                browser = pw.chromium.launch(headless=True)
                pages_since_restart = 0
                consecutive_errors = 0

            # Random delay between requests
            time.sleep(1.5 + random.random() * 1.5)

        browser.close()

    return total_written


# ---------------------------------------------------------------------------
# Local helpers (resume + input loading)
# ---------------------------------------------------------------------------

def _read_done_ids_with_tmp(output: str) -> set[str]:
    """Aggregate done product_ids from the final output and any leftover tmp files."""
    done = set(read_done_ids(output))

    # Check any leftover tmp files from a previous run
    pattern = f"{output}.worker*.tmp"
    for tmp in glob.glob(pattern):
        try:
            with open(tmp, newline="", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    pid = row.get("product_id", "")
                    if pid:
                        done.add(pid)
        except Exception:
            pass

    return done


def _read_input_urls(input_file: str) -> list[dict]:
    """Read URLs from the input CSV (listing_url.csv)."""
    urls = []
    with open(input_file, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("url") and row.get("product_id"):
                urls.append({"product_id": row["product_id"], "url": row["url"]})
    return urls


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Step 2: Crawl listing details from batdongsan.com.vn"
    )
    parser.add_argument(
        "--input", default="../listing_url.csv",
        help="Input CSV with product_id,url columns (default: ../listing_url.csv)",
    )
    parser.add_argument(
        "--output", default="../listing_details.csv",
        help="Output CSV file (default: ../listing_details.csv)",
    )
    parser.add_argument(
        "--workers", type=int, default=4,
        help="Parallel workers (default: 4, each runs its own browser)",
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Max URLs to crawl (0 = all). Useful for testing.",
    )
    parser.add_argument(
        "--since", default=None,
        help="Only keep rows with post_date >= YYYY-MM-DD when post_date is available",
    )
    args = parser.parse_args()

    # Resolve paths: absolute paths used as-is, relative paths resolved from CWD
    input_path = args.input if os.path.isabs(args.input) else os.path.normpath(os.path.abspath(args.input))
    output_path = args.output if os.path.isabs(args.output) else os.path.normpath(os.path.abspath(args.output))

    if not os.path.exists(input_path):
        print(f"[ERROR] Input file not found: {input_path}")
        return

    since = _parse_since_arg(args.since)
    if since:
        print(f"--since={since.isoformat()}: rows with post_date older than this will be dropped")

    # --- Read input URLs ---
    all_urls = _read_input_urls(input_path)
    print(f"Loaded {len(all_urls)} URLs from {input_path}")

    # --- Resume: find already-crawled IDs ---
    done_ids = _read_done_ids_with_tmp(output_path)
    if done_ids:
        print(f"Resuming: {len(done_ids)} already crawled, skipping them")
    pending = [u for u in all_urls if u["product_id"] not in done_ids]

    if args.limit > 0:
        pending = pending[:args.limit]
        print(f"Limited to {args.limit} URLs")

    if not pending:
        print("Nothing to crawl — all URLs already done!")
        return

    print(f"Crawling {len(pending)} listings with {args.workers} workers -> {output_path}")

    # --- Split work across workers ---
    num_workers = min(args.workers, len(pending))
    chunk_size = (len(pending) + num_workers - 1) // num_workers
    chunks = [pending[i : i + chunk_size] for i in range(0, len(pending), chunk_size)]

    for i, chunk in enumerate(chunks):
        print(f"  W{i}: {len(chunk)} listings")

    # Clean stale tmp files (only if not resuming)
    if not done_ids:
        tmp_pattern = f"{output_path}.worker*.tmp"
        for stale in glob.glob(tmp_pattern):
            os.remove(stale)
            print(f"  Removed stale {stale}")

    # --- Launch workers ---
    total = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=num_workers) as pool:
        futures = {
            pool.submit(
                worker_fn, i, chunk, f"{output_path}.worker{i}.tmp", since,
            ): i
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

    elapsed = time.time() - t0
    print(f"\nCrawling finished in {elapsed:.0f}s ({total} new listings)")

    # --- Merge and deduplicate (include existing output rows for resume) ---
    # Stage the existing output as a worker-style tmp file so the core merge
    # picks it up alongside this run's worker tmps and dedupes in one pass.
    tmp_pattern = f"{output_path}.worker*.tmp"
    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        carry_path = f"{output_path}.workerCARRY.tmp"
        os.replace(output_path, carry_path)

    final_count = merge_tmp_files(tmp_pattern, output_path, DETAIL_FIELDS)

    # Clean up tmp files (merge_tmp_files leaves them on disk)
    for tmp in glob.glob(tmp_pattern):
        os.remove(tmp)

    print(f"Done! {final_count} total unique listings saved to {output_path}")


if __name__ == "__main__":
    main()
