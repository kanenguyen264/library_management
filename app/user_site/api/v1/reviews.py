from typing import Dict, Any, List, Optional
from fastapi import (
    APIRouter,
    Depends,
    Path,
    Query,
    HTTPException,
    status,
    Request,
    Body,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.db.session import get_db
from app.user_site.api.deps import (
    get_current_active_user,
    get_current_user)
from app.user_site.api.v1 import throttle_requests
from app.user_site.models.user import User
from app.user_site.schemas.review import (
    ReviewCreate,
    ReviewUpdate,
    ReviewResponse,
    ReviewReportCreate,
    ReviewReportUpdate,
    ReviewReportResponse,
    ReviewListResponse,
    ReportReviewRequest,
    ReviewBriefResponse,
    ReviewStatsResponse,
    ReviewBulkActionRequest,
)
from app.user_site.services.review_service import ReviewService
from app.logging.setup import get_logger
from app.monitoring.metrics import track_request_time, increment_counter
from app.cache.decorators import cache_response, invalidate_cache
from app.security.audit.audit_trails import AuditLogger
from app.core.exceptions import (
    NotFoundException,
    ForbiddenException,
    BadRequestException,
    ServerException,
)

router = APIRouter()
logger = get_logger("review_api")
audit_logger = AuditLogger()


@router.post("/", response_model=ReviewResponse, status_code=status.HTTP_201_CREATED)
@track_request_time(endpoint="create_review")
@throttle_requests(max_requests=10, window_seconds=60)
@invalidate_cache(namespace="reviews", tags=["reviews"])
async def create_review(
    data: ReviewCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Tạo đánh giá mới cho sách.

    - Rate limiting: 10 request/phút để ngăn spam
    - Vô hiệu hóa cache sau khi tạo để đảm bảo tính nhất quán
    """
    review_service = ReviewService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Tạo đánh giá mới - User: {current_user.id}, Book: {data.book_id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra xem người dùng đã đánh giá sách này chưa
        existing_review = await review_service.get_user_review_for_book(
            current_user.id, data.book_id
        )
        if existing_review:
            raise BadRequestException(
                detail="Bạn đã đánh giá sách này trước đó. Vui lòng cập nhật đánh giá hiện có."
            )

        review = await review_service.create_review(current_user.id, data.model_dump())

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "review_create",
            f"Người dùng đã tạo đánh giá mới cho sách {data.book_id}",
            metadata={
                "user_id": current_user.id,
                "book_id": data.book_id,
                "rating": data.rating,
            },
        )

        # Tăng counter cho metrics
        increment_counter("reviews_created_total")

        return review
    except BadRequestException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi tạo đánh giá: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi tạo đánh giá",
        )


@router.get("/book/{book_id}", response_model=ReviewListResponse)
@track_request_time(endpoint="list_reviews_by_book")
@cache_response(ttl=300, vary_by=["book_id", "skip", "limit", "sort_by", "sort_desc"])
async def list_reviews_by_book(
    book_id: int = Path(..., gt=0),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    sort_by: str = Query("created_at", regex="^(created_at|rating|likes)$"),
    sort_desc: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """
    Lấy danh sách đánh giá của một cuốn sách.

    - Tối ưu hiệu suất: Cache kết quả trong 5 phút
    - Hỗ trợ phân trang và sắp xếp theo nhiều tiêu chí
    - Validation: Kiểm tra các tham số đầu vào
    """
    review_service = ReviewService(db)

    try:
        reviews, total = await review_service.list_reviews_by_book(
            book_id=book_id,
            user_id=current_user.id if current_user else None,
            skip=skip,
            limit=limit,
            sort_by=sort_by,
            sort_desc=sort_desc,
        )

        return {"items": reviews, "total": total}
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách đánh giá sách {book_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy danh sách đánh giá",
        )


@router.get("/user/{user_id}", response_model=ReviewListResponse)
@track_request_time(endpoint="list_reviews_by_user")
@cache_response(ttl=300, vary_by=["user_id", "skip", "limit"])
async def list_reviews_by_user(
    user_id: int = Path(..., gt=0),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """
    Lấy danh sách đánh giá của một người dùng.

    - Tối ưu hiệu suất: Cache kết quả trong 5 phút
    - Phân trang để tải nhanh hơn với dữ liệu lớn
    """
    review_service = ReviewService(db)

    try:
        reviews, total = await review_service.list_reviews_by_user(
            user_id=user_id,
            current_user_id=current_user.id if current_user else None,
            skip=skip,
            limit=limit,
        )

        return {"items": reviews, "total": total}
    except Exception as e:
        logger.error(f"Lỗi khi lấy đánh giá của người dùng {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy đánh giá của người dùng",
        )


@router.get("/my-reviews", response_model=ReviewListResponse)
@track_request_time(endpoint="list_my_reviews")
@cache_response(ttl=300, vary_by=["current_user.id", "skip", "limit"])
async def list_my_reviews(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy danh sách đánh giá của người dùng hiện tại.

    - Tối ưu hiệu suất: Cache kết quả trong 5 phút
    - Xác thực: Yêu cầu người dùng đăng nhập
    """
    review_service = ReviewService(db)

    try:
        reviews, total = await review_service.list_reviews_by_user(
            user_id=current_user.id,
            current_user_id=current_user.id,
            skip=skip,
            limit=limit,
        )

        return {"items": reviews, "total": total}
    except Exception as e:
        logger.error(f"Lỗi khi lấy đánh giá của người dùng hiện tại: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy đánh giá của người dùng hiện tại",
        )


@router.get("/{review_id}", response_model=ReviewResponse)
@track_request_time(endpoint="get_review")
@cache_response(ttl=300, vary_by=["review_id"])
async def get_review(
    review_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """
    Lấy thông tin chi tiết của một đánh giá.

    - Tối ưu hiệu suất: Cache kết quả trong 5 phút
    - API công khai: Không yêu cầu đăng nhập
    """
    review_service = ReviewService(db)

    try:
        review = await review_service.get_review_by_id(
            review_id=review_id,
            current_user_id=current_user.id if current_user else None,
        )

        if not review:
            raise NotFoundException(
                detail=f"Không tìm thấy đánh giá với ID: {review_id}"
            )

        return review
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy đánh giá {review_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy đánh giá",
        )


@router.put("/{review_id}", response_model=ReviewResponse)
@track_request_time(endpoint="update_review")
@throttle_requests(max_requests=20, window_seconds=60)
@invalidate_cache(namespace="reviews", tags=["reviews"])
async def update_review(
    data: ReviewUpdate,
    review_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
    current_user: User = Depends(get_current_active_user),
):
    """
    Cập nhật thông tin đánh giá.

    - Rate limiting: 20 request/phút để tránh lạm dụng
    - Vô hiệu hóa cache: Đảm bảo dữ liệu mới nhất luôn được hiển thị
    - Xác thực: Chỉ người dùng đã tạo đánh giá mới được cập nhật
    """
    review_service = ReviewService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Cập nhật đánh giá - User: {current_user.id}, Review: {review_id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra xem đánh giá có tồn tại và thuộc về người dùng hiện tại không
        existing_review = await review_service.get_review_by_id(review_id)
        if not existing_review:
            raise NotFoundException(
                detail=f"Không tìm thấy đánh giá với ID: {review_id}"
            )

        if existing_review.user_id != current_user.id:
            raise ForbiddenException(detail="Bạn không có quyền cập nhật đánh giá này")

        review = await review_service.update_review(
            review_id=review_id,
            user_id=current_user.id,
            data=data.model_dump(exclude_unset=True),
        )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "review_update",
            f"Người dùng đã cập nhật đánh giá {review_id}",
            metadata={"user_id": current_user.id, "review_id": review_id},
        )

        return review
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật đánh giá {review_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi cập nhật đánh giá",
        )


@router.delete("/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
@track_request_time(endpoint="delete_review")
@throttle_requests(max_requests=10, window_seconds=60)
@invalidate_cache(namespace="reviews", tags=["reviews"])
async def delete_review(
    review_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
    current_user: User = Depends(get_current_active_user),
):
    """
    Xóa đánh giá.

    - Rate limiting: 10 request/phút để ngăn lạm dụng
    - Vô hiệu hóa cache: Đảm bảo dữ liệu mới nhất luôn được hiển thị
    - Xác thực: Chỉ người dùng đã tạo đánh giá mới được xóa
    """
    review_service = ReviewService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Xóa đánh giá - User: {current_user.id}, Review: {review_id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra xem đánh giá có tồn tại và thuộc về người dùng hiện tại không
        existing_review = await review_service.get_review_by_id(review_id)
        if not existing_review:
            raise NotFoundException(
                detail=f"Không tìm thấy đánh giá với ID: {review_id}"
            )

        if existing_review.user_id != current_user.id:
            raise ForbiddenException(detail="Bạn không có quyền xóa đánh giá này")

        await review_service.delete_review(current_user.id, review_id)

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "review_delete",
            f"Người dùng đã xóa đánh giá {review_id}",
            metadata={"user_id": current_user.id, "review_id": review_id},
        )

        return None
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi xóa đánh giá {review_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi xóa đánh giá",
        )


@router.post("/{review_id}/like", response_model=ReviewResponse)
@track_request_time(endpoint="like_review")
@throttle_requests(max_requests=30, window_seconds=60)
@invalidate_cache(namespace="reviews", tags=["reviews"])
async def like_review(
    review_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
    current_user: User = Depends(get_current_active_user),
):
    """
    Thích một đánh giá.

    - Rate limiting: 30 request/phút để tránh lạm dụng
    - Vô hiệu hóa cache: Đảm bảo dữ liệu mới nhất luôn được hiển thị
    """
    review_service = ReviewService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Like đánh giá - User: {current_user.id}, Review: {review_id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra đánh giá có tồn tại không
        existing_review = await review_service.get_review_by_id(review_id)
        if not existing_review:
            raise NotFoundException(
                detail=f"Không tìm thấy đánh giá với ID: {review_id}"
            )

        review = await review_service.like_review(current_user.id, review_id)

        # Ghi nhật ký audit nếu thao tác thành công
        audit_logger.log_activity(
            current_user.id,
            "review_like",
            f"Người dùng đã thích đánh giá {review_id}",
            metadata={"user_id": current_user.id, "review_id": review_id},
        )

        return review
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi thích đánh giá {review_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi thích đánh giá",
        )


@router.delete("/{review_id}/like", response_model=ReviewResponse)
@track_request_time(endpoint="unlike_review")
@throttle_requests(max_requests=30, window_seconds=60)
@invalidate_cache(namespace="reviews", tags=["reviews"])
async def unlike_review(
    review_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
    current_user: User = Depends(get_current_active_user),
):
    """
    Bỏ thích một đánh giá.

    - Rate limiting: 30 request/phút để tránh lạm dụng
    - Vô hiệu hóa cache: Đảm bảo dữ liệu mới nhất luôn được hiển thị
    """
    review_service = ReviewService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Unlike đánh giá - User: {current_user.id}, Review: {review_id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra đánh giá có tồn tại không
        existing_review = await review_service.get_review_by_id(review_id)
        if not existing_review:
            raise NotFoundException(
                detail=f"Không tìm thấy đánh giá với ID: {review_id}"
            )

        review = await review_service.unlike_review(current_user.id, review_id)

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "review_unlike",
            f"Người dùng đã bỏ thích đánh giá {review_id}",
            metadata={"user_id": current_user.id, "review_id": review_id},
        )

        return review
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi bỏ thích đánh giá {review_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi bỏ thích đánh giá",
        )


@router.post("/{review_id}/report", status_code=status.HTTP_204_NO_CONTENT)
@track_request_time(endpoint="report_review")
@throttle_requests(max_requests=5, window_seconds=300)
async def report_review(
    data: ReportReviewRequest,
    review_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
    current_user: User = Depends(get_current_active_user),
):
    """
    Báo cáo đánh giá vi phạm.

    - Rate limiting: 5 request/5 phút để ngăn lạm dụng
    - Anti-spam: Giới hạn số lượng báo cáo
    """
    review_service = ReviewService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Báo cáo đánh giá - User: {current_user.id}, Review: {review_id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra đánh giá có tồn tại không
        existing_review = await review_service.get_review_by_id(review_id)
        if not existing_review:
            raise NotFoundException(
                detail=f"Không tìm thấy đánh giá với ID: {review_id}"
            )

        # Kiểm tra người dùng không báo cáo chính đánh giá của mình
        if existing_review.user_id == current_user.id:
            raise BadRequestException(
                detail="Bạn không thể báo cáo đánh giá của chính mình"
            )

        # Kiểm tra người dùng đã báo cáo đánh giá này trước đó chưa
        has_reported = await review_service.has_user_reported_review(
            current_user.id, review_id
        )
        if has_reported:
            raise BadRequestException(detail="Bạn đã báo cáo đánh giá này trước đó")

        await review_service.report_review(
            review_id=review_id,
            user_id=current_user.id,
            reason=data.reason,
            details=data.details,
        )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "review_report",
            f"Người dùng đã báo cáo đánh giá {review_id}",
            metadata={
                "user_id": current_user.id,
                "review_id": review_id,
                "reason": data.reason,
            },
        )

        return None
    except (NotFoundException, BadRequestException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi báo cáo đánh giá {review_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi báo cáo đánh giá",
        )


@router.get("/stats", response_model=ReviewStatsResponse)
@track_request_time(endpoint="get_review_stats")
@cache_response(ttl=3600)  # Cache 1 giờ
async def get_review_stats(
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """
    Lấy thống kê về đánh giá.

    - Tối ưu hiệu suất: Cache kết quả trong 1 giờ
    - API công khai: Không yêu cầu đăng nhập
    """
    review_service = ReviewService(db)

    try:
        stats = await review_service.get_review_stats(
            user_id=current_user.id if current_user else None
        )
        return stats
    except Exception as e:
        logger.error(f"Lỗi khi lấy thống kê đánh giá: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy thống kê đánh giá",
        )


@router.post("/bulk-action", status_code=status.HTTP_200_OK)
@track_request_time(endpoint="bulk_review_action")
@throttle_requests(max_requests=5, window_seconds=60)
@invalidate_cache(namespace="reviews", tags=["reviews"])
async def bulk_review_action(
    action_request: ReviewBulkActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Thực hiện hành động hàng loạt trên nhiều đánh giá.

    - Rate limiting: 5 request/phút để ngăn lạm dụng
    - Xác thực: Chỉ thực hiện trên đánh giá của người dùng hiện tại
    - Vô hiệu hóa cache: Đảm bảo dữ liệu mới nhất luôn được hiển thị
    """
    review_service = ReviewService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Hành động hàng loạt trên đánh giá - User: {current_user.id}, Action: {action_request.action}, IP: {client_ip}"
    )

    if not action_request.review_ids or len(action_request.review_ids) == 0:
        raise BadRequestException(detail="Cần cung cấp ít nhất một ID đánh giá")

    if len(action_request.review_ids) > 50:
        raise BadRequestException(
            detail="Chỉ có thể thực hiện hành động trên tối đa 50 đánh giá cùng lúc"
        )

    try:
        result = await review_service.bulk_action(
            user_id=current_user.id,
            review_ids=action_request.review_ids,
            action=action_request.action,
        )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            f"review_bulk_{action_request.action}",
            f"Người dùng đã thực hiện hành động {action_request.action} trên {len(action_request.review_ids)} đánh giá",
            metadata={
                "user_id": current_user.id,
                "review_ids": action_request.review_ids,
                "action": action_request.action,
                "success_count": result.get("success_count", 0),
            },
        )

        return {
            "success": True,
            "message": f"Đã thực hiện '{action_request.action}' thành công trên {result.get('success_count', 0)}/{len(action_request.review_ids)} đánh giá",
            "details": result,
        }
    except BadRequestException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi thực hiện hành động hàng loạt trên đánh giá: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi thực hiện hành động hàng loạt",
        )
