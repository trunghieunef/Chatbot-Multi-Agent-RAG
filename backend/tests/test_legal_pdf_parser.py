from pathlib import Path

from data_pipeline.legal.pdf_parser import parse_pdf


FIXTURE = Path(__file__).parent / "fixtures" / "sample_legal.pdf"


def test_parse_pdf_returns_text_with_normalized_whitespace():
    text = parse_pdf(str(FIXTURE))

    assert "Điều 1" in text
    assert "Phạm vi điều chỉnh" in text
    assert "\n\n\n" not in text


def test_parse_pdf_raises_for_missing_file():
    import pytest

    with pytest.raises(FileNotFoundError):
        parse_pdf("does/not/exist.pdf")
