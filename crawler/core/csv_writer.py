from __future__ import annotations

import csv
import glob
import os


def append_csv(path: str, rows: list[dict], fieldnames: list[str]) -> None:
    if not rows:
        return
    file_exists = os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)


def read_done_ids(output: str, key: str = "product_id") -> set[str]:
    if not os.path.exists(output):
        return set()
    with open(output, newline="", encoding="utf-8-sig") as handle:
        return {row[key] for row in csv.DictReader(handle) if row.get(key)}


def merge_tmp_files(pattern: str, output: str, fieldnames: list[str], dedupe_key: str = "product_id") -> int:
    rows: list[dict] = []
    for path in glob.glob(pattern):
        with open(path, newline="", encoding="utf-8-sig") as handle:
            rows.extend(csv.DictReader(handle))

    seen: set[str] = set()
    deduped: list[dict] = []
    for row in rows:
        key = row.get(dedupe_key)
        if key and key not in seen:
            seen.add(key)
            deduped.append(row)

    with open(output, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(deduped)
    return len(deduped)
