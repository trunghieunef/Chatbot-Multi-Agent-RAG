from datetime import datetime

from pydantic import BaseModel, Field


class ProjectCardResponse(BaseModel):
    id: int
    name: str
    slug: str | None = None
    developer: str | None = None
    location: str | None = None
    district: str | None = None
    city: str | None = None
    total_units: int | None = None
    price_range: str | None = None
    area_range: str | None = None
    status: str | None = None
    project_type: str | None = None
    description: str | None = None
    amenities: list[str] = Field(default_factory=list)
    url: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True
