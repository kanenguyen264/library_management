from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class AuthorBase(BaseModel):
    name: str
    bio: Optional[str] = None
    birth_date: Optional[date] = None
    death_date: Optional[date] = None
    nationality: Optional[str] = None
    website: Optional[str] = None
    image_url: Optional[str] = None


class AuthorCreate(AuthorBase):
    pass


class AuthorUpdate(BaseModel):
    name: Optional[str] = None
    bio: Optional[str] = None
    birth_date: Optional[date] = None
    death_date: Optional[date] = None
    nationality: Optional[str] = None
    website: Optional[str] = None
    image_url: Optional[str] = None


class AuthorInDB(AuthorBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None


class AuthorResponse(AuthorBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    book_count: int = 0
