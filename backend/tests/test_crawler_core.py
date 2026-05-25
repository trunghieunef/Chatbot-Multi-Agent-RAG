import csv
from pathlib import Path

from crawler.core.csv_writer import append_csv, merge_tmp_files, read_done_ids


FIELDNAMES = ["product_id", "url"]


def test_append_csv_writes_header_once(tmp_path: Path):
    target = tmp_path / "out.csv"

    append_csv(str(target), [{"product_id": "1", "url": "u1"}], FIELDNAMES)
    append_csv(str(target), [{"product_id": "2", "url": "u2"}], FIELDNAMES)

    rows = list(csv.DictReader(target.open(encoding="utf-8-sig")))
    assert [row["product_id"] for row in rows] == ["1", "2"]


def test_append_csv_skips_empty_input(tmp_path: Path):
    target = tmp_path / "out.csv"

    append_csv(str(target), [], FIELDNAMES)

    assert not target.exists()


def test_read_done_ids_returns_existing_keys(tmp_path: Path):
    target = tmp_path / "out.csv"
    append_csv(str(target), [{"product_id": "a", "url": "ua"}, {"product_id": "b", "url": "ub"}], FIELDNAMES)

    assert read_done_ids(str(target)) == {"a", "b"}


def test_merge_tmp_files_deduplicates_by_product_id(tmp_path: Path):
    output = tmp_path / "merged.csv"
    worker_a = tmp_path / "merged.csv.worker0.tmp"
    worker_b = tmp_path / "merged.csv.worker1.tmp"
    append_csv(str(worker_a), [{"product_id": "1", "url": "u1"}, {"product_id": "2", "url": "u2"}], FIELDNAMES)
    append_csv(str(worker_b), [{"product_id": "2", "url": "u2-dup"}, {"product_id": "3", "url": "u3"}], FIELDNAMES)

    count = merge_tmp_files(str(tmp_path / "merged.csv.worker*.tmp"), str(output), FIELDNAMES)

    rows = list(csv.DictReader(output.open(encoding="utf-8-sig")))
    assert count == 3
    assert sorted(row["product_id"] for row in rows) == ["1", "2", "3"]
