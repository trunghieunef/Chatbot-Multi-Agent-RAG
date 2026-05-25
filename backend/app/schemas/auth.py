"""
Pydantic schemas for authentication.
"""

from pydantic import BaseModel, EmailStr, Field


class UserRegisterRequest(BaseModel):
    """User registration."""
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=100)
    full_name: str | None = None
    phone: str | None = None


class UserLoginRequest(BaseModel):
    """User login."""
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """JWT token response."""
    access_token: str
    token_type: str = "bearer"
    user: "UserResponse"


class UserResponse(BaseModel):
    """Public user info."""
    id: int
    email: str
    full_name: str | None = None
    phone: str | None = None
    avatar_url: str | None = None

    class Config:
        from_attributes = True
