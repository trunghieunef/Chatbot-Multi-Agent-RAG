import pytest

from data_pipeline.ingestors import news_ingestor as ni
from data_pipeline.ingestors.news_ingestor import build_article_chunks


class FailingEmbedder:
    async def embed_texts(self, texts):
        raise RuntimeError("embedding unavailable")


class StubEmbedder:
    async def embed_texts(self, texts):
        return [[0.1] * 1024 for _ in texts]


async def noop_ensure_vector_extension():
    return None


def sample_article_row():
    return {
        "title": "Article Publish 1",
        "body": "Day la noi dung bai viet bat dong san. " * 10,
        "category": "news",
        "source": "batdongsan.com",
        "post_date": "2026-06-01",
        "url": "https://example.test/news/article-publish-1",
    }


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


def test_news_empty_ingest_result_shape():
    assert ni.empty_ingest_result() == {
        "published": 0,
        "indexed": 0,
        "chunks": 0,
        "publish_errors": 0,
        "index_errors": 0,
    }


@pytest.mark.asyncio
async def test_news_publish_survives_embedding_failure(monkeypatch):
    async def fake_publish_batch(rows):
        assert rows[0]["url"] == "https://example.test/news/article-publish-1"
        return [type("PersistedArticle", (), {"id": 301, "url": rows[0]["url"]})()]

    monkeypatch.setattr(ni, "publish_article_batch", fake_publish_batch)
    monkeypatch.setattr(ni, "BGEEmbedder", lambda **kwargs: FailingEmbedder())
    monkeypatch.setattr(ni, "ensure_vector_extension", noop_ensure_vector_extension)

    result = await ni.ingest_article_rows([sample_article_row()], batch_size=1)

    assert result["published"] == 1
    assert result["indexed"] == 0
    assert result["chunks"] == 0
    assert result["publish_errors"] == 0
    assert result["index_errors"] == 1


@pytest.mark.asyncio
async def test_news_parser_record_indexes_after_publish(monkeypatch):
    async def fake_publish_batch(rows):
        return [type("PersistedArticle", (), {"id": 302, "url": rows[0]["url"]})()]

    async def fake_index_batch(articles_with_chunks, *, embedder):
        assert articles_with_chunks[0][1]
        return {
            "indexed": 1,
            "chunks": len(articles_with_chunks[0][1]),
            "index_errors": 0,
        }

    monkeypatch.setattr(ni, "publish_article_batch", fake_publish_batch)
    monkeypatch.setattr(ni, "index_article_batch", fake_index_batch)
    monkeypatch.setattr(ni, "BGEEmbedder", lambda **kwargs: StubEmbedder())
    monkeypatch.setattr(ni, "ensure_vector_extension", noop_ensure_vector_extension)

    result = await ni.ingest_article_rows([sample_article_row()], batch_size=1)

    assert result["published"] == 1
    assert result["indexed"] == 1
    assert result["chunks"] >= 1
    assert result["publish_errors"] == 0
    assert result["index_errors"] == 0
