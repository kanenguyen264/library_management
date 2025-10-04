from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import get_current_admin_user, get_current_user
from app.core.database import get_db
from app.core.exceptions import BookNotFound, ChapterNotFound, DuplicateChapter
from app.crud.book import crud_book
from app.crud.chapter import crud_chapter
from app.models.user import User
from app.schemas.chapter import ChapterCreate, ChapterResponse, ChapterUpdate
from app.schemas.response import (
    CreateResponse,
    DeleteResponse,
    ListResponse,
    Messages,
    SuccessResponse,
    UpdateResponse,
)

router = APIRouter()


@router.get("/", response_model=ListResponse[ChapterResponse])
def read_chapters(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = Query(default=10000, le=10000),
    search: str = Query(None, description="Search in chapter title and content"),
    is_published: bool = Query(None, description="Filter by published status"),
    is_active: bool = Query(None, description="Filter by active status"),
    book_id: int = Query(None, description="Filter by book ID"),
    created_from: str = Query(
        None, description="Filter chapters created from this date (YYYY-MM-DD)"
    ),
    created_to: str = Query(
        None, description="Filter chapters created until this date (YYYY-MM-DD)"
    ),
    current_user: User = Depends(get_current_admin_user),
) -> Any:
    """
    Retrieve chapters with filtering (Admin only).
    """
    chapters = crud_chapter.get_multi_with_filters(
        db,
        skip=skip,
        limit=limit,
        search=search,
        is_published=is_published,
        is_active=is_active,
        book_id=book_id,
        created_from=created_from,
        created_to=created_to,
    )
    total_count = crud_chapter.count_with_filters(
        db,
        search=search,
        is_published=is_published,
        is_active=is_active,
        book_id=book_id,
        created_from=created_from,
        created_to=created_to,
    )
    return ListResponse(
        message=Messages.CHAPTERS_RETRIEVED,
        data=chapters,
        meta={"total": total_count, "skip": skip, "limit": limit},
    )


