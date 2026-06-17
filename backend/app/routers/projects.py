"""
Projects API router.

Public endpoints for browsing real estate development projects.
"""

import math

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.project import Project
from app.models.project_image import ProjectImage
from app.schemas.common import PaginatedResponse
from app.schemas.project import ProjectCardResponse


router = APIRouter(prefix="/projects", tags=["Projects"])


def project_card_response(
    project: Project,
    image_urls: list[str] | None = None,
) -> ProjectCardResponse:
    response = ProjectCardResponse.model_validate(project)
    urls = image_urls or []
    response.image_urls = urls
    response.primary_image_url = urls[0] if urls else None
    return response


async def _project_image_map(db: AsyncSession, project_ids: list[int]) -> dict[int, list[str]]:
    if not project_ids:
        return {}
    result = await db.execute(
        select(ProjectImage)
        .where(ProjectImage.project_id.in_(project_ids))
        .order_by(ProjectImage.project_id, ProjectImage.sort_order, ProjectImage.id)
    )
    images_by_project: dict[int, list[str]] = {project_id: [] for project_id in project_ids}
    for image in result.scalars().all():
        images_by_project.setdefault(image.project_id, []).append(image.image_url)
    return images_by_project


def apply_project_filters(query, params: dict):
    filters = []

    if params.get("search"):
        term = f"%{params['search']}%"
        filters.append(
            or_(
                Project.name.ilike(term),
                Project.description.ilike(term),
                Project.location.ilike(term),
                Project.developer.ilike(term),
            )
        )
    if params.get("city"):
        filters.append(Project.city.ilike(f"%{params['city']}%"))
    if params.get("district"):
        filters.append(Project.district.ilike(f"%{params['district']}%"))
    if params.get("project_type"):
        filters.append(Project.project_type.ilike(f"%{params['project_type']}%"))
    if params.get("status"):
        filters.append(Project.status == params["status"])

    target = query if query is not None else select(Project)
    if filters:
        target = target.where(and_(*filters))
    return target


def apply_project_sort(query, sort: str | None):
    target = query if query is not None else select(Project)
    sort_map = {
        "name_asc": Project.name.asc(),
        "name_desc": Project.name.desc(),
        "newest": Project.created_at.desc(),
    }
    return target.order_by(sort_map.get(sort, Project.created_at.desc()))


@router.get("", response_model=PaginatedResponse)
async def get_projects(
    search: str | None = None,
    city: str | None = None,
    district: str | None = None,
    project_type: str | None = None,
    status: str | None = None,
    sort: str | None = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=12, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    params = {
        "search": search,
        "city": city,
        "district": district,
        "project_type": project_type,
        "status": status,
    }

    count_query = apply_project_filters(select(func.count()).select_from(Project), params)
    total = (await db.execute(count_query)).scalar() or 0

    query = apply_project_filters(select(Project), params)
    query = apply_project_sort(query, sort).offset((page - 1) * limit).limit(limit)
    result = await db.execute(query)
    projects = result.scalars().all()
    image_map = await _project_image_map(db, [project.id for project in projects])

    return PaginatedResponse(
        items=[project_card_response(project, image_map.get(project.id, [])) for project in projects],
        total=total,
        page=page,
        limit=limit,
        total_pages=math.ceil(total / limit) if total > 0 else 0,
    )


@router.get("/{project_id}", response_model=ProjectCardResponse)
async def get_project_detail(
    project_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    image_map = await _project_image_map(db, [project.id])
    return project_card_response(project, image_map.get(project.id, []))
