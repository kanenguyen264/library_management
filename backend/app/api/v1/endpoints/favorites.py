from typing import Any, Optional
from datetime import datetime

from app.core.auth import get_current_user, get_current_admin_user
from app.core.database import get_db
from app.crud.favorite import crud_favorite
from app.models.user import User
from app.schemas.favorite import FavoriteCreate, FavoriteResponse, FavoriteWithDetails
from app.schemas.response import (
    CreateResponse,
    DeleteResponse,
    ListResponse,
    Messages,
    SuccessResponse,
)
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

router = APIRouter()


@router.get("/", response_model=ListResponse[FavoriteWithDetails])
def read_favorites(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = Query(default=10000, le=10000),
    # Admin filtering parameters
    search: Optional[str] = Query(None, description="Search by user or book name"),
    user_id: Optional[int] = Query(None, description="Filter by user ID"),
    book_id: Optional[int] = Query(None, description="Filter by book ID"),
    created_from: Optional[datetime] = Query(None, description="Filter by creation date from"),
    created_to: Optional[datetime] = Query(None, description="Filter by creation date to"),
    current_user: User = Depends(get_current_admin_user),  # Admin only
) -> Any:
    """
    Retrieve all favorites (Admin only) with filtering support.
    """
    # Use the new filtering method for admin
    favorites = crud_favorite.get_multi_with_filters(
        db,
        skip=skip,
        limit=limit,
        search=search,
        user_id=user_id,
        book_id=book_id,
        created_from=created_from,
        created_to=created_to
    )
    total_count = crud_favorite.count_with_filters(
        db,
        search=search,
        user_id=user_id,
        book_id=book_id,
        created_from=created_from,
        created_to=created_to
    )
    return ListResponse(
        message=Messages.FAVORITES_RETRIEVED,
        data=favorites,
        meta={
            "total": total_count,
            "skip": skip,
            "limit": limit
        }
    )


@router.post("/", response_model=CreateResponse[FavoriteResponse], status_code=status.HTTP_201_CREATED)
def add_favorite(
    *,
    db: Session = Depends(get_db),
    favorite_in: FavoriteCreate,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Add book to favorites.
    """
    # Set current user as the owner
    favorite_in.user_id = current_user.id
    
    # Check if favorite already exists
    existing_favorite = crud_favorite.get_by_user_and_book(
        db, user_id=current_user.id, book_id=favorite_in.book_id
    )
    if existing_favorite:
        raise HTTPException(
            status_code=400,
            detail=Messages.FAVORITE_ALREADY_EXISTS
        )
    
    favorite = crud_favorite.create(db, obj_in=favorite_in)
    return CreateResponse(
        message=Messages.FAVORITE_ADDED,
        data=favorite
    )


@router.get("/{favorite_id}", response_model=SuccessResponse[FavoriteWithDetails])
def read_favorite(
    *,
    db: Session = Depends(get_db),
    favorite_id: int,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Get favorite by ID.
    """
    favorite = crud_favorite.get_with_details(db, id=favorite_id)
    if not favorite:
        raise HTTPException(
            status_code=404,
            detail=Messages.FAVORITE_NOT_FOUND
        )
    
    # Check if user owns this favorite
    if favorite.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Not enough permissions"
        )
    
    return SuccessResponse(
        message=Messages.DATA_RETRIEVED,
        data=favorite
    )


