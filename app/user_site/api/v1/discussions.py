from typing import List, Optional, Dict, Any, Union
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
    Path,
    Request,
    Body,
    BackgroundTasks,
    File,
    UploadFile,
)
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import conint
from datetime import datetime, timezone, timedelta

from app.common.db.session import get_db
from app.user_site.api.deps import (
    get_current_active_user,
    get_current_user,
    
    is_moderator,
    is_admin)
from app.user_site.api.v1 import throttle_requests
from app.user_site.models.user import User
from app.user_site.services.discussion_service import DiscussionService
from app.user_site.schemas.discussion import (
    DiscussionCreate,
    DiscussionUpdate,
    DiscussionResponse,
    DiscussionListResponse,
    DiscussionCommentCreate,
    DiscussionCommentUpdate,
    DiscussionCommentResponse,
    DiscussionCommentListResponse,
    DiscussionSearchParams,
    DiscussionReportCreate,
    DiscussionVoteResponse,
    DiscussionReplyCreate,
    DiscussionReplyResponse,
    DiscussionReplyUpdate,
    DiscussionStatsResponse,
    TrendingDiscussionResponse,
    DiscussionDetailResponse,
    DiscussionModerationAction,
    ReportDiscussionRequest,
    DiscussionQualityResponse,
    DiscussionReactionResponse,
    DiscussionReactionCreate,
    DiscussionSyncRequest,
    DiscussionAnalyticsResponse,
    DiscussionBulkDeleteRequest,
    DiscussionBulkUpdateRequest,
    DiscussionBulkActionResponse,
    DiscussionTimeSeriesResponse,
    DiscussionActivitySummary,
    DiscussionHighlightResponse,
    DiscussionPollCreate,
    DiscussionPollResponse,
    DiscussionPollVoteRequest,
    CommentCreate,
    CommentResponse,
    CommentListResponse,
    CommentUpdate,
    VoteRequest,
)
from app.logging.setup import get_logger
from app.monitoring.metrics import track_request_time
from app.cache.decorators import cache_response, invalidate_cache
from app.security.audit.audit_trails import AuditLogger
from app.core.exceptions import (
    ForbiddenException,
    NotFoundException,
    BadRequestException,
    ServerException,
    ConflictException,
    RateLimitException,
    ValidationException,
)
from app.user_site.services.notification_service import NotificationService
from app.security.audit.log_admin_action import log_admin_action as log_action
from app.common.utils.pagination import PaginationParams
from app.media.services.image_service import ImageService

router = APIRouter()
logger = get_logger("discussion_api")
audit_logger = AuditLogger()


