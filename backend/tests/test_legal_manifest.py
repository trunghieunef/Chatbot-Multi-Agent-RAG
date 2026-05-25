from pathlib import Path

from data_pipeline.legal.manifest import compute_sha256, has_been_ingested, mark_ingested


def test_compute_sha256_is_deterministic(tmp_path: Path):
    file_a = tmp_path / "a.txt"
    file_a.write_bytes(b"hello world")

    digest = compute_sha256(str(file_a))

    assert len(digest) == 64
    assert digest == compute_sha256(str(file_a))


def test_mark_and_check_ingested(tmp_path: Path):
    log_dir = tmp_path / "ingested"
    digest = "a" * 64

    assert not has_been_ingested(digest, str(log_dir))
    mark_ingested(digest, str(log_dir), info={"file": "x.pdf", "chunks": 12})
    assert has_been_ingested(digest, str(log_dir))
