"""
Articles API router.

Public endpoints for browsing market/news articles.
"""

import math

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.article import Article
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


def article_card_response(article: Article) -> ArticleCardResponse:
    response = ArticleCardResponse.model_validate(article)
    response.summary = _summary(response.body)
    return response


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

    return PaginatedResponse(
        items=[article_card_response(article) for article in articles],
        total=total,
        page=page,
        limit=limit,
        total_pages=math.ceil(total / limit) if total > 0 else 0,
    )
