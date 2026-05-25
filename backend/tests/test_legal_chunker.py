from data_pipeline.legal.chunker import build_legal_chunks


def test_build_legal_chunks_creates_one_chunk_per_dieu_when_short():
    articles = [
        {"chuong": "Chương I", "chuong_title": "Quy định chung", "dieu_number": 1, "dieu_title": "Phạm vi", "text": "Luật này quy định..."},
        {"chuong": "Chương I", "chuong_title": "Quy định chung", "dieu_number": 2, "dieu_title": "Đối tượng", "text": "Áp dụng cho..."},
    ]

    chunks = build_legal_chunks(articles, doc_slug="luat-dat-dai-2024", chunk_size=1500)

    assert len(chunks) == 2
    assert chunks[0]["chunk_type"] == "dieu"
    assert chunks[0]["text"].startswith("Điều 1. Phạm vi")
    assert chunks[0]["citation"] == {
        "doc_slug": "luat-dat-dai-2024",
        "chuong": "Chương I",
        "dieu_number": 1,
        "dieu_title": "Phạm vi",
        "khoan_number": None,
    }


def test_build_legal_chunks_splits_long_dieu_by_khoan_with_citations():
    body = (
        "1. Khoản một nội dung. " + "Khoản một mở rộng. " * 60
        + "\n2. Khoản hai nội dung. " + "Khoản hai mở rộng. " * 60
        + "\n3. Khoản ba nội dung. " + "Khoản ba mở rộng. " * 60
    )
    articles = [
        {"chuong": "Chương II", "chuong_title": "Quyền", "dieu_number": 3, "dieu_title": "Quyền sử dụng", "text": body},
    ]

    chunks = build_legal_chunks(articles, doc_slug="luat-dat-dai-2024", chunk_size=1500, overlap=200)

    khoan_numbers = [chunk["citation"]["khoan_number"] for chunk in chunks]
    assert {1, 2, 3}.issubset(set(khoan_numbers))
    for chunk in chunks:
        assert chunk["citation"]["dieu_number"] == 3


def test_build_legal_chunks_falls_back_to_fixed_size_when_no_khoan():
    long_text = "Một câu nội dung dài không có khoản. " * 200
    articles = [
        {"chuong": "Chương III", "chuong_title": "Khác", "dieu_number": 7, "dieu_title": "Điều khác", "text": long_text},
    ]

    chunks = build_legal_chunks(articles, doc_slug="luat-dat-dai-2024", chunk_size=1500, overlap=200)

    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk["citation"]["dieu_number"] == 7
        assert chunk["citation"]["khoan_number"] is None
        assert len(chunk["text"]) <= 1700
