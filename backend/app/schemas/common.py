"""
Pydantic schemas for common patterns: pagination, filtering, responses.
"""

from pydantic import BaseModel, Field


class PaginationParams(BaseModel):
    """Standard pagination parameters."""
    page: int = Field(default=1, ge=1, description="Page number")
    limit: int = Field(default=20, ge=1, le=100, description="Items per page")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.limit


class PaginatedResponse(BaseModel):
    """Wrapper for paginated API responses."""
    items: list
    total: int
    page: int
    limit: int
    total_pages: int


class MessageResponse(BaseModel):
    """Simple message response."""
    message: str
    success: bool = True
