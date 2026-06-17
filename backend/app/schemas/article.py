from datetime import date, datetime

from pydantic import BaseModel


class ArticleCardResponse(BaseModel):
    id: int
    title: str
    body: str | None = None
    summary: str | None = None
    category: str | None = None
    source: str | None = None
    post_date: date | None = None
    url: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True
