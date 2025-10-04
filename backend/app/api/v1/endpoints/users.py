import logging
from datetime import datetime
from typing import Any, Dict, Optional, Union

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.auth import get_current_admin_user, get_current_user
from app.core.database import get_db
from app.core.exceptions import UserNotFound
from app.core.supabase_client import supabase_client
from app.crud.user import crud_user
from app.models.user import User
from app.schemas.response import (
    CreateResponse,
    DeleteResponse,
    ListResponse,
    Messages,
    SuccessResponse,
    UpdateResponse,
)
from app.schemas.user import UserCreate, UserResponse, UserUpdate

logger = logging.getLogger(__name__)
router = APIRouter()

# Avatar upload configuration
ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/gif",
}
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB


@router.get("/", response_model=ListResponse[UserResponse])
def read_users(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = Query(default=20, le=10000),
    search: Optional[str] = Query(
        None, description="Search by username, email, or full_name"
    ),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    is_admin: Optional[bool] = Query(None, description="Filter by admin status"),
    created_from: Optional[datetime] = Query(
        None, description="Filter users created from this date"
    ),
    created_to: Optional[datetime] = Query(
        None, description="Filter users created until this date"
    ),
    current_user: User = Depends(get_current_admin_user),
) -> Any:
    """
    Retrieve users with search and filter capabilities (Admin only).
    """
    # Build filter parameters
    filters = {}
    if search:
        filters["search"] = search
    if is_active is not None:
        filters["is_active"] = is_active
    if is_admin is not None:
        filters["is_admin"] = is_admin
    if created_from:
        filters["created_from"] = created_from
    if created_to:
        filters["created_to"] = created_to

    # Get filtered users
    users = crud_user.get_multi_with_filters(
        db, skip=skip, limit=limit, filters=filters
    )
    total_count = crud_user.count_with_filters(db, filters=filters)

    return ListResponse(
        message=Messages.DATA_RETRIEVED,
        data=users,
        meta={"total": total_count, "skip": skip, "limit": limit, "filters": filters},
    )


@router.post("/", response_model=CreateResponse[UserResponse])
def create_user(
    *,
    db: Session = Depends(get_db),
    user_in: UserCreate,
    current_user: User = Depends(get_current_admin_user),
) -> Any:
    """
    Create new user (Admin only).
    """
    user = crud_user.get_by_email(db, email=user_in.email)
    if user:
        raise HTTPException(
            status_code=400,
            detail=Messages.USER_ALREADY_EXISTS,
        )
    user = crud_user.create(db, obj_in=user_in)
    return CreateResponse(message=Messages.USER_CREATED, data=user)