@router.get("/published", response_model=ListResponse[ChapterResponse])
def read_published_chapters(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = Query(default=10000, le=10000),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Retrieve all published chapters.
    """
    chapters = crud_chapter.get_all_published_chapters(db, skip=skip, limit=limit)
    total_count = crud_chapter.count_all_published_chapters(db)
    return ListResponse(
        message=Messages.CHAPTERS_RETRIEVED,
        data=chapters,
        meta={"total": total_count, "skip": skip, "limit": limit},
    )


@router.get("/book/{book_id}", response_model=ListResponse[ChapterResponse])
def read_chapters_by_book(
    *,
    db: Session = Depends(get_db),
    book_id: int,
    skip: int = 0,
    limit: int = Query(default=10000, le=10000),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Get chapters by book ID.
    """
    # Validate book exists
    book = crud_book.get(db, id=book_id)
    if not book:
        raise BookNotFound(book_id)

    chapters = crud_chapter.get_by_book(db, book_id=book_id, skip=skip, limit=limit)
    total_count = crud_chapter.count_by_book(db, book_id=book_id)
    return ListResponse(
        message=Messages.CHAPTERS_RETRIEVED,
        data=chapters,
        meta={"book_id": book_id, "total": total_count, "skip": skip, "limit": limit},
    )


@router.get("/published/book/{book_id}", response_model=ListResponse[ChapterResponse])
def read_published_chapters_by_book(
    *,
    db: Session = Depends(get_db),
    book_id: int,
    skip: int = 0,
    limit: int = Query(default=10000, le=10000),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Get published chapters by book ID.
    """
    # Validate book exists
    book = crud_book.get(db, id=book_id)
    if not book:
        raise BookNotFound(book_id)

    chapters = crud_chapter.get_published_chapters(
        db, book_id=book_id, skip=skip, limit=limit
    )
    total_count = crud_chapter.count_published_chapters(db, book_id=book_id)
    return ListResponse(
        message=Messages.CHAPTERS_RETRIEVED,
        data=chapters,
        meta={"book_id": book_id, "total": total_count, "skip": skip, "limit": limit},
    )


@router.post(
    "/",
    response_model=CreateResponse[ChapterResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_chapter(
    *,
    db: Session = Depends(get_db),
    chapter_in: ChapterCreate,
    current_user: User = Depends(get_current_admin_user),
) -> Any:
    """
    Create new chapter (Admin only).
    """
    # Validate book exists
    if chapter_in.book_id is not None and chapter_in.book_id > 0:
        book = crud_book.get(db, id=chapter_in.book_id)
        if not book:
            raise HTTPException(
                status_code=400, detail=f"Book with id {chapter_in.book_id} not found"
            )
    else:
        raise HTTPException(status_code=400, detail="Book is required")

    # Check if chapter number already exists for this book
    existing_chapter = crud_chapter.get_by_book_and_chapter_number(
        db, book_id=chapter_in.book_id, chapter_number=chapter_in.chapter_number
    )
    if existing_chapter:
        raise DuplicateChapter(chapter_in.book_id, chapter_in.chapter_number)

    try:
        chapter = crud_chapter.create(db, obj_in=chapter_in)
        return CreateResponse(message=Messages.CHAPTER_CREATED, data=chapter)
    except IntegrityError:
        db.rollback()
        raise DuplicateChapter(chapter_in.book_id, chapter_in.chapter_number)


@router.get("/{chapter_id}", response_model=SuccessResponse[ChapterResponse])
def read_chapter(
    *,
    db: Session = Depends(get_db),
    chapter_id: int,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Get chapter by ID.
    """
    chapter = crud_chapter.get(db, id=chapter_id)
    if not chapter:
        raise ChapterNotFound(chapter_id)
    return SuccessResponse(message=Messages.DATA_RETRIEVED, data=chapter)


@router.put("/{chapter_id}", response_model=UpdateResponse[ChapterResponse])
def update_chapter(
    *,
    db: Session = Depends(get_db),
    chapter_id: int,
    chapter_in: ChapterUpdate,
    current_user: User = Depends(get_current_admin_user),
) -> Any:
    """
    Update a chapter (Admin only).
    """
    chapter = crud_chapter.get(db, id=chapter_id)
    if not chapter:
        raise ChapterNotFound(chapter_id)

    # Validate book exists if provided
    if chapter_in.book_id is not None:
        if chapter_in.book_id <= 0:
            raise HTTPException(
                status_code=400, detail="Book ID must be greater than 0"
            )
        book = crud_book.get(db, id=chapter_in.book_id)
        if not book:
            raise HTTPException(
                status_code=400, detail=f"Book with id {chapter_in.book_id} not found"
            )

    # Check for duplicate chapter number if both book_id and chapter_number are being updated
    if chapter_in.chapter_number is not None and (
        chapter_in.book_id is not None or chapter.book_id
    ):
        book_id = (
            chapter_in.book_id if chapter_in.book_id is not None else chapter.book_id
        )
        if (
            chapter_in.chapter_number != chapter.chapter_number
            or book_id != chapter.book_id
        ):
            existing_chapter = crud_chapter.get_by_book_and_chapter_number(
                db, book_id=book_id, chapter_number=chapter_in.chapter_number
            )
            if existing_chapter and existing_chapter.id != chapter_id:
                raise DuplicateChapter(book_id, chapter_in.chapter_number)

    try:
        chapter = crud_chapter.update(db, db_obj=chapter, obj_in=chapter_in)
        return UpdateResponse(message=Messages.CHAPTER_UPDATED, data=chapter)
    except IntegrityError:
        db.rollback()
        book_id = (
            chapter_in.book_id if chapter_in.book_id is not None else chapter.book_id
        )
        chapter_number = (
            chapter_in.chapter_number
            if chapter_in.chapter_number is not None
            else chapter.chapter_number
        )
        raise DuplicateChapter(book_id, chapter_number)


@router.delete("/{chapter_id}", response_model=DeleteResponse)
def delete_chapter(
    *,
    db: Session = Depends(get_db),
    chapter_id: int,
    current_user: User = Depends(get_current_admin_user),
) -> Any:
    """
    Delete a chapter (Admin only).
    """
    chapter = crud_chapter.get(db, id=chapter_id)
    if not chapter:
        raise ChapterNotFound(chapter_id)

    crud_chapter.remove(db, id=chapter_id)
    return DeleteResponse(message=Messages.CHAPTER_DELETED)


# PUBLIC ENDPOINTS FOR USER SITE (No Authentication Required)
@router.get("/public/book/{book_id}", response_model=ListResponse[ChapterResponse])
def read_public_chapters_by_book(
    *,
    db: Session = Depends(get_db),
    book_id: int,
    skip: int = 0,
    limit: int = Query(default=10000, le=10000),
) -> Any:
    """
    Get published chapters by book for public access (User Site).
    """
    chapters = crud_chapter.get_public_chapters_by_book(
        db, book_id=book_id, skip=skip, limit=limit
    )
    total_count = crud_chapter.count_public_chapters_by_book(db, book_id=book_id)
    return ListResponse(
        message=Messages.CHAPTERS_RETRIEVED,
        data=chapters,
        meta={"book_id": book_id, "total": total_count, "skip": skip, "limit": limit},
    )


@router.get("/public/{chapter_id}", response_model=SuccessResponse[ChapterResponse])
def read_public_chapter(
    *,
    db: Session = Depends(get_db),
    chapter_id: int,
) -> Any:
    """
    Get published chapter details for public access (User Site).
    """
    chapter = crud_chapter.get_published_chapter_with_details(db, id=chapter_id)
    if not chapter:
        raise ChapterNotFound(chapter_id)
    return SuccessResponse(message=Messages.DATA_RETRIEVED, data=chapter)


try:
    ChapterWithDetails.model_rebuild()
except Exception:
    pass  # Ignore rebuild errors during import
