from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status, Body
from sqlalchemy.orm import Session
from datetime import datetime

from app.common.db.session import get_db
from app.admin_site.api.deps import get_current_admin, check_admin_permissions
from app.user_site.models.user import User
from app.user_site.models.subscription import (
    Subscription,
    SubscriptionStatus,
    SubscriptionType,
)
from app.admin_site.services import subscription_service
from app.user_site.schemas.subscription import (
    SubscriptionCreate,
    SubscriptionUpdate,
    SubscriptionResponse,
    SubscriptionListResponse,
    SubscriptionStatsResponse,
)
from app.core.exceptions import NotFoundException, ConflictException

router = APIRouter()


@router.get("/", response_model=SubscriptionListResponse)
async def get_all_subscriptions(
    skip: int = Query(0, description="Number of records to skip"),
    limit: int = Query(100, description="Max number of records to return"),
    user_id: Optional[int] = Query(None, description="Filter by user ID"),
    status: Optional[SubscriptionStatus] = Query(None, description="Filter by status"),
    subscription_type: Optional[SubscriptionType] = Query(
        None, description="Filter by subscription type"
    ),
    from_date: Optional[datetime] = Query(None, description="Filter from date"),
    to_date: Optional[datetime] = Query(None, description="Filter to date"),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_desc: bool = Query(True, description="Sort in descending order"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        check_admin_permissions(["subscription:read", "subscription:list"])
    ),
):
    """
    Get list of subscriptions with various filtering options.
    """
    try:
        subscriptions = await subscription_service.get_all_subscriptions(
            db=db,
            skip=skip,
            limit=limit,
            user_id=user_id,
            status=status,
            subscription_type=subscription_type,
            from_date=from_date,
            to_date=to_date,
            sort_by=sort_by,
            sort_desc=sort_desc,
            admin_id=current_admin.id,
        )

        total_count = await subscription_service.count_subscriptions(
            db=db,
            user_id=user_id,
            status=status,
            subscription_type=subscription_type,
            from_date=from_date,
            to_date=to_date,
        )

        return SubscriptionListResponse(
            items=subscriptions,
            total=total_count,
            page=skip // limit + 1 if limit > 0 else 1,
            size=limit,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving subscriptions: {str(e)}",
        )


@router.get("/stats", response_model=SubscriptionStatsResponse)
async def get_subscription_statistics(
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        check_admin_permissions(["subscription:read", "stats:read"])
    ),
):
    """
    Get subscription statistics.
    """
    try:
        stats = await subscription_service.get_subscription_statistics(
            db=db,
            admin_id=current_admin.id,
        )
        return stats
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving subscription statistics: {str(e)}",
        )


@router.get("/{subscription_id}", response_model=SubscriptionResponse)
async def get_subscription(
    subscription_id: int = Path(..., description="Subscription ID"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin_permissions(["subscription:read"])),
):
    """
    Get a subscription by ID.
    """
    try:
        subscription = await subscription_service.get_subscription_by_id(
            db=db,
            subscription_id=subscription_id,
            admin_id=current_admin.id,
        )
        return subscription
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving subscription: {str(e)}",
        )


@router.get("/user/{user_id}/active", response_model=SubscriptionResponse)
async def get_user_active_subscription(
    user_id: int = Path(..., description="User ID"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        check_admin_permissions(["subscription:read", "user:read"])
    ),
):
    """
    Get a user's active subscription.
    """
    try:
        subscription = await subscription_service.get_user_active_subscription(
            db=db,
            user_id=user_id,
        )
        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No active subscription found for user with ID {user_id}",
            )
        return subscription
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving active subscription: {str(e)}",
        )


@router.post(
    "/", response_model=SubscriptionResponse, status_code=status.HTTP_201_CREATED
)
async def create_subscription(
    subscription_data: SubscriptionCreate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin_permissions(["subscription:create"])),
):
    """
    Create a new subscription.
    """
    try:
        subscription = await subscription_service.create_subscription(
            db=db,
            subscription_data=subscription_data.model_dump(),
            admin_id=current_admin.id,
        )
        return subscription
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating subscription: {str(e)}",
        )


@router.put("/{subscription_id}", response_model=SubscriptionResponse)
async def update_subscription(
    subscription_id: int = Path(..., description="Subscription ID"),
    subscription_data: SubscriptionUpdate = Body(...),
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin_permissions(["subscription:update"])),
):
    """
    Update a subscription.
    """
    try:
        subscription = await subscription_service.update_subscription(
            db=db,
            subscription_id=subscription_id,
            subscription_data=subscription_data.model_dump(exclude_unset=True),
            admin_id=current_admin.id,
        )
        return subscription
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating subscription: {str(e)}",
        )


@router.delete("/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subscription(
    subscription_id: int = Path(..., description="Subscription ID"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin_permissions(["subscription:delete"])),
):
    """
    Delete a subscription.
    """
    try:
        await subscription_service.delete_subscription(
            db=db,
            subscription_id=subscription_id,
            admin_id=current_admin.id,
        )
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting subscription: {str(e)}",
        )


@router.post("/{subscription_id}/cancel", response_model=SubscriptionResponse)
async def cancel_subscription(
    subscription_id: int = Path(..., description="Subscription ID"),
    reason: Optional[str] = Body(None, embed=True),
    db: Session = Depends(get_db),
    current_admin: User = Depends(check_admin_permissions(["subscription:update"])),
):
    """
    Cancel a subscription.
    """
    try:
        subscription = await subscription_service.cancel_subscription(
            db=db,
            subscription_id=subscription_id,
            reason=reason,
            admin_id=current_admin.id,
        )
        return subscription
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ConflictException as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error cancelling subscription: {str(e)}",
        )


@router.post("/process-expired", response_model=int)
async def process_expired_subscriptions(
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        check_admin_permissions(["subscription:update", "system:maintenance"])
    ),
):
    """
    Process expired subscriptions. Updates status and user premium status.

    Returns:
        Number of subscriptions processed.
    """
    try:
        count = await subscription_service.check_expired_subscriptions(db=db)
        return count
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing expired subscriptions: {str(e)}",
        )