@router.post("/upload-avatar", response_model=SuccessResponse[UserResponse])
async def upload_avatar(
    *,
    db: Session = Depends(get_db),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Upload user avatar.
    """
    # Validate file type
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail=Messages.INVALID_FILE_TYPE)

    try:
        # Read file content
        file_content = await file.read()

        # Validate file size
        if len(file_content) > MAX_IMAGE_SIZE:
            raise HTTPException(status_code=400, detail=Messages.FILE_TOO_LARGE)

        # Generate file path
        file_extension = file.filename.split(".")[-1] if file.filename else "jpg"
        file_path = f"avatars/{current_user.id}/avatar.{file_extension}"

        # Upload to Supabase Storage
        result = supabase_client.storage.from_("user-uploads").upload(
            file_path,
            file_content,
            {"content-type": file.content_type, "upsert": "true"},
        )

        if result:
            # Get public URL
            public_url = supabase_client.storage.from_("user-uploads").get_public_url(
                file_path
            )
            avatar_url = (
                public_url.get("publicUrl")
                if hasattr(public_url, "get")
                else str(public_url)
            )

            # Update user avatar URL in database
            user_update = UserUpdate(avatar_url=avatar_url)
            updated_user = crud_user.update(db, db_obj=current_user, obj_in=user_update)

            return SuccessResponse(message=Messages.FILE_UPLOADED, data=updated_user)
        else:
            raise HTTPException(status_code=500, detail="Failed to upload avatar")

    except Exception as e:
        logger.error(f"Avatar upload error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.delete("/avatar", response_model=SuccessResponse[UserResponse])
def delete_avatar(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Delete user avatar.
    """
    if not current_user.avatar_url:
        raise HTTPException(status_code=404, detail=Messages.FILE_NOT_FOUND)

    try:
        # Extract file path from avatar URL
        if current_user.avatar_url:
            # Assume the avatar URL contains the file path after the base URL
            file_path = f"avatars/{current_user.id}/"

            # Try to remove from Supabase Storage
            try:
                supabase_client.storage.from_("user-uploads").remove([file_path])
            except Exception as storage_error:
                # Log error but continue to update database
                logger.warning(
                    f"Failed to delete avatar from storage: {str(storage_error)}"
                )

        # Update user to remove avatar URL
        user_update = UserUpdate(avatar_url=None)
        updated_user = crud_user.update(db, db_obj=current_user, obj_in=user_update)

        return SuccessResponse(message=Messages.FILE_DELETED, data=updated_user)

    except Exception as e:
        logger.error(f"Avatar deletion error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Deletion failed: {str(e)}")


@router.get("/{user_id}", response_model=SuccessResponse[UserResponse])
def read_user_by_id(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Get a specific user by id.
    """
    user = crud_user.get(db, id=user_id)
    if user == current_user:
        return SuccessResponse(message=Messages.DATA_RETRIEVED, data=user)
    if not crud_user.is_admin(current_user):
        raise HTTPException(
            status_code=400, detail="The user doesn't have enough privileges"
        )
    if not user:
        raise UserNotFound(user_id)
    return SuccessResponse(message=Messages.DATA_RETRIEVED, data=user)


@router.put("/me", response_model=UpdateResponse[UserResponse])
def update_my_profile(
    *,
    db: Session = Depends(get_db),
    user_in: UserUpdate,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Update current user's profile.
    """
    # Users can only update certain fields of their own profile
    # Remove sensitive fields that only admins should be able to update
    update_data = user_in.model_dump(exclude_unset=True)

    # Remove admin-only fields
    if "is_active" in update_data:
        del update_data["is_active"]
    if "is_admin" in update_data:
        del update_data["is_admin"]

    user = crud_user.update(db, db_obj=current_user, obj_in=update_data)
    return UpdateResponse(message=Messages.USER_UPDATED, data=user)


@router.put("/{user_id}", response_model=UpdateResponse[UserResponse])
def update_user(
    *,
    db: Session = Depends(get_db),
    user_id: int,
    user_in: UserUpdate,
    current_user: User = Depends(get_current_admin_user),
) -> Any:
    """
    Update a user (Admin only).
    """
    user = crud_user.get(db, id=user_id)
    if not user:
        raise UserNotFound(user_id)

    user = crud_user.update(db, db_obj=user, obj_in=user_in)
    return UpdateResponse(message=Messages.USER_UPDATED, data=user)


@router.delete("/{user_id}", response_model=Union[DeleteResponse, Dict[str, Any]])
def delete_user(
    *,
    db: Session = Depends(get_db),
    user_id: int,
    current_user: User = Depends(get_current_admin_user),
) -> Any:
    """
    Delete a user (Admin only).
    """
    user = crud_user.get(db, id=user_id)
    if not user:
        raise UserNotFound(user_id)

    try:
        user = crud_user.remove(db, id=user_id)
        return DeleteResponse(message=Messages.USER_DELETED)
    except ValueError as e:
        # Business constraint - return structured response, not HTTP error
        return {
            "success": False,
            "message": str(e),
            "constraint_type": "business_rule",
            "details": {
                "user_id": user_id,
                "username": user.username,
                "reason": "associated_reading_progress",
            },
        }
    except Exception as e:
        # Technical error - still use HTTP exception
        logger.error(f"Unexpected error deleting user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
