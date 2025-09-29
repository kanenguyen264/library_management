from typing import Dict, Any, List, Optional
from fastapi import (
    APIRouter,
    Depends,
    Path,
    Query,
    HTTPException,
    status,
    Body,
    Request,
)
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone

from app.common.db.session import get_db
from app.user_site.api.deps import (
    get_current_active_user,
    get_current_user)
from app.user_site.api.v1 import throttle_requests
from app.user_site.models.user import User
from app.user_site.schemas.following import (
    FollowingResponse,
    FollowerResponse,
    FollowingListResponse,
    FollowerListResponse,
    SuggestedUserResponse,
    FollowStatsResponse,
    UserNetworkResponse,
    FollowResponse,
    FollowSuggestionResponse,
    FollowActivityResponse,
    FollowNotificationSettings,
)
from app.user_site.services.following_service import FollowingService
from app.user_site.services.notification_service import NotificationService
from app.logging.setup import get_logger
from app.monitoring.metrics import track_request_time
from app.core.exceptions import (
    NotFoundException,
    ForbiddenException,
    BadRequestException,
    ServerException,
)
from app.cache.decorators import cache_response as cache, invalidate_cache
from app.security.audit.audit_trails import AuditLogger
from app.common.utils.pagination import PaginationParams

logger = get_logger(__name__)
router = APIRouter()
audit_logger = AuditLogger()


