import logging
from datetime import datetime
from typing import Any, Dict, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth import get_current_admin_user, get_current_user
from app.core.database import get_db
from app.core.exceptions import AuthorNotFound
from app.crud.author import crud_author
from app.models.book import Book
from app.models.user import User
from app.schemas.author import AuthorCreate, AuthorResponse, AuthorUpdate
from app.schemas.response import (
    CreateResponse,
    DeleteResponse,
    ListResponse,
    Messages,
    SuccessResponse,
    UpdateResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", response_model=ListResponse[AuthorResponse])
def read_authors(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = Query(default=20, le=10000),
    search: Optional[str] = Query(
        None, description="Search by author name, bio, or nationality"
    ),
    nationality: Optional[str] = Query(None, description="Filter by nationality"),
    created_from: Optional[datetime] = Query(
        None, description="Filter authors created from this date"
    ),
    created_to: Optional[datetime] = Query(
        None, description="Filter authors created until this date"
    ),
    birth_from: Optional[datetime] = Query(
        None, description="Filter authors born from this date"
    ),
    birth_to: Optional[datetime] = Query(
        None, description="Filter authors born until this date"
    ),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Retrieve authors with search and filter capabilities.
    """
    # Build filter parameters
    filters = {}
    if search:
        filters["search"] = search
    if nationality:
        filters["nationality"] = nationality
    if created_from:
        filters["created_from"] = created_from
    if created_to:
        filters["created_to"] = created_to
    if birth_from:
        filters["birth_from"] = birth_from
    if birth_to:
        filters["birth_to"] = birth_to

    # Get filtered authors with book counts
    authors_with_counts = crud_author.get_authors_with_book_count_filtered(
        db, skip=skip, limit=limit, filters=filters
    )
    total_count = crud_author.count_with_filters(db, filters=filters)

    # Convert to response format
    authors = []
    for author_row in authors_with_counts:
        # Unpack the tuple (Author, book_count)
        author, book_count = author_row
        author_data = {
            "id": author.id,
            "name": author.name,
            "bio": author.bio,
            "nationality": author.nationality,
            "website": author.website,
            "image_url": author.image_url,
            "birth_date": author.birth_date,
            "death_date": author.death_date,
            "created_at": author.created_at,
            "updated_at": author.updated_at,
            "book_count": book_count,
        }
        authors.append(author_data)

    return ListResponse(
        message=Messages.AUTHORS_RETRIEVED,
        data=authors,
        meta={"total": total_count, "skip": skip, "limit": limit},
    )


@router.get("/search", response_model=ListResponse[AuthorResponse])
def search_authors(
    *,
    db: Session = Depends(get_db),
    q: str = Query(..., min_length=1),
    skip: int = 0,
    limit: int = Query(default=100, le=100),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Search authors by name.
    """
    authors = crud_author.search_by_name(db, name=q, skip=skip, limit=limit)
    total_count = crud_author.count_search_by_name(db, name=q)
    return ListResponse(
        message=Messages.SEARCH_COMPLETED,
        data=authors,
        meta={"query": q, "total": total_count, "skip": skip, "limit": limit},
    )


@router.post("/", response_model=CreateResponse[AuthorResponse])
def create_author(
    *,
    db: Session = Depends(get_db),
    author_in: AuthorCreate,
    current_user: User = Depends(get_current_admin_user),
) -> Any:
    """
    Create new author (Admin only).
    """
    # Check if author with same name already exists
    existing_author = crud_author.get_by_name(db, name=author_in.name)
    if existing_author:
        raise HTTPException(
            status_code=400,
            detail=f"Author with name '{author_in.name}' already exists",
        )

    author = crud_author.create(db, obj_in=author_in)
    return CreateResponse(message=Messages.AUTHOR_CREATED, data=author)


@router.get("/{author_id}", response_model=SuccessResponse[AuthorResponse])
def read_author(
    *,
    db: Session = Depends(get_db),
    author_id: int,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Get author by ID.
    """
    author = crud_author.get(db, id=author_id)
    if not author:
        raise AuthorNotFound(author_id)
    return SuccessResponse(message=Messages.DATA_RETRIEVED, data=author)


@router.put("/{author_id}", response_model=UpdateResponse[AuthorResponse])
def update_author(
    *,
    db: Session = Depends(get_db),
    author_id: int,
    author_in: AuthorUpdate,
    current_user: User = Depends(get_current_admin_user),
) -> Any:
    """
    Update an author (Admin only).
    """
    author = crud_author.get(db, id=author_id)
    if not author:
        raise AuthorNotFound(author_id)

    # Check if author with same name already exists (except current one)
    if author_in.name:
        existing_author = crud_author.get_by_name(db, name=author_in.name)
        if existing_author and existing_author.id != author_id:
            raise HTTPException(
                status_code=400,
                detail=f"Author with name '{author_in.name}' already exists",
            )

    author = crud_author.update(db, db_obj=author, obj_in=author_in)
    return UpdateResponse(message=Messages.AUTHOR_UPDATED, data=author)


@router.delete("/{author_id}", response_model=Union[DeleteResponse, Dict[str, Any]])
def delete_author(
    *,
    db: Session = Depends(get_db),
    author_id: int,
    current_user: User = Depends(get_current_admin_user),
) -> Any:
    """
    Delete an author (Admin only).
    """
    author = crud_author.get(db, id=author_id)
    if not author:
        raise AuthorNotFound(author_id)

    # Check if author has associated books
    book_count = (
        db.query(func.count(Book.id)).filter(Book.author_id == author_id).scalar()
    )
    if book_count > 0:
        return {
            "success": False,
            "message": f"Cannot delete author. There are {book_count} books associated with this author.",
            "constraint_type": "business_rule",
            "details": {
                "author_id": author_id,
                "author_name": author.name,
                "book_count": book_count,
                "reason": "associated_books",
            },
        }

    crud_author.remove(db, id=author_id)
    return DeleteResponse(message=Messages.AUTHOR_DELETED)


# PUBLIC ENDPOINTS FOR USER SITE (No Authentication Required)
@router.get("/public/", response_model=ListResponse[AuthorResponse])
def read_public_authors(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = Query(default=10000, le=10000),
) -> Any:
    """
    Get authors for public access (User Site).
    """
    authors = crud_author.get_public_authors(db, skip=skip, limit=limit)
    total_count = crud_author.count(db)
    return ListResponse(
        message=Messages.AUTHORS_RETRIEVED,
        data=authors,
        meta={"total": total_count, "skip": skip, "limit": limit},
    )


@router.get("/public/{author_id}", response_model=SuccessResponse[AuthorResponse])
def read_public_author(
    *,
    db: Session = Depends(get_db),
    author_id: int,
) -> Any:
    """
    Get author details for public access (User Site).
    """
    author = crud_author.get_public_author(db, id=author_id)
    if not author:
        raise AuthorNotFound(author_id)
    return SuccessResponse(message=Messages.DATA_RETRIEVED, data=author)
