from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_admin_user, get_current_user
from app.core.database import get_db
from app.crud.reading_progress import crud_reading_progress
from app.crud.user import crud_user
from app.models.user import User
from app.schemas.reading_progress import (
    ReadingProgressResponse,
    ReadingProgressUpdate,
    ReadingProgressWithDetails,
)
from app.schemas.response import (
    CreateResponse,
    DeleteResponse,
    ListResponse,
    Messages,
    SuccessResponse,
    UpdateResponse,
)

router = APIRouter()


@router.get("/")
def read_reading_progress(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = Query(default=10000, le=10000),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Retrieve reading progress.
    Admin: Get all reading progress with user and book details
    User: Get only their own progress
    """
    if crud_user.is_admin(current_user):
        # Admin: Get all reading progress with user and book details
        progress = crud_reading_progress.get_multi_with_details(
            db, skip=skip, limit=limit
        )
        total_count = crud_reading_progress.count(db)
    else:
        # Regular user: Get only their own progress
        progress = crud_reading_progress.get_by_user(
            db, user_id=current_user.id, skip=skip, limit=limit
        )
        total_count = crud_reading_progress.count_by_user(db, user_id=current_user.id)

    # Manual serialization to avoid TypeAdapter issues
    progress_data = []
    for p in progress:
        progress_item = {
            "id": p.id,
            "user_id": p.user_id,
            "book_id": p.book_id,
            "current_page": p.current_page,
            "total_pages": p.total_pages,
            "progress_percentage": p.progress_percentage,
            "reading_time_minutes": p.reading_time_minutes,
            "status": p.status,
            "is_completed": p.is_completed,
            "notes": p.notes,
            "started_at": p.started_at.isoformat() if p.started_at else None,
            "completed_at": p.completed_at.isoformat() if p.completed_at else None,
            "last_read_at": p.last_read_at.isoformat() if p.last_read_at else None,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        }

        # Add book details if available
        if hasattr(p, "book") and p.book:
            progress_item["book"] = {
                "id": p.book.id,
                "title": p.book.title,
                "isbn": p.book.isbn,
                "description": p.book.description,
                "pages": p.book.pages,
                "language": p.book.language,
                "cover_url": p.book.cover_url,
                "author_id": p.book.author_id,
                "category_id": p.book.category_id,
            }

        # Add user details if available (for admin)
        if hasattr(p, "user") and p.user:
            progress_item["user"] = {
                "id": p.user.id,
                "email": p.user.email,
                "username": p.user.username,
                "full_name": p.user.full_name,
            }

        progress_data.append(progress_item)

    return {
        "success": True,
        "message": "Reading progress retrieved successfully",
        "data": progress_data,
        "errors": None,
        "meta": {"total": total_count, "skip": skip, "limit": limit},
    }


@router.get("/admin/all", response_model=ListResponse[ReadingProgressWithDetails])
def read_all_progress_admin(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = Query(default=10000, le=10000),
    search: str = Query(None, description="Search in user names/email or book titles"),
    user_id: int = Query(None, description="Filter by user ID"),
    book_id: int = Query(None, description="Filter by book ID"),
    status: str = Query(
        None, description="Filter by status (reading, completed, dropped)"
    ),
    last_read_from: str = Query(
        None, description="Filter by last read date from (ISO format)"
    ),
    last_read_to: str = Query(
        None, description="Filter by last read date to (ISO format)"
    ),
    current_user: User = Depends(get_current_admin_user),
) -> Any:
    """
    Get all reading progress from all users with advanced filtering (Admin only).
    """
    progress = crud_reading_progress.get_multi_with_filters(
        db,
        skip=skip,
        limit=limit,
        search=search,
        user_id=user_id,
        book_id=book_id,
        status=status,
        last_read_from=last_read_from,
        last_read_to=last_read_to,
    )
    total_count = crud_reading_progress.count_with_filters(
        db,
        search=search,
        user_id=user_id,
        book_id=book_id,
        status=status,
        last_read_from=last_read_from,
        last_read_to=last_read_to,
    )
    return ListResponse(
        message=Messages.READING_PROGRESS_RETRIEVED,
        data=progress,
        meta={"total": total_count, "skip": skip, "limit": limit},
    )


@router.post("/", response_model=CreateResponse[ReadingProgressResponse])
def create_progress(
    *,
    db: Session = Depends(get_db),
    progress_in: ReadingProgressUpdate,  # Use Update schema to avoid requiring user_id
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Create or update reading progress.
    """
    # Validate book_id is provided
    if not progress_in.book_id:
        raise HTTPException(status_code=422, detail="book_id is required")

    # Check if progress already exists for this user and book
    existing_progress = crud_reading_progress.get_by_user_and_book(
        db, user_id=current_user.id, book_id=progress_in.book_id
    )

    if existing_progress:
        # Update existing progress
        progress = crud_reading_progress.update(
            db, db_obj=existing_progress, obj_in=progress_in
        )
        return CreateResponse(message=Messages.READING_PROGRESS_UPDATED, data=progress)
    else:
        # Create new progress
        progress_data = progress_in.model_dump(exclude_unset=True)
        progress_data["user_id"] = current_user.id

        from app.schemas.reading_progress import ReadingProgressCreate

        create_data = ReadingProgressCreate(**progress_data)
        progress = crud_reading_progress.create(db, obj_in=create_data)
        return CreateResponse(message=Messages.READING_PROGRESS_CREATED, data=progress)


@router.get("/book/{book_id}")
def read_progress_for_book(
    *,
    db: Session = Depends(get_db),
    book_id: int,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Get reading progress for a specific book.
    """
    progress = crud_reading_progress.get_by_user_and_book(
        db, user_id=current_user.id, book_id=book_id
    )
    # Return None when no progress found, or convert to Pydantic model for serialization
    if progress is None:
        return SuccessResponse(message=Messages.READING_PROGRESS_NOT_FOUND, data=None)
    return SuccessResponse(
        message=Messages.READING_PROGRESS_RETRIEVED,
        data=ReadingProgressResponse.model_validate(progress),
    )


@router.put("/book/{book_id}", response_model=UpdateResponse[ReadingProgressResponse])
def update_progress_for_book(
    *,
    db: Session = Depends(get_db),
    book_id: int,
    progress_in: ReadingProgressUpdate,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Update reading progress for a specific book.
    """
    progress = crud_reading_progress.get_by_user_and_book(
        db, user_id=current_user.id, book_id=book_id
    )

    if not progress:
        # Create new progress if it doesn't exist
        progress_data = progress_in.model_dump(exclude_unset=True)
        progress_data["user_id"] = current_user.id
        progress_data["book_id"] = book_id

        from app.schemas.reading_progress import ReadingProgressCreate

        create_data = ReadingProgressCreate(**progress_data)
        progress = crud_reading_progress.create(db, obj_in=create_data)

        return UpdateResponse(message=Messages.READING_PROGRESS_CREATED, data=progress)
    else:
        # Update existing progress
        progress = crud_reading_progress.update(db, db_obj=progress, obj_in=progress_in)
        return UpdateResponse(message=Messages.READING_PROGRESS_UPDATED, data=progress)


@router.delete("/book/{book_id}", response_model=DeleteResponse)
def delete_progress_for_book(
    *,
    db: Session = Depends(get_db),
    book_id: int,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Delete reading progress for a specific book.
    """
    progress = crud_reading_progress.get_by_user_and_book(
        db, user_id=current_user.id, book_id=book_id
    )

    if not progress:
        raise HTTPException(status_code=404, detail=Messages.READING_PROGRESS_NOT_FOUND)

    crud_reading_progress.remove(db, id=progress.id)
    return DeleteResponse(message=Messages.READING_PROGRESS_DELETED)


@router.delete("/{progress_id}", response_model=DeleteResponse)
def delete_progress(
    *,
    db: Session = Depends(get_db),
    progress_id: int,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Delete reading progress by ID.
    Admin can delete any progress, users can only delete their own.
    """
    progress = crud_reading_progress.get(db, id=progress_id)

    if not progress:
        raise HTTPException(status_code=404, detail=Messages.READING_PROGRESS_NOT_FOUND)

    # Check if user can delete this progress
    if not crud_user.is_admin(current_user) and progress.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Not enough permissions to delete this reading progress",
        )

    crud_reading_progress.remove(db, id=progress_id)
    return DeleteResponse(message=Messages.READING_PROGRESS_DELETED)


@router.get("/completed")
def read_completed_books(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = Query(default=10000, le=10000),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Get completed books for current user.
    """
    completed_progress = crud_reading_progress.get_completed_by_user(
        db, user_id=current_user.id, skip=skip, limit=limit
    )

    # Manual serialization
    progress_data = []
    for p in completed_progress:
        progress_item = {
            "id": p.id,
            "user_id": p.user_id,
            "book_id": p.book_id,
            "current_page": p.current_page,
            "total_pages": p.total_pages,
            "progress_percentage": p.progress_percentage,
            "reading_time_minutes": p.reading_time_minutes,
            "status": p.status,
            "is_completed": p.is_completed,
            "notes": p.notes,
            "started_at": p.started_at.isoformat() if p.started_at else None,
            "completed_at": p.completed_at.isoformat() if p.completed_at else None,
            "last_read_at": p.last_read_at.isoformat() if p.last_read_at else None,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        }

        # Add book details if available
        if hasattr(p, "book") and p.book:
            progress_item["book"] = {
                "id": p.book.id,
                "title": p.book.title,
                "isbn": p.book.isbn,
                "description": p.book.description,
                "pages": p.book.pages,
                "language": p.book.language,
                "cover_url": p.book.cover_url,
                "author_id": p.book.author_id,
                "category_id": p.book.category_id,
            }

        progress_data.append(progress_item)

    return progress_data


@router.get("/currently-reading")
def read_currently_reading(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = Query(default=10000, le=10000),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Get currently reading books for current user.
    """
    current_reading = crud_reading_progress.get_currently_reading(
        db, user_id=current_user.id, skip=skip, limit=limit
    )

    # Manual serialization
    progress_data = []
    for p in current_reading:
        progress_item = {
            "id": p.id,
            "user_id": p.user_id,
            "book_id": p.book_id,
            "current_page": p.current_page,
            "total_pages": p.total_pages,
            "progress_percentage": p.progress_percentage,
            "reading_time_minutes": p.reading_time_minutes,
            "status": p.status,
            "is_completed": p.is_completed,
            "notes": p.notes,
            "started_at": p.started_at.isoformat() if p.started_at else None,
            "completed_at": p.completed_at.isoformat() if p.completed_at else None,
            "last_read_at": p.last_read_at.isoformat() if p.last_read_at else None,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        }

        # Add book details if available
        if hasattr(p, "book") and p.book:
            progress_item["book"] = {
                "id": p.book.id,
                "title": p.book.title,
                "isbn": p.book.isbn,
                "description": p.book.description,
                "pages": p.book.pages,
                "language": p.book.language,
                "cover_url": p.book.cover_url,
                "author_id": p.book.author_id,
                "category_id": p.book.category_id,
            }

        progress_data.append(progress_item)

    return progress_data


@router.get("/stats", response_model=dict)
def read_user_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Get reading statistics for current user.
    """
    stats = crud_reading_progress.get_user_stats(db, user_id=current_user.id)
    return stats