@router.post(
    "/{user_id}/follow",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Follow user",
    description="Follow a user",
)
@track_request_time
@throttle_requests(max_requests=10, window_seconds=60)
@invalidate_cache(
    namespace="following", tags=["follow_counts", "followers", "following"]
)
async def follow_user(
    request: Request,
    user_id: int = Path(..., description="User ID to follow"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Follow a user."""
    try:
        if user_id == current_user.id:
            raise BadRequestException(detail="You cannot follow yourself")

        following_service = FollowingService(db)
        notification_service = NotificationService(db)
        result = await following_service.toggle_follow(
            follower_id=current_user.id, followed_id=user_id
        )

        # Send notification to the followed user
        if result["following"]:
            await notification_service.create_follow_notification(
                follower_id=current_user.id, followed_id=user_id
            )

        # Log audit event
        client_ip = request.client.host if request else "unknown"
        audit_logger.log_event(
            actor_id=current_user.id,
            action="follow_user",
            resource_type="user",
            resource_id=user_id,
            ip_address=client_ip,
        )

        return result
    except BadRequestException:
        raise
    except Exception as e:
        logger.error(f"Error toggling follow for user {user_id}: {str(e)}")
        raise ServerException(detail=f"Failed to toggle follow status: {str(e)}")


@router.post(
    "/{user_id}/unfollow",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Unfollow user",
    description="Unfollow a user",
)
@track_request_time
@invalidate_cache(
    namespace="following", tags=["follow_counts", "followers", "following"]
)
async def unfollow_user(
    request: Request,
    user_id: int = Path(..., description="User ID to unfollow"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Unfollow a user."""
    try:
        if user_id == current_user.id:
            raise BadRequestException(detail="You cannot unfollow yourself")

        following_service = FollowingService(db)
        result = await following_service.unfollow_user(
            follower_id=current_user.id, following_id=user_id
        )

        # Log audit event
        client_ip = request.client.host if request else "unknown"
        audit_logger.log_event(
            actor_id=current_user.id,
            action="unfollow_user",
            resource_type="user",
            resource_id=user_id,
            ip_address=client_ip,
        )

        return result
    except BadRequestException:
        raise
    except Exception as e:
        logger.error(f"Error unfollowing user: {str(e)}")
        raise ServerException(detail="Failed to unfollow user")


@router.get(
    "/following",
    response_model=FollowingListResponse,
    summary="Get following",
    description="Get list of users the current user is following",
)
@track_request_time
@cache(ttl=60, namespace="following")
async def get_following(
    request: Request,
    skip: int = Query(0, ge=0, description="Skip N items for pagination"),
    limit: int = Query(
        20, ge=1, le=100, description="Limit the number of results returned"
    ),
    sort_by: str = Query("recent", description="Sort by: recent, alphabetical, mutual"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> FollowingListResponse:
    """Get list of users the current user is following."""
    try:
        following_service = FollowingService(db)
        result = await following_service.get_following(
            user_id=current_user.id, skip=skip, limit=limit, sort_by=sort_by
        )

        return FollowingListResponse(
            items=result.items, total=result.total, has_more=result.has_more
        )
    except Exception as e:
        logger.error(f"Error retrieving following: {str(e)}")
        raise ServerException(detail="Failed to retrieve following list")


@router.get(
    "/followers",
    response_model=FollowerListResponse,
    summary="Get followers",
    description="Get list of users following the current user",
)
@track_request_time
@cache(ttl=60, namespace="followers")
async def get_followers(
    request: Request,
    skip: int = Query(0, ge=0, description="Skip N items for pagination"),
    limit: int = Query(
        20, ge=1, le=100, description="Limit the number of results returned"
    ),
    sort_by: str = Query("recent", description="Sort by: recent, alphabetical, mutual"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> FollowerListResponse:
    """Get list of users following the current user."""
    try:
        following_service = FollowingService(db)
        result = await following_service.get_followers(
            user_id=current_user.id, skip=skip, limit=limit, sort_by=sort_by
        )

        return FollowerListResponse(
            items=result.items, total=result.total, has_more=result.has_more
        )
    except Exception as e:
        logger.error(f"Error retrieving followers: {str(e)}")
        raise ServerException(detail="Failed to retrieve followers list")


@router.get(
    "/user/{user_id}/following",
    response_model=FollowingListResponse,
    summary="Get user following",
    description="Get list of users a specific user is following",
)
@track_request_time
@cache(ttl=120, namespace="suggestions")
async def get_user_following(
    request: Request,
    user_id: int = Path(..., description="User ID"),
    skip: int = Query(0, ge=0, description="Skip N items for pagination"),
    limit: int = Query(
        20, ge=1, le=100, description="Limit the number of results returned"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
) -> FollowingListResponse:
    """Get list of users a specific user is following."""
    try:
        following_service = FollowingService(db)
        result = await following_service.get_following(
            user_id=user_id,
            current_user_id=current_user.id if current_user else None,
            skip=skip,
            limit=limit,
        )

        return FollowingListResponse(
            items=result.items, total=result.total, has_more=result.has_more
        )
    except Exception as e:
        logger.error(f"Error retrieving user following: {str(e)}")
        raise ServerException(detail="Failed to retrieve user's following list")


@router.get(
    "/user/{user_id}/followers",
    response_model=FollowerListResponse,
    summary="Get user followers",
    description="Get list of users following a specific user",
)
@track_request_time
@cache(ttl=120, namespace="suggestions")
async def get_user_followers(
    request: Request,
    user_id: int = Path(..., description="User ID"),
    skip: int = Query(0, ge=0, description="Skip N items for pagination"),
    limit: int = Query(
        20, ge=1, le=100, description="Limit the number of results returned"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
) -> FollowerListResponse:
    """Get list of users following a specific user."""
    try:
        following_service = FollowingService(db)
        result = await following_service.get_followers(
            user_id=user_id,
            current_user_id=current_user.id if current_user else None,
            skip=skip,
            limit=limit,
        )

        return FollowerListResponse(
            items=result.items, total=result.total, has_more=result.has_more
        )
    except Exception as e:
        logger.error(f"Error retrieving user followers: {str(e)}")
        raise ServerException(detail="Failed to retrieve user's followers list")


@router.get(
    "/suggestions",
    response_model=List[SuggestedUserResponse],
    summary="Get user suggestions",
    description="Get suggested users to follow based on interests, reading behavior, and social graph",
)
@track_request_time
@cache(ttl=300, namespace="suggestions")
async def get_suggested_users(
    request: Request,
    limit: int = Query(
        10, ge=1, le=50, description="Limit the number of results returned"
    ),
    include_reason: bool = Query(True, description="Include reason for suggestion"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[SuggestedUserResponse]:
    """Get suggested users to follow based on various factors."""
    try:
        following_service = FollowingService(db)
        suggestions = await following_service.get_follow_suggestions(
            user_id=current_user.id, limit=limit, include_reason=include_reason
        )

        return suggestions
    except Exception as e:
        logger.error(f"Error retrieving user suggestions: {str(e)}")
        raise ServerException(detail="Failed to retrieve user suggestions")


@router.get(
    "/mutual/{user_id}",
    response_model=List[FollowingResponse],
    summary="Get mutual followers",
    description="Get list of mutual followers between current user and specified user",
)
@track_request_time
@cache(ttl=180, namespace="mutual_followers")
async def get_mutual_followers(
    request: Request,
    user_id: int = Path(..., description="User ID"),
    limit: int = Query(
        20, ge=1, le=100, description="Limit the number of results returned"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[FollowingResponse]:
    """Get list of mutual followers between current user and specified user."""
    try:
        if user_id == current_user.id:
            raise BadRequestException(
                detail="User ID must be different from current user"
            )

        following_service = FollowingService(db)
        mutual_followers = await following_service.get_mutual_followers(
            user_id_1=current_user.id, user_id_2=user_id, limit=limit
        )

        return mutual_followers
    except BadRequestException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving mutual followers: {str(e)}")
        raise ServerException(detail="Failed to retrieve mutual followers")


@router.get(
    "/stats",
    response_model=FollowStatsResponse,
    summary="Get follow statistics",
    description="Get statistics about followers and following",
)
@track_request_time
@cache(ttl=300, namespace="following_stats")
async def get_follow_stats(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> FollowStatsResponse:
    """Get statistics about followers and following."""
    try:
        following_service = FollowingService(db)
        stats = await following_service.get_follow_stats(user_id=current_user.id)

        return stats
    except Exception as e:
        logger.error(f"Error retrieving follow statistics: {str(e)}")
        raise ServerException(detail="Failed to retrieve follow statistics")


@router.get(
    "/network",
    response_model=UserNetworkResponse,
    summary="Get user network",
    description="Get extended network information for the current user",
)
@track_request_time
@cache(ttl=600, namespace="user_network")
async def get_user_network(
    request: Request,
    depth: int = Query(2, ge=1, le=3, description="Network depth (1-3)"),
    limit: int = Query(
        100, ge=1, le=500, description="Maximum number of users to return"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> UserNetworkResponse:
    """Get extended network information for the current user."""
    try:
        following_service = FollowingService(db)
        network = await following_service.get_user_network(
            user_id=current_user.id, depth=depth, limit=limit
        )

        return network
    except Exception as e:
        logger.error(f"Error retrieving user network: {str(e)}")
        raise ServerException(detail="Failed to retrieve user network")


@router.post(
    "/bulk-follow",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Bulk follow users",
    description="Follow multiple users at once",
)
@track_request_time
@throttle_requests(max_requests=2, window_seconds=300)
async def bulk_follow_users(
    request: Request,
    user_ids: List[int] = Body(..., description="List of user IDs to follow"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Follow multiple users at once."""
    try:
        if len(user_ids) > 20:
            raise BadRequestException(detail="Cannot follow more than 20 users at once")

        if current_user.id in user_ids:
            raise BadRequestException(detail="Cannot follow yourself")

        following_service = FollowingService(db)
        notification_service = NotificationService(db)
        result = await following_service.bulk_follow(
            follower_id=current_user.id, followed_ids=user_ids
        )

        # Send notifications to followed users
        if result["followed_count"] > 0:
            for followed_id in result["followed_users"]:
                await notification_service.create_follow_notification(
                    follower_id=current_user.id, followed_id=followed_id
                )

        return result
    except BadRequestException:
        raise
    except Exception as e:
        logger.error(f"Error during bulk follow: {str(e)}")
        raise ServerException(detail="Failed to bulk follow users")


@router.get(
    "/check/{user_id}",
    response_model=Dict[str, bool],
    summary="Check follow status",
    description="Check if the current user is following a specific user",
)
@track_request_time
async def check_follow_status(
    request: Request,
    user_id: int = Path(..., description="User ID to check"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, bool]:
    """Check if the current user is following a specific user."""
    try:
        following_service = FollowingService(db)
        is_following = await following_service.is_following(
            follower_id=current_user.id, following_id=user_id
        )

        is_follower = await following_service.is_following(
            follower_id=user_id, following_id=current_user.id
        )

        return {
            "is_following": is_following,
            "is_follower": is_follower,
            "is_mutual": is_following and is_follower,
        }
    except Exception as e:
        logger.error(f"Error checking follow status: {str(e)}")
        raise ServerException(detail="Failed to check follow status")


@router.get("/followers/{user_id}", response_model=FollowerListResponse)
@track_request_time(endpoint="get_followers")
@cache(ttl=600, namespace="followers")
async def get_followers_with_pagination(
    user_id: int = Path(..., gt=0, description="User ID to get followers for"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query("recent", description="Sort by: recent, name"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """
    Get the list of followers for a specific user with pagination and sorting options.
    Supports sorting by recent follow date or alphabetically by name.
    """
    following_service = FollowingService(db)

    try:
        # Check if user exists
        user = await following_service.get_user(user_id)
        if not user:
            raise NotFoundException(f"User with ID {user_id} not found")

        # Calculate pagination
        skip = (page - 1) * page_size

        # Get followers with pagination
        followers, total = await following_service.get_followers(
            user_id=user_id,
            skip=skip,
            limit=page_size,
            sort_by=sort_by,
            current_user_id=current_user.id if current_user else None,
        )

        # Calculate total pages
        total_pages = (total + page_size - 1) // page_size

        return {
            "items": followers,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting followers for user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get followers",
        )


@router.get("/following/{user_id}", response_model=FollowingListResponse)
@track_request_time(endpoint="get_following")
@cache(ttl=600, namespace="following")
async def get_following_with_pagination(
    user_id: int = Path(..., gt=0, description="User ID to get following for"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query("recent", description="Sort by: recent, name"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """
    Get the list of users that a specific user is following with pagination and sorting options.
    Supports sorting by recent follow date or alphabetically by name.
    """
    following_service = FollowingService(db)

    try:
        # Check if user exists
        user = await following_service.get_user(user_id)
        if not user:
            raise NotFoundException(f"User with ID {user_id} not found")

        # Calculate pagination
        skip = (page - 1) * page_size

        # Get following with pagination
        following, total = await following_service.get_following(
            user_id=user_id,
            skip=skip,
            limit=page_size,
            sort_by=sort_by,
            current_user_id=current_user.id if current_user else None,
        )

        # Calculate total pages
        total_pages = (total + page_size - 1) // page_size

        return {
            "items": following,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting following for user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get following",
        )


@router.get("/check/{user_id}", response_model=Dict[str, bool])
@track_request_time(endpoint="check_follow_status")
@cache(ttl=300, namespace="following_activities")
async def check_follow_status(
    user_id: int = Path(..., gt=0, description="User ID to check follow status with"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Check if the current user is following a specific user and if that user is following back.
    """
    following_service = FollowingService(db)

    try:
        # Check if target user exists
        target_user = await following_service.get_user(user_id)
        if not target_user:
            raise NotFoundException(f"User with ID {user_id} not found")

        # Check follow relationships
        is_following = await following_service.is_following(
            follower_id=current_user.id, followed_id=user_id
        )

        is_followed_by = await following_service.is_following(
            follower_id=user_id, followed_id=current_user.id
        )

        return {"is_following": is_following, "is_followed_by": is_followed_by}
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Error checking follow status with user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check follow status",
        )


@router.get("/suggestions", response_model=FollowSuggestionResponse)
@track_request_time(endpoint="get_follow_suggestions")
@cache(ttl=1800, namespace="following_books")
async def get_follow_suggestions(
    limit: int = Query(10, ge=1, le=50, description="Number of suggestions to return"),
    exclude_following: bool = Query(
        True, description="Exclude users already being followed"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get personalized user suggestions for the current user to follow, based on
    reading interests, mutual connections, and activity patterns.
    """
    following_service = FollowingService(db)

    try:
        suggestions = await following_service.get_follow_suggestions(
            user_id=current_user.id, limit=limit, exclude_following=exclude_following
        )

        return {"items": suggestions, "generated_at": datetime.now(timezone.utc)}
    except Exception as e:
        logger.error(f"Error getting follow suggestions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get follow suggestions",
        )


@router.get("/stats/{user_id}", response_model=FollowStatsResponse)
@track_request_time(endpoint="get_follow_stats")
@cache(ttl=1800, namespace="following_reviews")
async def get_follow_stats(
    user_id: int = Path(..., gt=0, description="User ID to get stats for"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """
    Get detailed follow statistics for a user, including counts, growth trends,
    and engagement metrics.
    """
    following_service = FollowingService(db)

    try:
        # Check if user exists
        user = await following_service.get_user(user_id)
        if not user:
            raise NotFoundException(f"User with ID {user_id} not found")

        # Get follow statistics
        stats = await following_service.get_follow_stats(user_id)

        return stats
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting follow stats for user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get follow statistics",
        )


@router.get("/mutuals/{user_id}", response_model=FollowingListResponse)
@track_request_time(endpoint="get_mutual_followers")
@cache(ttl=900, namespace="explore_network")
async def get_mutual_followers(
    user_id: int = Path(..., gt=0, description="User ID to get mutual followers with"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get the list of mutual followers between the current user and another user.
    These are users who both follow and are followed by both parties.
    """
    following_service = FollowingService(db)

    try:
        # Check if target user exists
        target_user = await following_service.get_user(user_id)
        if not target_user:
            raise NotFoundException(f"User with ID {user_id} not found")

        # Calculate pagination
        skip = (page - 1) * page_size

        # Get mutual followers
        mutuals, total = await following_service.get_mutual_followers(
            user_id_1=current_user.id, user_id_2=user_id, skip=skip, limit=page_size
        )

        # Calculate total pages
        total_pages = (total + page_size - 1) // page_size

        return {
            "items": mutuals,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting mutual followers with user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get mutual followers",
        )


@router.get("/activity", response_model=FollowActivityResponse)
@track_request_time(endpoint="get_follow_activity")
@cache(ttl=600, namespace="following_activities")
async def get_follow_activity(
    days: int = Query(
        7, ge=1, le=90, description="Number of days of activity to retrieve"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get recent follow activity for the current user, including new followers,
    recent unfollows, and activity from followed users.
    """
    following_service = FollowingService(db)

    try:
        activity = await following_service.get_follow_activity(
            user_id=current_user.id, days=days
        )

        return {
            "items": activity,
            "days": days,
            "generated_at": datetime.now(timezone.utc),
        }
    except Exception as e:
        logger.error(f"Error getting follow activity: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get follow activity",
        )


@router.get("/notification-settings", response_model=FollowNotificationSettings)
@track_request_time
async def get_follow_notification_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get the user's follow notification settings.
    """
    try:
        following_service = FollowingService(db)
        return await following_service.get_notification_settings(
            user_id=current_user.id
        )
    except Exception as e:
        logger.error(
            f"Error getting follow notification settings for user {current_user.id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get notification settings: {str(e)}",
        )


@router.put("/notification-settings", response_model=FollowNotificationSettings)
@track_request_time
async def update_follow_notification_settings(
    settings: FollowNotificationSettings = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Update the user's follow notification settings.
    """
    try:
        following_service = FollowingService(db)
        result = await following_service.update_notification_settings(
            user_id=current_user.id, settings=settings
        )

        logger.info(f"User {current_user.id} updated follow notification settings")
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(
            f"Error updating follow notification settings for user {current_user.id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update notification settings: {str(e)}",
        )
