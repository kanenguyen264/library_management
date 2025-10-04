import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_admin_user, get_current_user
from app.core.database import get_db
from app.core.exceptions import BookNotFound
from app.crud.author import crud_author
from app.crud.book import crud_book
from app.crud.category import crud_category
from app.models.user import User
from app.schemas.book import BookCreate, BookResponse, BookUpdate, BookWithDetails
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


@router.get("/", response_model=ListResponse[BookWithDetails])
def read_books(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = Query(default=10000, le=10000),
    current_user: User = Depends(get_current_user),
    # Search parameters
    search: str = Query(None, description="Search in title, description"),
    # Filter parameters
    author_id: int = Query(None, description="Filter by author ID"),
    category_id: int = Query(None, description="Filter by category ID"),
    is_active: bool = Query(None, description="Filter by active status"),
    is_free: bool = Query(None, description="Filter by free/paid status"),
    # Date range filters
    publication_date_from: str = Query(
        None, description="Filter by publication date from (YYYY-MM-DD)"
    ),
    publication_date_to: str = Query(
        None, description="Filter by publication date to (YYYY-MM-DD)"
    ),
) -> Any:
    """
    Retrieve books with optional search and filtering.
    """
    # Build filter parameters
    filter_params = {
        "search": search,
        "author_id": author_id,
        "category_id": category_id,
        "is_active": is_active,
        "is_free": is_free,
        "publication_date_from": publication_date_from,
        "publication_date_to": publication_date_to,
    }

    books = crud_book.get_multi_with_filters(
        db, skip=skip, limit=limit, **filter_params
    )
    total_count = crud_book.count_with_filters(db, **filter_params)

    return ListResponse(
        message=Messages.BOOKS_RETRIEVED,
        data=books,
        meta={
            "total": total_count,
            "skip": skip,
            "limit": limit,
            "filters": filter_params,
        },
    )