@router.post(
    "/", response_model=DiscussionResponse, status_code=status.HTTP_201_CREATED
)
@track_request_time(endpoint="create_discussion")
@throttle_requests(max_requests=10, window_seconds=60)
@invalidate_cache(namespace="discussions", tags=["discussions"])
async def create_discussion(
    discussion: DiscussionCreate = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Tạo một thảo luận mới.
    """
    discussion_service = DiscussionService(db)
    notification_service = NotificationService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(f"Tạo thảo luận mới - User: {current_user.id}, IP: {client_ip}")

    try:
        new_discussion = await discussion_service.create_discussion(
            discussion=discussion, user_id=current_user.id
        )

        # Generate notifications for relevant users (e.g., book author, mentioned users)
        await notification_service.create_discussion_notifications(
            discussion_id=new_discussion.id,
            creator_id=current_user.id,
            book_id=discussion.book_id if hasattr(discussion, "book_id") else None,
        )

        # Ghi nhật ký audit
        audit_logger.log_event(
            actor_id=current_user.id,
            action="create_discussion",
            resource_type="discussion",
            resource_id=new_discussion.id,
            ip_address=client_ip,
        )

        return new_discussion
    except BadRequestException as e:
        logger.warning(f"Bad request when creating discussion: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating discussion: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create discussion: {str(e)}",
        )


@router.get("/{discussion_id}", response_model=DiscussionDetailResponse)
@track_request_time(endpoint="get_discussion")
@cache_response(ttl=300)
async def get_discussion(
    discussion_id: int = Path(..., gt=0), db: AsyncSession = Depends(get_db)
):
    """
    Lấy thông tin chi tiết của một thảo luận.
    """
    discussion_service = DiscussionService(db)

    try:
        discussion = await discussion_service.get_discussion(discussion_id)

        if not discussion:
            raise NotFoundException(
                detail=f"Không tìm thấy thảo luận với ID: {discussion_id}"
            )

        return discussion
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin thảo luận {discussion_id}: {str(e)}")
        raise


@router.get("/", response_model=DiscussionListResponse)
@track_request_time(endpoint="list_discussions")
@cache_response(ttl=300)
async def list_discussions(
    book_id: Optional[int] = Query(None, description="Filter by book ID"),
    chapter_id: Optional[int] = Query(None, description="Filter by chapter ID"),
    user_id: Optional[int] = Query(None, description="Filter by user ID"),
    is_pinned: Optional[bool] = Query(None, description="Filter by pinned status"),
    is_spoiler: Optional[bool] = Query(None, description="Filter by spoiler status"),
    tag: Optional[str] = Query(None, description="Filter by tag"),
    sort_by: str = Query(
        "created_at", description="Sort field: created_at, likes, comments"
    ),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search in title and content"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """
    List discussions with pagination, sorting and filtering options
    """
    try:
        discussion_service = DiscussionService(db)
        skip = (page - 1) * limit

        current_user_id = current_user.id if current_user else None

        discussions, total = await discussion_service.get_discussions(
            book_id=book_id,
            chapter_id=chapter_id,
            user_id=user_id,
            is_pinned=is_pinned,
            is_spoiler=is_spoiler,
            tag=tag,
            search=search,
            sort_by=sort_by,
            sort_order=sort_order,
            skip=skip,
            limit=limit,
            current_user_id=current_user_id,
        )

        return {
            "items": discussions,
            "total": total,
            "page": page,
            "limit": limit,
            "pages": (total + limit - 1) // limit,
        }
    except BadRequestException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error fetching discussions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch discussions",
        )


@router.put("/{discussion_id}", response_model=DiscussionResponse)
@track_request_time(endpoint="update_discussion")
@throttle_requests(max_requests=20, window_seconds=60)
@invalidate_cache(namespace="discussions", tags=["discussions"])
async def update_discussion(
    discussion_id: int = Path(..., gt=0, description="Discussion ID"),
    discussion_update: DiscussionUpdate = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Cập nhật thông tin thảo luận.
    """
    discussion_service = DiscussionService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Cập nhật thảo luận - ID: {discussion_id}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra thảo luận có tồn tại không
        discussion = await discussion_service.get_discussion(discussion_id)

        if not discussion:
            raise NotFoundException(
                detail=f"Không tìm thấy thảo luận với ID: {discussion_id}"
            )

        # Kiểm tra quyền sở hữu
        if discussion.user_id != current_user.id:
            raise ForbiddenException(detail="Bạn không có quyền cập nhật thảo luận này")

        updated_discussion = await discussion_service.update_discussion(
            discussion_id=discussion_id, discussion_update=discussion_update
        )

        # Ghi nhật ký audit
        audit_logger.log_event(
            actor_id=current_user.id,
            action="update_discussion",
            resource_type="discussion",
            resource_id=discussion_id,
            ip_address=client_ip,
        )

        return updated_discussion
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật thảo luận {discussion_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi cập nhật thảo luận",
        )


@router.delete("/{discussion_id}", status_code=status.HTTP_204_NO_CONTENT)
@track_request_time(endpoint="delete_discussion")
@throttle_requests(max_requests=10, window_seconds=60)
@invalidate_cache(namespace="discussions", tags=["discussions"])
async def delete_discussion(
    discussion_id: int = Path(..., gt=0, description="Discussion ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Xóa thảo luận.
    """
    discussion_service = DiscussionService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Xóa thảo luận - ID: {discussion_id}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra thảo luận có tồn tại không
        discussion = await discussion_service.get_discussion(discussion_id)

        if not discussion:
            raise NotFoundException(
                detail=f"Không tìm thấy thảo luận với ID: {discussion_id}"
            )

        # Kiểm tra quyền sở hữu
        if discussion.user_id != current_user.id:
            raise ForbiddenException(detail="Bạn không có quyền xóa thảo luận này")

        await discussion_service.delete_discussion(discussion_id=discussion_id)

        # Ghi nhật ký audit
        audit_logger.log_event(
            actor_id=current_user.id,
            action="delete_discussion",
            resource_type="discussion",
            resource_id=discussion_id,
            ip_address=client_ip,
        )

        return None
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi xóa thảo luận {discussion_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi xóa thảo luận",
        )


@router.post("/{discussion_id}/upvote", response_model=DiscussionVoteResponse)
@track_request_time(endpoint="upvote_discussion")
@throttle_requests(max_requests=30, window_seconds=60)
@invalidate_cache(namespace="discussions", tags=["discussions"])
async def upvote_discussion(
    discussion_id: int = Path(..., gt=0, description="Discussion ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Upvote cho thảo luận.
    """
    discussion_service = DiscussionService(db)
    notification_service = NotificationService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Upvote thảo luận - ID: {discussion_id}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra thảo luận có tồn tại không
        discussion = await discussion_service.get_discussion(discussion_id)

        if not discussion:
            raise NotFoundException(
                detail=f"Không tìm thấy thảo luận với ID: {discussion_id}"
            )

        result = await discussion_service.toggle_discussion_vote(
            discussion_id=discussion_id, user_id=current_user.id, vote_type="upvote"
        )

        if result["action"] == "added":
            # Get discussion author
            discussion = await discussion_service.get_discussion(
                discussion_id=discussion_id, current_user_id=current_user.id
            )

            # Create notification for the discussion author
            if discussion.user_id != current_user.id:
                await notification_service.create_discussion_vote_notification(
                    voter_id=current_user.id,
                    discussion_id=discussion_id,
                    author_id=discussion.user_id,
                    vote_type="upvote",
                )

        audit_logger.log_event(
            actor_id=current_user.id,
            action=f"{result['action']}_discussion_upvote",
            resource_type="discussion",
            resource_id=discussion_id,
            ip_address=client_ip,
        )

        return result
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi upvote thảo luận {discussion_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upvote discussion",
        )


@router.post("/{discussion_id}/downvote", response_model=DiscussionVoteResponse)
@track_request_time(endpoint="downvote_discussion")
@throttle_requests(max_requests=30, window_seconds=60)
@invalidate_cache(namespace="discussions", tags=["discussions"])
async def downvote_discussion(
    discussion_id: int = Path(..., gt=0, description="Discussion ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Downvote cho thảo luận.
    """
    discussion_service = DiscussionService(db)
    notification_service = NotificationService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Downvote thảo luận - ID: {discussion_id}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra thảo luận có tồn tại không
        discussion = await discussion_service.get_discussion(discussion_id)

        if not discussion:
            raise NotFoundException(
                detail=f"Không tìm thấy thảo luận với ID: {discussion_id}"
            )

        result = await discussion_service.toggle_discussion_vote(
            discussion_id=discussion_id, user_id=current_user.id, vote_type="downvote"
        )

        if result["action"] == "added":
            # Get discussion author
            discussion = await discussion_service.get_discussion(
                discussion_id=discussion_id, current_user_id=current_user.id
            )

            # Create notification for the discussion author
            if discussion.user_id != current_user.id:
                await notification_service.create_discussion_vote_notification(
                    voter_id=current_user.id,
                    discussion_id=discussion_id,
                    author_id=discussion.user_id,
                    vote_type="downvote",
                )

        audit_logger.log_event(
            actor_id=current_user.id,
            action=f"{result['action']}_discussion_downvote",
            resource_type="discussion",
            resource_id=discussion_id,
            ip_address=client_ip,
        )

        return result
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi downvote thảo luận {discussion_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to downvote discussion",
        )


# API cho comments


@router.post(
    "/{discussion_id}/comments",
    response_model=DiscussionCommentResponse,
    status_code=status.HTTP_201_CREATED,
)
@track_request_time(endpoint="create_discussion_comment")
@throttle_requests(max_requests=15, window_seconds=60)
@invalidate_cache(namespace="discussions", tags=["discussions", "comments"])
async def create_discussion_comment(
    discussion_id: int = Path(..., gt=0, description="Discussion ID"),
    comment: DiscussionCommentCreate = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Tạo một bình luận mới cho thảo luận.
    """
    discussion_service = DiscussionService(db)
    notification_service = NotificationService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Tạo bình luận mới - Discussion ID: {discussion_id}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Đảm bảo discussion_id trong path giống với trong body
        if comment.discussion_id != discussion_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Discussion ID trong path và body phải giống nhau",
            )

        # Kiểm tra thảo luận có tồn tại không
        discussion = await discussion_service.get_discussion(discussion_id)

        if not discussion:
            raise NotFoundException(
                detail=f"Không tìm thấy thảo luận với ID: {discussion_id}"
            )

        new_comment = await discussion_service.create_discussion_comment(
            discussion_id=discussion_id, user_id=current_user.id, comment=comment
        )

        # Get discussion information for notification
        discussion = await discussion_service.get_discussion(
            discussion_id=discussion_id, current_user_id=current_user.id
        )

        # Notify discussion author if they're not the commenter
        if discussion.user_id != current_user.id:
            await notification_service.create_discussion_comment_notification(
                commenter_id=current_user.id,
                discussion_id=discussion_id,
                author_id=discussion.user_id,
                comment_id=new_comment.id,
                is_reply=False,
            )

        # If this is a reply, also notify the parent comment author
        if comment.parent_id and comment.parent_id > 0:
            parent_comment = await discussion_service.get_discussion_comment(
                comment_id=comment.parent_id, current_user_id=current_user.id
            )

            if (
                parent_comment.user_id != current_user.id
                and parent_comment.user_id != discussion.user_id
            ):
                await notification_service.create_discussion_comment_notification(
                    commenter_id=current_user.id,
                    discussion_id=discussion_id,
                    author_id=parent_comment.user_id,
                    comment_id=new_comment.id,
                    is_reply=True,
                )

        audit_logger.log_event(
            actor_id=current_user.id,
            action="create_discussion_comment",
            resource_type="discussion_comment",
            resource_id=new_comment.id,
            parent_resource_type="discussion",
            parent_resource_id=discussion_id,
            ip_address=client_ip,
        )

        return new_comment
    except NotFoundException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi tạo bình luận cho thảo luận {discussion_id}: {str(e)}")
        raise


@router.get("/{discussion_id}/comments", response_model=DiscussionCommentListResponse)
@track_request_time(endpoint="list_discussion_comments")
@cache_response(ttl=300)
async def list_discussion_comments(
    discussion_id: int = Path(..., gt=0, description="Discussion ID"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query("created_at", description="Sort field: created_at, likes"),
    sort_order: str = Query("asc", description="Sort order: asc or desc"),
    parent_id: Optional[int] = Query(
        None, description="Filter by parent comment ID (for replies)"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """
    Lấy danh sách bình luận cho thảo luận.
    """
    discussion_service = DiscussionService(db)

    try:
        # Kiểm tra thảo luận có tồn tại không
        discussion = await discussion_service.get_discussion(discussion_id)

        if not discussion:
            raise NotFoundException(
                detail=f"Không tìm thấy thảo luận với ID: {discussion_id}"
            )

        comments, total = await discussion_service.get_discussion_comments(
            discussion_id=discussion_id,
            parent_id=parent_id,
            sort_by=sort_by,
            sort_order=sort_order,
            skip=(page - 1) * limit,
            limit=limit,
            current_user_id=current_user.id if current_user else None,
        )

        return {
            "items": comments,
            "total": total,
            "page": page,
            "limit": limit,
            "pages": (total + limit - 1) // limit,
        }
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy danh sách bình luận cho thảo luận {discussion_id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch comments",
        )


@router.get("/comments/{comment_id}", response_model=DiscussionCommentResponse)
@track_request_time(endpoint="get_discussion_comment")
@cache_response(ttl=300)
async def get_discussion_comment(
    comment_id: int = Path(..., gt=0), db: AsyncSession = Depends(get_db)
):
    """
    Lấy thông tin chi tiết của một bình luận.
    """
    discussion_service = DiscussionService(db)

    try:
        comment = await discussion_service.get_discussion_comment(comment_id)

        if not comment:
            raise NotFoundException(
                detail=f"Không tìm thấy bình luận với ID: {comment_id}"
            )

        return comment
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin bình luận {comment_id}: {str(e)}")
        raise


@router.put("/comments/{comment_id}", response_model=DiscussionCommentResponse)
@track_request_time(endpoint="update_discussion_comment")
@throttle_requests(max_requests=20, window_seconds=60)
@invalidate_cache(namespace="discussions", tags=["discussions", "comments"])
async def update_discussion_comment(
    comment_id: int = Path(..., gt=0, description="Comment ID"),
    comment_update: DiscussionCommentUpdate = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Cập nhật thông tin bình luận.
    """
    discussion_service = DiscussionService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Cập nhật bình luận - ID: {comment_id}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra bình luận có tồn tại không
        comment = await discussion_service.get_discussion_comment(comment_id)

        if not comment:
            raise NotFoundException(
                detail=f"Không tìm thấy bình luận với ID: {comment_id}"
            )

        # Kiểm tra quyền sở hữu
        if comment.user_id != current_user.id:
            raise ForbiddenException(detail="Bạn không có quyền cập nhật bình luận này")

        updated_comment = await discussion_service.update_discussion_comment(
            comment_id=comment_id, comment_update=comment_update
        )

        audit_logger.log_event(
            actor_id=current_user.id,
            action="update_discussion_comment",
            resource_type="discussion_comment",
            resource_id=comment_id,
            ip_address=client_ip,
        )

        return updated_comment
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật bình luận {comment_id}: {str(e)}")
        raise


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
@track_request_time(endpoint="delete_discussion_comment")
@throttle_requests(max_requests=10, window_seconds=60)
@invalidate_cache(namespace="discussions", tags=["discussions", "comments"])
async def delete_discussion_comment(
    comment_id: int = Path(..., gt=0, description="Comment ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Xóa bình luận.
    """
    discussion_service = DiscussionService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Xóa bình luận - ID: {comment_id}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra bình luận có tồn tại không
        comment = await discussion_service.get_discussion_comment(comment_id)

        if not comment:
            raise NotFoundException(
                detail=f"Không tìm thấy bình luận với ID: {comment_id}"
            )

        # Kiểm tra quyền sở hữu
        if comment.user_id != current_user.id:
            raise ForbiddenException(detail="Bạn không có quyền xóa bình luận này")

        await discussion_service.delete_discussion_comment(comment_id=comment_id)

        audit_logger.log_event(
            actor_id=current_user.id,
            action="delete_discussion_comment",
            resource_type="discussion_comment",
            resource_id=comment_id,
            ip_address=client_ip,
        )

        return None
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi xóa bình luận {comment_id}: {str(e)}")
        raise


@router.post("/comments/{comment_id}/upvote", response_model=DiscussionVoteResponse)
@track_request_time(endpoint="upvote_comment")
@throttle_requests(max_requests=30, window_seconds=60)
@invalidate_cache(namespace="discussions", tags=["discussions", "comments"])
async def upvote_comment(
    comment_id: int = Path(..., gt=0, description="Comment ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Upvote cho bình luận.
    """
    discussion_service = DiscussionService(db)
    notification_service = NotificationService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Upvote bình luận - ID: {comment_id}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra bình luận có tồn tại không
        comment = await discussion_service.get_discussion_comment(comment_id)

        if not comment:
            raise NotFoundException(
                detail=f"Không tìm thấy bình luận với ID: {comment_id}"
            )

        result = await discussion_service.toggle_comment_vote(
            comment_id=comment_id, user_id=current_user.id, vote_type="upvote"
        )

        if result["action"] == "added":
            # Get comment author
            comment = await discussion_service.get_discussion_comment(
                comment_id=comment_id, current_user_id=current_user.id
            )

            # Create notification for the comment author
            if comment.user_id != current_user.id:
                await notification_service.create_comment_vote_notification(
                    voter_id=current_user.id,
                    comment_id=comment_id,
                    author_id=comment.user_id,
                    vote_type="upvote",
                )

        audit_logger.log_event(
            actor_id=current_user.id,
            action=f"{result['action']}_comment_upvote",
            resource_type="discussion_comment",
            resource_id=comment_id,
            ip_address=client_ip,
        )

        return result
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi upvote bình luận {comment_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upvote comment",
        )


@router.post("/comments/{comment_id}/downvote", response_model=DiscussionVoteResponse)
@track_request_time(endpoint="downvote_comment")
@throttle_requests(max_requests=30, window_seconds=60)
@invalidate_cache(namespace="discussions", tags=["discussions", "comments"])
async def downvote_comment(
    comment_id: int = Path(..., gt=0, description="Comment ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Downvote cho bình luận.
    """
    discussion_service = DiscussionService(db)
    notification_service = NotificationService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Downvote bình luận - ID: {comment_id}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra bình luận có tồn tại không
        comment = await discussion_service.get_discussion_comment(comment_id)

        if not comment:
            raise NotFoundException(
                detail=f"Không tìm thấy bình luận với ID: {comment_id}"
            )

        result = await discussion_service.toggle_comment_vote(
            comment_id=comment_id, user_id=current_user.id, vote_type="downvote"
        )

        if result["action"] == "added":
            # Get comment author
            comment = await discussion_service.get_discussion_comment(
                comment_id=comment_id, current_user_id=current_user.id
            )

            # Create notification for the comment author
            if comment.user_id != current_user.id:
                await notification_service.create_comment_vote_notification(
                    voter_id=current_user.id,
                    comment_id=comment_id,
                    author_id=comment.user_id,
                    vote_type="downvote",
                )

        audit_logger.log_event(
            actor_id=current_user.id,
            action=f"{result['action']}_comment_downvote",
            resource_type="discussion_comment",
            resource_id=comment_id,
            ip_address=client_ip,
        )

        return result
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi downvote bình luận {comment_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to downvote comment",
        )


@router.post("/{discussion_id}/report", status_code=status.HTTP_204_NO_CONTENT)
@track_request_time(endpoint="report_discussion")
@throttle_requests(max_requests=5, window_seconds=300)
async def report_discussion(
    discussion_id: int = Path(..., gt=0, description="Discussion ID"),
    report: DiscussionReportCreate = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Report a discussion for inappropriate content
    """
    discussion_service = DiscussionService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"User {current_user.id} reporting discussion {discussion_id} - IP: {client_ip}"
    )

    try:
        await discussion_service.report_discussion(
            discussion_id=discussion_id,
            user_id=current_user.id,
            reason=report.reason,
            details=report.details,
        )

        audit_logger.log_event(
            actor_id=current_user.id,
            action="report_discussion",
            resource_type="discussion",
            resource_id=discussion_id,
            ip_address=client_ip,
            additional_data={"reason": report.reason},
        )

        return None
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ConflictException as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except RateLimitException as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error reporting discussion {discussion_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to report discussion",
        )


@router.post("/comments/{comment_id}/report", status_code=status.HTTP_204_NO_CONTENT)
@track_request_time(endpoint="report_comment")
@throttle_requests(max_requests=5, window_seconds=300)
async def report_comment(
    comment_id: int = Path(..., gt=0, description="Comment ID"),
    report: DiscussionReportCreate = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Report a comment for inappropriate content
    """
    discussion_service = DiscussionService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"User {current_user.id} reporting comment {comment_id} - IP: {client_ip}"
    )

    try:
        await discussion_service.report_comment(
            comment_id=comment_id,
            user_id=current_user.id,
            reason=report.reason,
            details=report.details,
        )

        audit_logger.log_event(
            actor_id=current_user.id,
            action="report_comment",
            resource_type="discussion_comment",
            resource_id=comment_id,
            ip_address=client_ip,
            additional_data={"reason": report.reason},
        )

        return None
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ConflictException as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except RateLimitException as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error reporting comment {comment_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to report comment",
        )


@router.get("/trending", response_model=List[TrendingDiscussionResponse])
@track_request_time(endpoint="get_trending_discussions")
@cache_response(ttl=1800)  # Cache for 30 minutes
async def get_trending_discussions(
    time_period: str = Query("day", description="Time period: day, week, month, year"),
    category_id: Optional[int] = Query(None, description="Filter by category ID"),
    limit: int = Query(
        10, ge=1, le=50, description="Number of trending discussions to return"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """
    Get trending discussions based on activity metrics (views, comments, reactions)
    for a specified time period and optional category.
    """
    try:
        discussion_service = DiscussionService(db)
        current_user_id = current_user.id if current_user else None

        valid_periods = {"day", "week", "month", "year"}
        if time_period not in valid_periods:
            raise ValidationException(
                f"Invalid time period. Must be one of: {', '.join(valid_periods)}"
            )

        trending = await discussion_service.get_trending_discussions(
            time_period=time_period,
            category_id=category_id,
            limit=limit,
            current_user_id=current_user_id,
        )

        return trending
    except ValidationException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error fetching trending discussions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch trending discussions",
        )


@router.post("/{discussion_id}/polls", response_model=DiscussionPollResponse)
@track_request_time(endpoint="create_discussion_poll")
@throttle_requests(max_requests=5, window_seconds=60)
async def create_discussion_poll(
    discussion_id: int = Path(..., gt=0, description="Discussion ID"),
    poll_data: DiscussionPollCreate = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Create a poll for an existing discussion. The creator of the discussion or moderators
    can add polls to gather opinions from participants.
    """
    discussion_service = DiscussionService(db)
    client_ip = request.client.host if request and request.client else "unknown"

    try:
        # Check if discussion exists
        discussion = await discussion_service.get_discussion(discussion_id)
        if not discussion:
            raise NotFoundException(f"Discussion with ID {discussion_id} not found")

        # Check if user is allowed to create poll (owner or moderator)
        is_owner = discussion.user_id == current_user.id
        is_mod = await is_moderator(current_user, db)

        if not (is_owner or is_mod):
            raise ForbiddenException(
                "Only the discussion creator or moderators can add polls"
            )

        # Validate poll options (at least 2 options required)
        if len(poll_data.options) < 2:
            raise ValidationException("At least 2 options are required for a poll")

        # Create the poll
        poll = await discussion_service.create_discussion_poll(
            discussion_id=discussion_id, poll_data=poll_data, user_id=current_user.id
        )

        # Log the action
        audit_logger.log_event(
            actor_id=current_user.id,
            action="create_discussion_poll",
            resource_type="discussion_poll",
            resource_id=poll.id,
            related_resource_type="discussion",
            related_resource_id=discussion_id,
            ip_address=client_ip,
        )

        return poll
    except (NotFoundException, ForbiddenException, ValidationException) as e:
        logger.warning(f"{type(e).__name__} when creating discussion poll: {str(e)}")
        raise HTTPException(
            status_code=(
                e.status_code
                if hasattr(e, "status_code")
                else status.HTTP_400_BAD_REQUEST
            ),
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error creating discussion poll: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create discussion poll: {str(e)}",
        )


@router.post("/{discussion_id}/polls/{poll_id}/vote")
@track_request_time(endpoint="vote_discussion_poll")
@throttle_requests(max_requests=20, window_seconds=60)
@invalidate_cache(namespace="discussions", tags=["polls"])
async def vote_discussion_poll(
    discussion_id: int = Path(..., gt=0, description="Discussion ID"),
    poll_id: int = Path(..., gt=0, description="Poll ID"),
    vote_data: DiscussionPollVoteRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Vote on a discussion poll option. Users can vote once per poll,
    with the ability to change their vote.
    """
    discussion_service = DiscussionService(db)
    client_ip = request.client.host if request and request.client else "unknown"

    try:
        # Submit the vote
        result = await discussion_service.vote_on_poll(
            poll_id=poll_id, option_id=vote_data.option_id, user_id=current_user.id
        )

        # Log the action
        audit_logger.log_event(
            actor_id=current_user.id,
            action="vote_discussion_poll",
            resource_type="discussion_poll",
            resource_id=poll_id,
            related_resource_type="discussion",
            related_resource_id=discussion_id,
            ip_address=client_ip,
        )

        return {"success": True, "message": "Vote recorded successfully"}
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ConflictException as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        logger.error(f"Error voting on discussion poll: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record vote: {str(e)}",
        )


@router.get("/stats/timeseries", response_model=DiscussionTimeSeriesResponse)
@track_request_time(endpoint="get_discussion_timeseries")
@cache_response(ttl=3600)  # Cache for 1 hour
async def get_discussion_timeseries(
    period: str = Query("week", description="Time period: day, week, month, year"),
    book_id: Optional[int] = Query(None, description="Filter by book ID"),
    category_id: Optional[int] = Query(None, description="Filter by category ID"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """
    Get time series data for discussions to analyze trends over time.
    Data includes discussion creation, comments, and reactions over the specified period.
    """
    discussion_service = DiscussionService(db)

    try:
        # Validate period
        valid_periods = {"day", "week", "month", "year"}
        if period not in valid_periods:
            raise ValidationException(
                f"Invalid period. Must be one of: {', '.join(valid_periods)}"
            )

        # Get time series data
        timeseries_data = await discussion_service.get_discussion_timeseries(
            period=period, book_id=book_id, category_id=category_id
        )

        return timeseries_data
    except ValidationException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error fetching discussion time series data: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch discussion time series data",
        )


@router.post("/bulk/delete", response_model=DiscussionBulkActionResponse)
@track_request_time(endpoint="bulk_delete_discussions")
@throttle_requests(max_requests=3, window_seconds=120)
@invalidate_cache(namespace="discussions", tags=["discussions"])
async def bulk_delete_discussions(
    delete_request: DiscussionBulkDeleteRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Bulk delete multiple discussions. Only available to the owner of all discussions
    or to moderators/admins.
    """
    discussion_service = DiscussionService(db)
    client_ip = request.client.host if request and request.client else "unknown"

    try:
        # Validate the request
        if not delete_request.discussion_ids or len(delete_request.discussion_ids) == 0:
            raise ValidationException("No discussion IDs provided")

        if len(delete_request.discussion_ids) > 50:
            raise ValidationException("Maximum 50 discussions can be deleted at once")

        # Check permissions (either owner of all discussions or moderator/admin)
        is_mod = await is_moderator(current_user, db)
        is_admin_user = await is_admin(current_user, db)

        if not (is_mod or is_admin_user):
            # Check if user owns all discussions
            for discussion_id in delete_request.discussion_ids:
                discussion = await discussion_service.get_discussion(discussion_id)
                if not discussion or discussion.user_id != current_user.id:
                    raise ForbiddenException(
                        "You can only bulk delete your own discussions unless you're a moderator"
                    )

        # Process deletion
        result = await discussion_service.bulk_delete_discussions(
            discussion_ids=delete_request.discussion_ids,
            user_id=current_user.id,
            is_moderator=is_mod or is_admin_user,
            reason=delete_request.reason,
        )

        # Log the action
        for discussion_id in delete_request.discussion_ids:
            audit_logger.log_event(
                actor_id=current_user.id,
                action="bulk_delete_discussion",
                resource_type="discussion",
                resource_id=discussion_id,
                ip_address=client_ip,
                metadata={
                    "reason": (
                        delete_request.reason
                        if delete_request.reason
                        else "No reason provided"
                    )
                },
            )

        return {
            "success": True,
            "message": f"Successfully deleted {result.deleted_count} of {len(delete_request.discussion_ids)} discussions",
            "processed_count": len(delete_request.discussion_ids),
            "success_count": result.deleted_count,
            "failed_ids": result.failed_ids,
            "error_details": result.error_details,
        }
    except ValidationException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ForbiddenException as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        logger.error(f"Error in bulk delete discussions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process bulk delete: {str(e)}",
        )


@router.get("/highlights", response_model=DiscussionHighlightResponse)
@track_request_time(endpoint="get_discussion_highlights")
@cache_response(ttl=1800)  # Cache for 30 minutes
async def get_discussion_highlights(
    book_id: Optional[int] = Query(None, description="Filter by book ID"),
    days: int = Query(7, ge=1, le=90, description="Days to consider for highlights"),
    limit: int = Query(10, ge=1, le=50, description="Number of highlights to return"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """
    Get highlighted discussions based on engagement quality, content quality,
    recency, and user interactions.
    """
    discussion_service = DiscussionService(db)
    current_user_id = current_user.id if current_user else None

    try:
        highlights = await discussion_service.get_discussion_highlights(
            book_id=book_id, days=days, limit=limit, current_user_id=current_user_id
        )

        return {
            "items": highlights,
            "generated_at": datetime.now(timezone.utc),
            "period_days": days,
        }
    except Exception as e:
        logger.error(f"Error fetching discussion highlights: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch discussion highlights",
        )


@router.post("/{discussion_id}/image", response_model=DiscussionResponse)
@track_request_time(endpoint="add_discussion_image")
@throttle_requests(max_requests=5, window_seconds=60)
@invalidate_cache(namespace="discussions", tags=["discussions"])
async def add_discussion_image(
    discussion_id: int = Path(..., gt=0, description="Discussion ID"),
    image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Add an image to an existing discussion. Only the discussion creator can add images.
    """
    discussion_service = DiscussionService(db)
    image_service = ImageService()
    client_ip = request.client.host if request and request.client else "unknown"

    try:
        # Check if discussion exists and user has permission
        discussion = await discussion_service.get_discussion(discussion_id)

        if not discussion:
            raise NotFoundException(f"Discussion with ID {discussion_id} not found")

        if discussion.user_id != current_user.id:
            raise ForbiddenException("Only the discussion creator can add images")

        # Validate image file
        if not image.content_type.startswith("image/"):
            raise ValidationException("Uploaded file must be an image")

        # Process and store the image
        image_url = await image_service.upload_discussion_image(
            discussion_id=discussion_id, user_id=current_user.id, image_file=image
        )

        # Update the discussion with the image URL
        updated_discussion = await discussion_service.add_discussion_image(
            discussion_id=discussion_id, image_url=image_url
        )

        # Log the action
        audit_logger.log_event(
            actor_id=current_user.id,
            action="add_discussion_image",
            resource_type="discussion",
            resource_id=discussion_id,
            ip_address=client_ip,
        )

        return updated_discussion
    except ValidationException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ForbiddenException as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        logger.error(f"Error adding image to discussion: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add image to discussion: {str(e)}",
        )


@router.get("/user/activity/summary", response_model=DiscussionActivitySummary)
@track_request_time(endpoint="get_user_discussion_activity")
@cache_response(ttl=600, key_prefix="user_discussion_activity")
async def get_user_discussion_activity(
    user_id: Optional[int] = Query(
        None, description="User ID (defaults to current user if authenticated)"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """
    Get a summary of a user's discussion activity, including created discussions,
    comments, reactions, and engagement metrics.
    """
    discussion_service = DiscussionService(db)

    try:
        # Determine which user's activity to retrieve
        target_user_id = user_id

        # If no user_id provided and user is authenticated, use current user
        if not target_user_id and current_user:
            target_user_id = current_user.id

        # If still no target_user_id, raise an error
        if not target_user_id:
            raise BadRequestException(
                "User ID must be provided or request must be authenticated"
            )

        # Get the activity summary
        activity_summary = await discussion_service.get_user_discussion_activity(
            user_id=target_user_id
        )

        return activity_summary
    except BadRequestException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Error fetching user discussion activity: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch user discussion activity",
        )


@router.post("/search", response_model=DiscussionListResponse)
@track_request_time(endpoint="advanced_search_discussions")
@throttle_requests(max_requests=20, window_seconds=60)
async def advanced_search_discussions(
    search_params: DiscussionSearchParams,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """
    Tìm kiếm nâng cao các thảo luận với nhiều tiêu chí.

    Cho phép tìm kiếm theo nội dung, tiêu đề, thẻ, ngày tạo, mức độ tương tác
    và nhiều thuộc tính khác để tìm kiếm thảo luận một cách chính xác.

    Các tham số tìm kiếm bao gồm:
    - Từ khóa trong tiêu đề và nội dung
    - Thời gian tạo (từ ngày, đến ngày)
    - Thẻ đánh dấu
    - ID sách, ID chương
    - Loại thảo luận
    - Mức độ tương tác (lượt thích, bình luận)
    - Sắp xếp theo nhiều tiêu chí
    """
    try:
        discussion_service = DiscussionService(db)
        skip = (search_params.page - 1) * search_params.limit

        # Tạo dict các tham số search từ Pydantic model
        search_dict = search_params.model_dump()
        search_dict["skip"] = skip
        search_dict["current_user_id"] = current_user.id if current_user else None

        # Gọi service để tìm kiếm
        discussions, total = await discussion_service.search_discussions(**search_dict)

        return {
            "items": discussions,
            "total": total,
            "page": search_params.page,
            "limit": search_params.limit,
            "pages": (total + search_params.limit - 1) // search_params.limit,
        }
    except BadRequestException as e:
        logger.warning(f"Bad request in advanced search: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error in advanced search: {str(e)}")
        raise ServerException(detail="Lỗi khi tìm kiếm thảo luận")
