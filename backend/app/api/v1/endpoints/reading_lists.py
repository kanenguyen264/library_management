from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.crud.reading_list import crud_reading_list, crud_reading_list_item
from app.models.user import User
from app.schemas.reading_list import (
    ReadingListCreate,
    ReadingListItemCreate,
    ReadingListItemResponse,
    ReadingListResponse,
    ReadingListUpdate,
    ReadingListWithItems,
)
from app.schemas.response import (
    CreateResponse,
    DeleteResponse,
    ListResponse,
    Messages,
    UpdateResponse,
)

router = APIRouter()


@router.get("/", response_model=ListResponse[ReadingListResponse])
def read_reading_lists(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = Query(default=10000, le=10000),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Retrieve reading lists. Admin users see all reading lists (including inactive),
    regular users see only their own active reading lists.
    """
    # Check if user is admin
    if current_user.is_admin:
        # Admin gets all reading lists (including inactive ones)
        reading_lists = crud_reading_list.get_all_for_admin(db, skip=skip, limit=limit)
        total_count = crud_reading_list.count_all_for_admin(db)
    else:
        # Regular users get only their own active reading lists
        reading_lists = crud_reading_list.get_by_user(
            db, user_id=current_user.id, skip=skip, limit=limit
        )
        total_count = crud_reading_list.count_by_user(db, user_id=current_user.id)

    return ListResponse(
        message=Messages.READING_LISTS_RETRIEVED,
        data=reading_lists,
        meta={"total": total_count, "skip": skip, "limit": limit},
    )


@router.post(
    "/",
    response_model=CreateResponse[ReadingListResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_reading_list(
    *,
    db: Session = Depends(get_db),
    reading_list_in: ReadingListCreate,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Create new reading list.
    """
    # Set current user as owner
    reading_list_in.user_id = current_user.id

    # Check for duplicate name
    existing_list = crud_reading_list.get_by_user_and_name(
        db, user_id=current_user.id, name=reading_list_in.name
    )
    if existing_list:
        raise HTTPException(
            status_code=400, detail="You already have a reading list with this name"
        )

    reading_list = crud_reading_list.create(db, obj_in=reading_list_in)
    return CreateResponse(message=Messages.READING_LIST_CREATED, data=reading_list)


@router.get("/public", response_model=ListResponse[ReadingListResponse])
def read_public_reading_lists_short(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = Query(default=10000, le=10000),
) -> Any:
    """
    Retrieve public reading lists (User Site) - short endpoint for frontend compatibility.
    """
    reading_lists = crud_reading_list.get_public_lists(db, skip=skip, limit=limit)
    total_count = crud_reading_list.count_public_lists(db)
    return ListResponse(
        message=Messages.READING_LISTS_RETRIEVED,
        data=reading_lists,
        meta={"total": total_count, "skip": skip, "limit": limit},
    )


@router.get("/public/lists", response_model=ListResponse[ReadingListResponse])
def read_public_reading_lists(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = Query(default=10000, le=10000),
) -> Any:
    """
    Retrieve public reading lists (User Site).
    """
    reading_lists = crud_reading_list.get_public_lists(db, skip=skip, limit=limit)
    total_count = crud_reading_list.count_public_lists(db)
    return ListResponse(
        message=Messages.READING_LISTS_RETRIEVED,
        data=reading_lists,
        meta={"total": total_count, "skip": skip, "limit": limit},
    )


@router.get("/{reading_list_id}")
def read_reading_list(
    *,
    db: Session = Depends(get_db),
    reading_list_id: int,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Retrieve a reading list with items.
    """
    reading_list = crud_reading_list.get_with_items(db, id=reading_list_id)
    if not reading_list:
        raise HTTPException(status_code=404, detail=Messages.READING_LIST_NOT_FOUND)

    # Check permissions - must be owner or public list
    if reading_list.user_id != current_user.id and not reading_list.is_public:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    # Manually serialize to avoid forward reference issues
    response_data = {
        "success": True,
        "message": Messages.DATA_RETRIEVED,
        "data": {
            "id": reading_list.id,
            "name": reading_list.name,
            "description": reading_list.description,
            "is_public": reading_list.is_public,
            "is_active": reading_list.is_active,
            "user_id": reading_list.user_id,
            "created_at": reading_list.created_at.isoformat()
            if reading_list.created_at
            else None,
            "updated_at": reading_list.updated_at.isoformat()
            if reading_list.updated_at
            else None,
            "items": [
                {
                    "id": item.id,
                    "reading_list_id": item.reading_list_id,
                    "book_id": item.book_id,
                    "notes": item.notes,
                    "order_index": item.order_index,
                    "created_at": item.created_at.isoformat()
                    if item.created_at
                    else None,
                    "updated_at": item.updated_at.isoformat()
                    if item.updated_at
                    else None,
                    "book": {
                        "id": item.book.id,
                        "title": item.book.title,
                        "isbn": item.book.isbn,
                        "description": item.book.description,
                        "pages": item.book.pages,
                        "language": item.book.language,
                        "cover_url": item.book.cover_url,
                        "author_id": item.book.author_id,
                        "category_id": item.book.category_id,
                    }
                    if item.book
                    else None,
                }
                for item in reading_list.items
            ],
        },
        "errors": None,
        "meta": None,
    }

    return response_data


@router.put("/{reading_list_id}", response_model=UpdateResponse[ReadingListResponse])
def update_reading_list(
    *,
    db: Session = Depends(get_db),
    reading_list_id: int,
    reading_list_in: ReadingListUpdate,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Update a reading list.
    """
    reading_list = crud_reading_list.get(db, id=reading_list_id)
    if not reading_list:
        raise HTTPException(status_code=404, detail=Messages.READING_LIST_NOT_FOUND)
    if reading_list.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    reading_list = crud_reading_list.update(
        db, db_obj=reading_list, obj_in=reading_list_in
    )
    return UpdateResponse(message=Messages.READING_LIST_UPDATED, data=reading_list)


@router.delete("/{reading_list_id}", response_model=DeleteResponse)
def delete_reading_list(
    *,
    db: Session = Depends(get_db),
    reading_list_id: int,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Delete a reading list.
    """
    reading_list = crud_reading_list.get(db, id=reading_list_id)
    if not reading_list:
        raise HTTPException(status_code=404, detail=Messages.READING_LIST_NOT_FOUND)
    if reading_list.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    crud_reading_list.remove(db, id=reading_list_id)
    return DeleteResponse(message=Messages.READING_LIST_DELETED)


# Reading List Items


@router.post(
    "/{reading_list_id}/items",
    response_model=CreateResponse[ReadingListItemResponse],
    status_code=status.HTTP_201_CREATED,
)
def add_reading_list_item(
    *,
    db: Session = Depends(get_db),
    reading_list_id: int,
    item_in: ReadingListItemCreate,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Add a book to reading list.
    """
    # Check if reading list exists and user owns it
    reading_list = crud_reading_list.get(db, id=reading_list_id)
    if not reading_list:
        raise HTTPException(status_code=404, detail=Messages.READING_LIST_NOT_FOUND)
    if reading_list.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    # Set reading list ID
    item_in.reading_list_id = reading_list_id

    # Check if book is already in reading list
    existing_item = crud_reading_list_item.get_by_reading_list_and_book(
        db, reading_list_id=reading_list_id, book_id=item_in.book_id
    )
    if existing_item:
        raise HTTPException(
            status_code=400, detail="Book is already in this reading list"
        )

    item = crud_reading_list_item.create(db, obj_in=item_in)
    return CreateResponse(message=Messages.READING_LIST_ITEM_ADDED, data=item)


@router.post(
    "/{reading_list_id}/books/{book_id}",
    response_model=CreateResponse[ReadingListItemResponse],
    status_code=status.HTTP_201_CREATED,
)
def add_book_to_reading_list(
    *,
    db: Session = Depends(get_db),
    reading_list_id: int,
    book_id: int,
    notes: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Add a book to reading list (alternative endpoint for tests).
    """
    # Check if reading list exists and user owns it
    reading_list = crud_reading_list.get(db, id=reading_list_id)
    if not reading_list:
        raise HTTPException(status_code=404, detail=Messages.READING_LIST_NOT_FOUND)
    if reading_list.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    # Check if book exists
    from app.crud.book import crud_book

    book = crud_book.get(db, id=book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    # Check if book is already in reading list
    existing_item = crud_reading_list_item.get_by_reading_list_and_book(
        db, reading_list_id=reading_list_id, book_id=book_id
    )
    if existing_item:
        raise HTTPException(
            status_code=400, detail="Book is already in this reading list"
        )

    item = crud_reading_list_item.add_book_to_list(
        db, reading_list_id=reading_list_id, book_id=book_id, notes=notes
    )
    return CreateResponse(message=Messages.READING_LIST_ITEM_ADDED, data=item)


@router.delete("/{reading_list_id}/books/{book_id}", response_model=DeleteResponse)
def remove_book_from_reading_list(
    *,
    db: Session = Depends(get_db),
    reading_list_id: int,
    book_id: int,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Remove a book from reading list (alternative endpoint for tests).
    """
    # Check if reading list exists and user owns it
    reading_list = crud_reading_list.get(db, id=reading_list_id)
    if not reading_list:
        raise HTTPException(status_code=404, detail=Messages.READING_LIST_NOT_FOUND)
    if reading_list.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    item = crud_reading_list_item.remove_book_from_list(
        db, reading_list_id=reading_list_id, book_id=book_id
    )
    if not item:
        raise HTTPException(status_code=404, detail="Book not found in reading list")

    return DeleteResponse(message=Messages.READING_LIST_ITEM_REMOVED)


@router.put(
    "/{reading_list_id}/reorder", response_model=UpdateResponse[ReadingListResponse]
)
def reorder_reading_list_items(
    *,
    db: Session = Depends(get_db),
    reading_list_id: int,
    reorder_data: List[dict],
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Reorder items in reading list.
    """
    # Check if reading list exists and user owns it
    reading_list = crud_reading_list.get(db, id=reading_list_id)
    if not reading_list:
        raise HTTPException(status_code=404, detail=Messages.READING_LIST_NOT_FOUND)
    if reading_list.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    # Convert reorder data to the format expected by CRUD
    book_orders = [(item["book_id"], item["order"]) for item in reorder_data]

    success = crud_reading_list_item.reorder_items(
        db, reading_list_id=reading_list_id, book_orders=book_orders
    )

    if not success:
        raise HTTPException(status_code=400, detail="Failed to reorder items")

    return UpdateResponse(
        message="Reading list items reordered successfully", data=reading_list
    )


# Force rebuild models to resolve forward references
try:
    from app.schemas.reading_list import ReadingListItemWithDetails

    ReadingListWithItems.model_rebuild()
    ReadingListItemWithDetails.model_rebuild()
except Exception:
    pass  # Ignore rebuild errors during import
