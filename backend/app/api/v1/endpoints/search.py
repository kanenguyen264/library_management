from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.crud.author import crud_author
from app.crud.book import crud_book
from app.crud.category import crud_category
from app.models.user import User
from app.schemas.author import AuthorResponse
from app.schemas.book import BookWithDetails
from app.schemas.category import CategoryResponse
from app.schemas.response import ListResponse, Messages, SuccessResponse

router = APIRouter()


@router.get("/books", response_model=ListResponse[BookWithDetails])
def search_books(
    *,
    db: Session = Depends(get_db),
    q: str = Query(..., min_length=1),
    skip: int = 0,
    limit: int = Query(default=100, le=100),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Search books by title or description.
    """
    books = crud_book.search_books(db, query=q, skip=skip, limit=limit)
    total_count = crud_book.count_search_books(db, query=q)
    return ListResponse(
        message=Messages.SEARCH_COMPLETED,
        data=books,
        meta={"query": q, "total": total_count, "skip": skip, "limit": limit},
    )


@router.get("/authors", response_model=ListResponse[AuthorResponse])
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


@router.get("/categories", response_model=ListResponse[CategoryResponse])
def search_categories(
    *,
    db: Session = Depends(get_db),
    q: str = Query(..., min_length=1),
    skip: int = 0,
    limit: int = Query(default=100, le=100),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Search categories by name.
    """
    categories = crud_category.search_by_name(db, name=q, skip=skip, limit=limit)
    total_count = crud_category.count_search_by_name(db, name=q)
    return ListResponse(
        message=Messages.SEARCH_COMPLETED,
        data=categories,
        meta={"query": q, "total": total_count, "skip": skip, "limit": limit},
    )


@router.get("/all", response_model=SuccessResponse[dict])
def search_all(
    *,
    db: Session = Depends(get_db),
    q: str = Query(..., min_length=1),
    skip: int = 0,
    limit: int = Query(default=50, le=100),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Search across all entities (books, authors, categories).
    """
    books = crud_book.search_books(db, query=q, skip=skip, limit=limit)
    authors = crud_author.search_by_name(db, name=q, skip=skip, limit=limit)
    categories = crud_category.search_by_name(db, name=q, skip=skip, limit=limit)

    # Convert SQLAlchemy models to dict for proper serialization
    books_data = [BookWithDetails.model_validate(book).model_dump() for book in books]
    authors_data = [
        AuthorResponse.model_validate(author).model_dump() for author in authors
    ]
    categories_data = [
        CategoryResponse.model_validate(category).model_dump()
        for category in categories
    ]

    search_results = {
        "books": books_data,
        "authors": authors_data,
        "categories": categories_data,
        "query": q,
        "results_count": {
            "books": len(books_data),
            "authors": len(authors_data),
            "categories": len(categories_data),
        },
    }

    return SuccessResponse(message=Messages.SEARCH_COMPLETED, data=search_results)
