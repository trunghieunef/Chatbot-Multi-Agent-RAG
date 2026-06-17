import pytest

from data_pipeline.ingestors import projects_ingestor as pi
from data_pipeline.ingestors.projects_ingestor import (
    build_project_chunks,
    prepare_project_image_rows,
    project_image_urls_from_row,
)


class FailingEmbedder:
    async def embed_texts(self, texts):
        raise RuntimeError("embedding unavailable")


class StubEmbedder:
    async def embed_texts(self, texts):
        return [[0.1] * 1024 for _ in texts]


async def noop_ensure_vector_extension():
    return None


class ProjectImageStub:
    id = 22
    slug = "sun-festo-town"


def sample_project_row():
    return {
        "slug": "project-publish-1",
        "name": "Project Publish 1",
        "developer": "Demo Developer",
        "district": "Quan 7",
        "city": "Ho Chi Minh",
        "status": "selling",
        "price_range": "5-7 ty",
        "area_range": "50-80 m2",
        "project_type": "apartment",
        "description": "Project description",
        "amenities": '["pool", "school"]',
        "url": "https://example.test/projects/project-publish-1",
    }


def test_build_project_chunks_creates_overview_and_amenities_chunks():
    project = {
        "slug": "vinhomes-grand-park",
        "name": "Vinhomes Grand Park",
        "developer": "Vinhomes",
        "district": "Quận 9",
        "city": "Hồ Chí Minh",
        "price_range": "2,5 - 4,8 tỷ",
        "area_range": "55 - 120 m²",
        "status": "selling",
        "description": "Khu đô thị tích hợp.",
        "amenities": ["Hồ bơi", "Công viên"],
    }

    chunks = build_project_chunks(project)
    chunk_types = [chunk["chunk_type"] for chunk in chunks]

    assert "overview" in chunk_types
    assert "description" in chunk_types
    assert "amenities" in chunk_types


def test_project_empty_ingest_result_shape():
    assert pi.empty_ingest_result() == {
        "published": 0,
        "indexed": 0,
        "chunks": 0,
        "publish_errors": 0,
        "index_errors": 0,
    }


def test_project_image_urls_from_row_accepts_json_and_dedupes():
    row = {
        "image_urls": '["https://cdn.example.test/p1.jpg", "https://cdn.example.test/p1.jpg", "data:image/png;base64,abc", "https://cdn.example.test/p2.jpg"]'
    }

    assert project_image_urls_from_row(row) == [
        "https://cdn.example.test/p1.jpg",
        "https://cdn.example.test/p2.jpg",
    ]


def test_prepare_project_image_rows_marks_first_image_primary():
    rows = prepare_project_image_rows(
        ProjectImageStub(),
        ["https://cdn.example.test/p1.jpg", "https://cdn.example.test/p2.jpg"],
    )

    assert rows[0]["project_id"] == 22
    assert rows[0]["project_slug"] == "sun-festo-town"
    assert rows[0]["sort_order"] == 0
    assert rows[0]["is_primary"] is True
    assert rows[1]["is_primary"] is False


@pytest.mark.asyncio
async def test_project_publish_survives_embedding_failure(monkeypatch):
    async def fake_publish_batch(rows):
        assert rows[0]["slug"] == "project-publish-1"
        return [type("PersistedProject", (), {"id": 201, "slug": "project-publish-1"})()]

    monkeypatch.setattr(pi, "publish_project_batch", fake_publish_batch)
    monkeypatch.setattr(pi, "BGEEmbedder", lambda **kwargs: FailingEmbedder())
    monkeypatch.setattr(pi, "ensure_vector_extension", noop_ensure_vector_extension)

    result = await pi.ingest_project_rows([sample_project_row()], batch_size=1)

    assert result["published"] == 1
    assert result["indexed"] == 0
    assert result["chunks"] == 0
    assert result["publish_errors"] == 0
    assert result["index_errors"] == 1


@pytest.mark.asyncio
async def test_project_parser_record_indexes_after_publish(monkeypatch):
    async def fake_publish_batch(rows):
        return [type("PersistedProject", (), {"id": 202, "slug": rows[0]["slug"]})()]

    async def fake_index_batch(projects_with_chunks, *, embedder):
        assert projects_with_chunks[0][1]
        return {
            "indexed": 1,
            "chunks": len(projects_with_chunks[0][1]),
            "index_errors": 0,
        }

    monkeypatch.setattr(pi, "publish_project_batch", fake_publish_batch)
    monkeypatch.setattr(pi, "index_project_batch", fake_index_batch)
    monkeypatch.setattr(pi, "BGEEmbedder", lambda **kwargs: StubEmbedder())
    monkeypatch.setattr(pi, "ensure_vector_extension", noop_ensure_vector_extension)

    result = await pi.ingest_project_rows([sample_project_row()], batch_size=1)

    assert result["published"] == 1
    assert result["indexed"] == 1
    assert result["chunks"] >= 1
    assert result["publish_errors"] == 0
    assert result["index_errors"] == 0