@router.get("/active", response_model=ListResponse[BookWithDetails])
def read_active_books(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = Query(default=10000, le=10000),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Retrieve active books.
    """
    books = crud_book.get_active_books_with_details(db, skip=skip, limit=limit)
    total_count = crud_book.count_active_books(db)
    return ListResponse(
        message=Messages.BOOKS_RETRIEVED,
        data=books,
        meta={"total": total_count, "skip": skip, "limit": limit},
    )


@router.get("/search", response_model=ListResponse[BookWithDetails])
def search_books(
    *,
    db: Session = Depends(get_db),
    q: str = Query(..., min_length=1),
    skip: int = 0,
    limit: int = Query(default=100, le=100),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Search books by title, description.
    """
    books = crud_book.search_books(db, query=q, skip=skip, limit=limit)
    total_count = crud_book.count_search_books(db, query=q)
    return ListResponse(
        message=Messages.BOOKS_RETRIEVED,
        data=books,
        meta={"total": total_count, "skip": skip, "limit": limit},
    )


@router.get("/author/{author_id}", response_model=ListResponse[BookWithDetails])
def read_books_by_author(
    *,
    db: Session = Depends(get_db),
    author_id: int,
    skip: int = 0,
    limit: int = Query(default=100, le=100),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Retrieve books by author.
    """
    # Check if author exists
    author = crud_author.get(db, id=author_id)
    if not author:
        books = []
        total_count = 0
    else:
        books = crud_book.get_by_author(db, author_id=author_id, skip=skip, limit=limit)
        total_count = crud_book.count_by_author(db, author_id=author_id)

    return ListResponse(
        message=Messages.BOOKS_RETRIEVED,
        data=books,
        meta={"total": total_count, "skip": skip, "limit": limit},
    )


@router.get("/category/{category_id}", response_model=ListResponse[BookWithDetails])
def read_books_by_category(
    *,
    db: Session = Depends(get_db),
    category_id: int,
    skip: int = 0,
    limit: int = Query(default=100, le=100),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Retrieve books by category.
    """
    # Check if category exists
    category = crud_category.get(db, id=category_id)
    if not category:
        books = []
        total_count = 0
    else:
        books = crud_book.get_by_category(
            db, category_id=category_id, skip=skip, limit=limit
        )
        total_count = crud_book.count_by_category(db, category_id=category_id)

    return ListResponse(
        message=Messages.BOOKS_RETRIEVED,
        data=books,
        meta={"total": total_count, "skip": skip, "limit": limit},
    )


@router.get("/free", response_model=ListResponse[BookWithDetails])
def read_free_books(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = Query(default=100, le=100),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Retrieve free books.
    """
    books = crud_book.get_free_books(db, skip=skip, limit=limit)
    total_count = crud_book.count_free_books(db)
    return ListResponse(
        message=Messages.BOOKS_RETRIEVED,
        data=books,
        meta={"total": total_count, "skip": skip, "limit": limit},
    )


@router.post("/", response_model=CreateResponse[BookResponse])
def create_book(
    *,
    db: Session = Depends(get_db),
    book_in: BookCreate,
    current_user: User = Depends(get_current_admin_user),
) -> Any:
    """
    Create new book (Admin only).
    """
    # Validate author exists
    if book_in.author_id is not None and book_in.author_id > 0:
        author = crud_author.get(db, id=book_in.author_id)
        if not author:
            raise HTTPException(
                status_code=400, detail=f"Author with id {book_in.author_id} not found"
            )
    else:
        raise HTTPException(status_code=400, detail="Author is required")

    # Validate category exists
    if book_in.category_id is not None and book_in.category_id > 0:
        category = crud_category.get(db, id=book_in.category_id)
        if not category:
            raise HTTPException(
                status_code=400,
                detail=f"Category with id {book_in.category_id} not found",
            )
    else:
        raise HTTPException(status_code=400, detail="Category is required")

    book = crud_book.create(db, obj_in=book_in)
    return CreateResponse(message=Messages.BOOK_CREATED, data=book)


@router.get("/{book_id}", response_model=SuccessResponse[BookWithDetails])
def read_book(
    *,
    db: Session = Depends(get_db),
    book_id: int,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Get book by ID.
    """
    book = crud_book.get_with_details(db, id=book_id)
    if not book:
        raise BookNotFound(book_id)
    return SuccessResponse(message=Messages.DATA_RETRIEVED, data=book)


@router.put("/{book_id}", response_model=UpdateResponse[BookResponse])
def update_book(
    *,
    db: Session = Depends(get_db),
    book_id: int,
    book_in: BookUpdate,
    current_user: User = Depends(get_current_admin_user),
) -> Any:
    """
    Update a book and cleanup old files when replaced (Admin only).
    """
    book = crud_book.get(db, id=book_id)
    if not book:
        raise BookNotFound(book_id)

    # Validate author exists if provided
    if book_in.author_id is not None:
        if book_in.author_id <= 0:
            raise HTTPException(
                status_code=400, detail="Author ID must be greater than 0"
            )
        author = crud_author.get(db, id=book_in.author_id)
        if not author:
            raise HTTPException(
                status_code=400, detail=f"Author with id {book_in.author_id} not found"
            )

    # Validate category exists if provided
    if book_in.category_id is not None:
        if book_in.category_id <= 0:
            raise HTTPException(
                status_code=400, detail="Category ID must be greater than 0"
            )
        category = crud_category.get(db, id=book_in.category_id)
        if not category:
            raise HTTPException(
                status_code=400,
                detail=f"Category with id {book_in.category_id} not found",
            )

    book = crud_book.update(db, db_obj=book, obj_in=book_in)
    return UpdateResponse(message=Messages.BOOK_UPDATED, data=book)


@router.delete("/{book_id}", response_model=DeleteResponse)
def delete_book(
    *,
    db: Session = Depends(get_db),
    book_id: int,
    current_user: User = Depends(get_current_admin_user),
) -> Any:
    """
    Delete a book (Admin only).
    """
    book = crud_book.get(db, id=book_id)
    if not book:
        raise BookNotFound(book_id)

    crud_book.remove(db, id=book_id)
    return DeleteResponse(message=Messages.BOOK_DELETED)


# PUBLIC ENDPOINTS FOR USER SITE (No Authentication Required)
@router.get("/public/", response_model=ListResponse[BookWithDetails])
def read_public_books(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = Query(default=100, le=100),
) -> Any:
    """
    Get active books for public access (User Site).
    """
    books = crud_book.get_active_books_with_details(db, skip=skip, limit=limit)
    total_count = crud_book.count_active_books(db)
    return ListResponse(
        message=Messages.BOOKS_RETRIEVED,
        data=books,
        meta={"total": total_count, "skip": skip, "limit": limit},
    )


@router.get("/public/free", response_model=ListResponse[BookWithDetails])
def read_public_free_books(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = Query(default=100, le=100),
) -> Any:
    """
    Get free books for public access (User Site).
    """
    try:
        books = crud_book.get_public_free_books(db, skip=skip, limit=limit)
        total_count = crud_book.count_free_books(db)

        # Validate books data before returning
        validated_books = []
        for book in books:
            if book and hasattr(book, "id"):  # Basic validation
                validated_books.append(book)

        return ListResponse(
            message=Messages.BOOKS_RETRIEVED,
            data=validated_books,
            meta={"total": total_count, "skip": skip, "limit": limit},
        )
    except Exception as e:
        logger.error(f"Error retrieving free books: {str(e)}")
        # Return empty list instead of failing
        return ListResponse(
            message="Free books retrieved with errors",
            data=[],
            meta={"total": 0, "skip": skip, "limit": limit, "error": str(e)},
        )


@router.get("/public/featured", response_model=ListResponse[BookWithDetails])
def read_public_featured_books(
    db: Session = Depends(get_db),
    limit: int = Query(default=10, le=20),
) -> Any:
    """
    Get featured books for public access (User Site).
    """
    try:
        books = crud_book.get_featured_books(db, limit=limit)

        # Validate books data before returning
        validated_books = []
        for book in books:
            if book and hasattr(book, "id"):  # Basic validation
                validated_books.append(book)

        return ListResponse(
            message=Messages.BOOKS_RETRIEVED,
            data=validated_books,
            meta={"total": len(validated_books), "skip": 0, "limit": limit},
        )
    except Exception as e:
        logger.error(f"Error retrieving featured books: {str(e)}")
        # Return empty list instead of failing
        return ListResponse(
            message="Featured books retrieved with errors",
            data=[],
            meta={"total": 0, "skip": 0, "limit": limit, "error": str(e)},
        )


@router.get("/public/search/", response_model=ListResponse[BookWithDetails])
def search_public_books(
    *,
    db: Session = Depends(get_db),
    q: str = Query(..., min_length=1),
    skip: int = 0,
    limit: int = Query(default=100, le=100),
) -> Any:
    """
    Search books for public access (User Site).
    """
    books = crud_book.search_public_books(db, query=q, skip=skip, limit=limit)
    total_count = crud_book.count_search_books(db, query=q)
    return ListResponse(
        message=Messages.SEARCH_COMPLETED,
        data=books,
        meta={"query": q, "total": total_count, "skip": skip, "limit": limit},
    )


@router.get(
    "/public/category/{category_id}", response_model=ListResponse[BookWithDetails]
)
def read_public_books_by_category(
    *,
    db: Session = Depends(get_db),
    category_id: int,
    skip: int = 0,
    limit: int = Query(default=100, le=100),
) -> Any:
    """
    Get books by category for public access (User Site).
    """
    books = crud_book.get_public_books_by_category(
        db, category_id=category_id, skip=skip, limit=limit
    )
    total_count = crud_book.count_by_category(db, category_id=category_id)
    return ListResponse(
        message=Messages.BOOKS_RETRIEVED,
        data=books,
        meta={"total": total_count, "skip": skip, "limit": limit},
    )


@router.get("/public/author/{author_id}", response_model=ListResponse[BookWithDetails])
def read_public_books_by_author(
    *,
    db: Session = Depends(get_db),
    author_id: int,
    skip: int = 0,
    limit: int = Query(default=100, le=100),
) -> Any:
    """
    Get books by author for public access (User Site).
    """
    books = crud_book.get_public_books_by_author(
        db, author_id=author_id, skip=skip, limit=limit
    )
    total_count = crud_book.count_by_author(db, author_id=author_id)
    return ListResponse(
        message=Messages.BOOKS_RETRIEVED,
        data=books,
        meta={"total": total_count, "skip": skip, "limit": limit},
    )


@router.get("/public/{book_id}", response_model=SuccessResponse[BookWithDetails])
def read_public_book(
    *,
    db: Session = Depends(get_db),
    book_id: int,
) -> Any:
    book = crud_book.get_public_book_with_details(db, id=book_id)
    if not book:
        raise BookNotFound(book_id)
    return SuccessResponse(message=Messages.DATA_RETRIEVED, data=book)
