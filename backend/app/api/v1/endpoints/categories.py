import logging
from typing import Any, Dict, Union

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import get_current_admin_user, get_current_user
from app.core.database import get_db
from app.core.exceptions import CategoryNotFound
from app.crud.category import crud_category
from app.models.user import User
from app.schemas.category import CategoryCreate, CategoryResponse, CategoryUpdate
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


@router.get("/", response_model=ListResponse[CategoryResponse])
def read_categories(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = Query(default=10000, le=10000),
    current_user: User = Depends(get_current_user),
    # Search parameters
    search: str = Query(None, description="Search in name, description"),
    # Filter parameters
    is_active: bool = Query(None, description="Filter by active status"),
    # Date range filters
    created_from: str = Query(
        None, description="Filter by creation date from (YYYY-MM-DD)"
    ),
    created_to: str = Query(
        None, description="Filter by creation date to (YYYY-MM-DD)"
    ),
) -> Any:
    """
    Retrieve categories with optional search and filtering.
    """
    # Build filter parameters
    filter_params = {
        "search": search,
        "is_active": is_active,
        "created_from": created_from,
        "created_to": created_to,
    }

    categories = crud_category.get_multi_with_filters(
        db, skip=skip, limit=limit, **filter_params
    )
    total_count = crud_category.count_with_filters(db, **filter_params)

    return ListResponse(
        message=Messages.CATEGORIES_RETRIEVED,
        data=categories,
        meta={
            "total": total_count,
            "skip": skip,
            "limit": limit,
            "filters": filter_params,
        },
    )


@router.get("/active", response_model=ListResponse[CategoryResponse])
def read_active_categories(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = Query(default=10000, le=10000),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Retrieve active categories.
    """
    categories = crud_category.get_active(db, skip=skip, limit=limit)
    total_count = crud_category.count_active(db)
    return ListResponse(
        message=Messages.CATEGORIES_RETRIEVED,
        data=categories,
        meta={"total": total_count, "skip": skip, "limit": limit},
    )


@router.post("/", response_model=CreateResponse[CategoryResponse])
def create_category(
    *,
    db: Session = Depends(get_db),
    category_in: CategoryCreate,
    current_user: User = Depends(get_current_admin_user),
) -> Any:
    """
    Create new category (Admin only).
    """
    try:
        category = crud_category.create(db, obj_in=category_in)
        return CreateResponse(message=Messages.CATEGORY_CREATED, data=category)
    except IntegrityError as e:
        db.rollback()
        if "UNIQUE constraint failed" in str(e):
            raise HTTPException(
                status_code=400, detail=Messages.CATEGORY_ALREADY_EXISTS
            )
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to create category due to database constraint",
            )


@router.get("/{category_id}", response_model=SuccessResponse[CategoryResponse])
def read_category(
    *,
    db: Session = Depends(get_db),
    category_id: int,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Get category by ID.
    """
    category = crud_category.get(db, id=category_id)
    if not category:
        raise CategoryNotFound(category_id)
    return SuccessResponse(message=Messages.DATA_RETRIEVED, data=category)


@router.put("/{category_id}", response_model=UpdateResponse[CategoryResponse])
def update_category(
    *,
    db: Session = Depends(get_db),
    category_id: int,
    category_in: CategoryUpdate,
    current_user: User = Depends(get_current_admin_user),
) -> Any:
    """
    Update a category (Admin only).
    """
    category = crud_category.get(db, id=category_id)
    if not category:
        raise CategoryNotFound(category_id)

    try:
        category = crud_category.update(db, db_obj=category, obj_in=category_in)
        return UpdateResponse(message=Messages.CATEGORY_UPDATED, data=category)
    except IntegrityError as e:
        db.rollback()
        if "UNIQUE constraint failed" in str(e):
            raise HTTPException(
                status_code=400, detail=Messages.CATEGORY_ALREADY_EXISTS
            )
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to update category due to database constraint",
            )


@router.delete("/{category_id}", response_model=Union[DeleteResponse, Dict[str, Any]])
def delete_category(
    *,
    db: Session = Depends(get_db),
    category_id: int,
    current_user: User = Depends(get_current_admin_user),
) -> Any:
    """
    Delete a category (Admin only).
    """
    category = crud_category.get(db, id=category_id)
    if not category:
        raise CategoryNotFound(category_id)

    try:
        crud_category.remove(db, id=category_id)
        return DeleteResponse(message=Messages.CATEGORY_DELETED)
    except ValueError as e:
        # Business constraint - return structured response, not HTTP error
        return {
            "success": False,
            "message": str(e),
            "constraint_type": "business_rule",
            "details": {
                "category_id": category_id,
                "category_name": category.name,
                "reason": "associated_books",
            },
        }
    except Exception as e:
        # Technical error - still use HTTP exception
        logger.error(f"Unexpected error deleting category {category_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# PUBLIC ENDPOINTS FOR USER SITE (No Authentication Required)
@router.get("/public/", response_model=ListResponse[CategoryResponse])
def read_public_categories(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = Query(default=10000, le=10000),
) -> Any:
    """
    Get active categories for public access (User Site).
    """
    categories = crud_category.get_active_categories(db, skip=skip, limit=limit)
    total_count = crud_category.count_active(db)
    return ListResponse(
        message=Messages.CATEGORIES_RETRIEVED,
        data=categories,
        meta={"total": total_count, "skip": skip, "limit": limit},
    )


@router.get("/public/{category_id}", response_model=SuccessResponse[CategoryResponse])
def read_public_category(
    *,
    db: Session = Depends(get_db),
    category_id: int,
) -> Any:
    """
    Get category details for public access (User Site).
    """
    category = crud_category.get_active_category(db, id=category_id)
    if not category:
        raise CategoryNotFound(category_id)
    return SuccessResponse(message=Messages.DATA_RETRIEVED, data=category)
