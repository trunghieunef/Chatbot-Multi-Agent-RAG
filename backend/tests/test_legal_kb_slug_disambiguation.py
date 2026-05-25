"""Tests for the slug disambiguation helper that prevents one legal file from
silently overwriting another when their derived titles collide."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Article
from data_pipeline.ingestors.legal_kb_ingestor import _resolve_unique_slug


@pytest_asyncio.fixture()
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    # Create only the articles table to keep the in-memory DB minimal.
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Article.__table__.create(sync_conn))
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as s:
        yield s
    await engine.dispose()


@pytest.mark.asyncio
async def test_resolve_unique_slug_returns_base_when_no_existing_article(session):
    slug = await _resolve_unique_slug(session, "luat-dat-dai-2024", digest="a" * 64)

    assert slug == "luat-dat-dai-2024"


@pytest.mark.asyncio
async def test_resolve_unique_slug_reuses_base_for_same_digest(session):
    digest = "b" * 64
    session.add(
        Article(
            title="Luật Đất đai",
            body="...",
            category="legal",
            url="legal://luat-dat-dai",
            metadata_json={"sha256": digest, "slug": "luat-dat-dai"},
        )
    )
    await session.commit()

    slug = await _resolve_unique_slug(session, "luat-dat-dai", digest=digest)

    # Same digest → same source file re-ingest → reuse the existing slug.
    assert slug == "luat-dat-dai"


@pytest.mark.asyncio
async def test_resolve_unique_slug_disambiguates_collision_for_different_digest(session):
    session.add(
        Article(
            title="Luật Đất đai",
            body="...",
            category="legal",
            url="legal://luat-dat-dai",
            metadata_json={"sha256": "c" * 64, "slug": "luat-dat-dai"},
        )
    )
    await session.commit()

    new_digest = "d" * 64
    slug = await _resolve_unique_slug(session, "luat-dat-dai", digest=new_digest)

    # Different digest, same base slug → suffix with the new digest's prefix.
    assert slug == f"luat-dat-dai-{new_digest[:8]}"


@pytest.mark.asyncio
async def test_resolve_unique_slug_disambiguates_when_existing_metadata_lacks_sha(session):
    """An article inserted before the M4 review fix may have NULL or no sha256.
    The helper must NOT mistakenly reuse the base slug — that would overwrite
    the legacy article."""
    session.add(
        Article(
            title="Luật Đất đai",
            body="...",
            category="legal",
            url="legal://luat-dat-dai",
            metadata_json=None,
        )
    )
    await session.commit()

    new_digest = "e" * 64
    slug = await _resolve_unique_slug(session, "luat-dat-dai", digest=new_digest)

    assert slug == f"luat-dat-dai-{new_digest[:8]}"
