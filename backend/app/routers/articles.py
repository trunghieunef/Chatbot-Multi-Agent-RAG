"""
Articles API router.

Public endpoints for browsing market/news articles.
"""

import math

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.article import Article
from app.models.article_image import ArticleImage
from app.schemas.article import ArticleCardResponse
from app.schemas.common import PaginatedResponse


router = APIRouter(prefix="/articles", tags=["Articles"])


def _summary(body: str | None, limit: int = 160) -> str | None:
    if not body:
        return None
    normalized = " ".join(body.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit].rstrip()}..."


def article_card_response(
    article: Article,
    image_urls: list[str] | None = None,
) -> ArticleCardResponse:
    response = ArticleCardResponse.model_validate(article)
    urls = image_urls or []
    response.summary = _summary(response.body)
    response.image_urls = urls
    response.primary_image_url = urls[0] if urls else None
    return response


async def _article_image_map(db: AsyncSession, article_ids: list[int]) -> dict[int, list[str]]:
    if not article_ids:
        return {}
    result = await db.execute(
        select(ArticleImage)
        .where(ArticleImage.article_id.in_(article_ids))
        .order_by(ArticleImage.article_id, ArticleImage.sort_order, ArticleImage.id)
    )
    images_by_article: dict[int, list[str]] = {article_id: [] for article_id in article_ids}
    for image in result.scalars().all():
        images_by_article.setdefault(image.article_id, []).append(image.image_url)
    return images_by_article


def apply_article_filters(query, params: dict):
    filters = []
    category = params.get("category")

    if category:
        filters.append(Article.category == category)
    else:
        filters.append(or_(Article.category.is_(None), Article.category != "legal"))

    if params.get("search"):
        term = f"%{params['search']}%"
        filters.append(or_(Article.title.ilike(term), Article.body.ilike(term)))

    target = query if query is not None else select(Article)
    return target.where(and_(*filters))


def apply_article_sort(query, sort: str | None):
    target = query if query is not None else select(Article)
    if sort == "oldest":
        return target.order_by(Article.post_date.asc().nullslast(), Article.created_at.asc())
    return target.order_by(Article.post_date.desc().nullslast(), Article.created_at.desc())


@router.get("", response_model=PaginatedResponse)
async def get_articles(
    search: str | None = None,
    category: str | None = None,
    sort: str | None = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=12, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    params = {"search": search, "category": category}

    count_query = apply_article_filters(select(func.count()).select_from(Article), params)
    total = (await db.execute(count_query)).scalar() or 0

    query = apply_article_filters(select(Article), params)
    query = apply_article_sort(query, sort).offset((page - 1) * limit).limit(limit)
    result = await db.execute(query)
    articles = result.scalars().all()
    image_map = await _article_image_map(db, [article.id for article in articles])

    return PaginatedResponse(
        items=[article_card_response(article, image_map.get(article.id, [])) for article in articles],
        total=total,
        page=page,
        limit=limit,
        total_pages=math.ceil(total / limit) if total > 0 else 0,
    )


@router.get("/{article_id}", response_model=ArticleCardResponse)
async def get_article_detail(
    article_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Article).where(Article.id == article_id))
    article = result.scalar_one_or_none()
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    image_map = await _article_image_map(db, [article.id])
    return article_card_response(article, image_map.get(article.id, []))