@router.delete("/{favorite_id}", response_model=DeleteResponse)
def remove_favorite(
    *,
    db: Session = Depends(get_db),
    favorite_id: int,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Remove favorite by ID.
    """
    favorite = crud_favorite.get(db, id=favorite_id)
    if not favorite:
        raise HTTPException(
            status_code=404,
            detail=Messages.FAVORITE_NOT_FOUND
        )
    
    # Check if user owns this favorite
    if favorite.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Not enough permissions"
        )
    
    crud_favorite.remove(db, id=favorite_id)
    return DeleteResponse(
        message=Messages.FAVORITE_REMOVED
    )


@router.delete("/book/{book_id}", response_model=SuccessResponse[dict])
def remove_favorite(
    *,
    db: Session = Depends(get_db),
    book_id: int,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Remove book from favorites.
    """
    favorite = crud_favorite.get_by_user_and_book(db, user_id=current_user.id, book_id=book_id)
    if not favorite:
        raise HTTPException(
            status_code=404,
            detail=Messages.FAVORITE_NOT_FOUND
        )
    
    crud_favorite.remove(db, id=favorite.id)
    return SuccessResponse(
        message=Messages.FAVORITE_REMOVED,
        data={}
    )


# Additional endpoint with 'books' path that frontend expects
@router.delete("/books/{book_id}", response_model=SuccessResponse[dict])
def remove_favorite_books_path(
    *,
    db: Session = Depends(get_db),
    book_id: int,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Remove book from favorites (frontend compatibility endpoint).
    """
    return remove_favorite(db=db, book_id=book_id, current_user=current_user)


@router.post("/books/{book_id}", response_model=SuccessResponse[FavoriteWithDetails])
def add_favorite_books_path(
    *,
    db: Session = Depends(get_db),
    book_id: int,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Add book to favorites (frontend compatibility endpoint).
    """
    # Check if book exists and is active
    book = crud_book.get_public_book_with_details(db, id=book_id)
    if not book:
        raise HTTPException(
            status_code=404,
            detail="Book not found"
        )
    
    # Check if already favorited
    existing_favorite = crud_favorite.get_user_book_favorite(db, user_id=current_user.id, book_id=book_id)
    if existing_favorite:
        raise HTTPException(
            status_code=400,
            detail="Book is already in favorites"
        )
    
    # Create favorite
    favorite_in = FavoriteCreate(user_id=current_user.id, book_id=book_id)
    favorite = crud_favorite.create(db, obj_in=favorite_in)
    
    # Get with details for response
    favorite_with_details = crud_favorite.get_with_details(db, id=favorite.id)
    
    return SuccessResponse(
        message=Messages.FAVORITE_ADDED,
        data=favorite_with_details
    )


@router.post("/books/{book_id}/toggle", response_model=SuccessResponse[dict])
def toggle_favorite(
    *,
    db: Session = Depends(get_db),
    book_id: int,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Toggle book favorite status (add if not favorited, remove if favorited).
    """
    # Check if book exists and is active
    book = crud_book.get_public_book_with_details(db, id=book_id)
    if not book:
        raise HTTPException(
            status_code=404,
            detail="Book not found"
        )
    
    # Check if already favorited
    existing_favorite = crud_favorite.get_user_book_favorite(db, user_id=current_user.id, book_id=book_id)
    
    if existing_favorite:
        # Remove from favorites
        crud_favorite.remove(db, id=existing_favorite.id)
        return SuccessResponse(
            message=Messages.FAVORITE_REMOVED,
            data={"favorited": False, "action": "removed"}
        )
    else:
        # Add to favorites
        favorite_in = FavoriteCreate(user_id=current_user.id, book_id=book_id)
        crud_favorite.create(db, obj_in=favorite_in)
        return SuccessResponse(
            message=Messages.FAVORITE_ADDED,
            data={"favorited": True, "action": "added"}
        )


@router.get("/books/{book_id}/status", response_model=SuccessResponse[dict])
def get_favorite_status(
    *,
    db: Session = Depends(get_db),
    book_id: int,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Check if a book is favorited by the current user.
    """
    favorite = crud_favorite.get_by_user_and_book(db, user_id=current_user.id, book_id=book_id)
    
    return SuccessResponse(
        message="Favorite status retrieved",
        data={
            "book_id": book_id,
            "favorited": favorite is not None,
            "favorite_id": favorite.id if favorite else None
        }
    )


@router.get("/count", response_model=SuccessResponse[dict])
def get_favorites_count(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Get total count of user's favorites.
    """
    count = crud_favorite.get_user_favorites_count(db, user_id=current_user.id)
    
    return SuccessResponse(
        message="Favorites count retrieved",
        data={
            "user_id": current_user.id,
            "total_favorites": count
        }
    )