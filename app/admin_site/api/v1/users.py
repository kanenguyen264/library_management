from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status, Body
from sqlalchemy.orm import Session
from datetime import datetime

from app.common.db.session import get_db
from app.admin_site.api.deps import get_current_admin, check_admin_permissions
from app.user_site.models.user import User, Gender
from app.admin_site.services import user_service
from app.user_site.schemas.user import (
    UserCreate,
    UserUpdate,
    UserResponse,
    UserListResponse,
    UserStatsResponse,
)
from app.cache.decorators import cached
from app.core.exceptions import NotFoundException, ConflictException

router = APIRouter()


@router.get("/", response_model=UserListResponse)
async def get_users(
    skip: int = Query(0, description="Number of records to skip"),
    limit: int = Query(100, description="Max number of records to return"),
    search: Optional[str] = Query(
        None, description="Search by username, email or name"
    ),
    sort_by: str = Query("id", description="Field to sort by"),
    sort_desc: bool = Query(False, description="Sort in descending order"),
    only_active: bool = Query(False, description="Show only active users"),
    only_premium: bool = Query(False, description="Show only premium users"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin_permissions(["user:read", "user:list"])),
):
    """
    Get list of users with filtering options.
    """
    try:
        users = await user_service.get_all_users(
            db=db,
            skip=skip,
            limit=limit,
            search=search,
            sort_by=sort_by,
            sort_desc=sort_desc,
            only_active=only_active,
            only_premium=only_premium,
            admin_id=current_admin.id,
        )

        total_count = await user_service.count_users(
            db=db,
            search=search,
            only_active=only_active,
            only_premium=only_premium,
        )

        return UserListResponse(
            items=users,
            total=total_count,
            page=skip // limit + 1 if limit > 0 else 1,
            size=limit,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving users: {str(e)}",
        )


@router.get("/stats", response_model=UserStatsResponse)
async def get_user_statistics(
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin_permissions(["user:read", "stats:read"])),
):
    """
    Get user statistics.
    """
    try:
        stats = await user_service.get_user_statistics(
            db=db,
            admin_id=current_admin.id,
        )
        return stats
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving user statistics: {str(e)}",
        )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int = Path(..., description="User ID"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin_permissions(["user:read"])),
):
    """
    Get a user by ID.
    """
    try:
        user = await user_service.get_user_by_id(
            db=db,
            user_id=user_id,
            admin_id=current_admin.id,
        )
        return user
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving user: {str(e)}",
        )


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin_permissions(["user:create"])),
):
    """
    Create a new user.
    """
    try:
        user = await user_service.create_user(
            db=db,
            user_data=user_data.model_dump(),
            admin_id=current_admin.id,
        )
        return user
    except ConflictException as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating user: {str(e)}",
        )


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int = Path(..., description="User ID"),
    user_data: UserUpdate = Body(...),
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin_permissions(["user:update"])),
):
    """
    Update a user.
    """
    try:
        user = await user_service.update_user(
            db=db,
            user_id=user_id,
            user_data=user_data.model_dump(exclude_unset=True),
            admin_id=current_admin.id,
        )
        return user
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ConflictException as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating user: {str(e)}",
        )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int = Path(..., description="User ID"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin_permissions(["user:delete"])),
):
    """
    Delete a user.
    """
    try:
        await user_service.delete_user(
            db=db,
            user_id=user_id,
            admin_id=current_admin.id,
        )
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting user: {str(e)}",
        )


@router.post("/{user_id}/premium", response_model=UserResponse)
async def set_premium_status(
    user_id: int = Path(..., description="User ID"),
    is_premium: bool = Body(..., embed=True),
    premium_until: Optional[datetime] = Body(None, embed=True),
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        check_admin_permissions(["user:update", "user:premium"])
    ),
):
    """
    Set or remove premium status for a user.
    """
    try:
        user = await user_service.set_premium_status(
            db=db,
            user_id=user_id,
            is_premium=is_premium,
            premium_until=premium_until,
            admin_id=current_admin.id,
        )
        return user
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error setting premium status: {str(e)}",
        )


@router.post("/{user_id}/verify-email", response_model=UserResponse)
async def verify_user_email(
    user_id: int = Path(..., description="User ID"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin_permissions(["user:update"])),
):
    """
    Manually verify a user's email.
    """
    try:
        user = await user_service.verify_user_email(
            db=db,
            user_id=user_id,
            admin_id=current_admin.id,
        )
        return user
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error verifying email: {str(e)}",
        )


@router.post("/{user_id}/deactivate", response_model=UserResponse)
async def deactivate_user(
    user_id: int = Path(..., description="User ID"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        check_admin_permissions(["user:update", "user:deactivate"])
    ),
):
    """
    Deactivate a user account.
    """
    try:
        user = await user_service.deactivate_user(
            db=db,
            user_id=user_id,
            admin_id=current_admin.id,
        )
        return user
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deactivating user: {str(e)}",
        )


@router.post("/{user_id}/reactivate", response_model=UserResponse)
async def reactivate_user(
    user_id: int = Path(..., description="User ID"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        check_admin_permissions(["user:update", "user:reactivate"])
    ),
):
    """
    Reactivate a user account.
    """
    try:
        user = await user_service.reactivate_user(
            db=db,
            user_id=user_id,
            admin_id=current_admin.id,
        )
        return user
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error reactivating user: {str(e)}",
        )
