from data_pipeline.ingestors.news_ingestor import build_article_chunks


def test_build_article_chunks_splits_long_body_with_overlap():
    body = "Câu một. " * 200
    article = {"title": "Tiêu đề", "body": body, "category": "news"}

    chunks = build_article_chunks(article, chunk_size=120, overlap=20)

    assert len(chunks) > 1
    assert all(len(chunk["text"]) <= 200 for chunk in chunks)
    assert chunks[0]["chunk_type"] == "title"
    assert chunks[1]["chunk_type"] == "body"


def test_build_article_chunks_returns_only_title_when_body_empty():
    article = {"title": "Tiêu đề", "body": "", "category": "news"}

    chunks = build_article_chunks(article, chunk_size=120, overlap=20)

    assert [chunk["chunk_type"] for chunk in chunks] == ["title"]
