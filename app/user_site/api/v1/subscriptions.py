from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
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
from app.user_site.api.v1 import throttle_requests
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.db.session import get_db
from app.user_site.api.deps import get_current_active_user
from app.user_site.models.user import User
from app.user_site.schemas.subscription import (
    SubscriptionResponse,
    SubscriptionCreate,
    SubscriptionListResponse,
    SubscriptionPlanResponse,
    SubscriptionPlanListResponse,
    SubscriptionUsageResponse,
    SubscriptionExtendRequest,
)
from app.user_site.services.subscription_service import SubscriptionService
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
logger = get_logger("subscription_api")
audit_logger = AuditLogger()


@router.get("/plans", response_model=SubscriptionPlanListResponse)
@track_request_time(endpoint="list_subscription_plans")
@cache_response(ttl=3600)  # Cache for 1 hour
async def list_subscription_plans(db: AsyncSession = Depends(get_db)):
    """
    Lấy danh sách các gói đăng ký.

    - Tối ưu hiệu suất: Cache kết quả trong 1 giờ
    - API công khai: Không yêu cầu đăng nhập
    """
    subscription_service = SubscriptionService(db)

    try:
        plans, total = await subscription_service.list_subscription_plans()

        return {"items": plans, "total": total}
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách gói đăng ký: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy danh sách gói đăng ký",
        )


@router.get("/plans/{plan_id}", response_model=SubscriptionPlanResponse)
@track_request_time(endpoint="get_subscription_plan")
@cache_response(ttl=3600, vary_by=["plan_id"])  # Cache for 1 hour
async def get_subscription_plan(
    plan_id: int = Path(..., gt=0, description="ID của gói đăng ký"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy thông tin chi tiết của một gói đăng ký.

    - Tối ưu hiệu suất: Cache kết quả trong 1 giờ
    - API công khai: Không yêu cầu đăng nhập
    """
    subscription_service = SubscriptionService(db)

    try:
        plan = await subscription_service.get_subscription_plan_by_id(plan_id)

        if not plan:
            raise NotFoundException(
                detail=f"Không tìm thấy gói đăng ký với ID: {plan_id}"
            )

        return plan
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin gói đăng ký {plan_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy thông tin gói đăng ký",
        )


@router.post(
    "/", response_model=SubscriptionResponse, status_code=status.HTTP_201_CREATED
)
@track_request_time(endpoint="create_subscription")
@throttle_requests(max_requests=5, window_seconds=60)  # Rate limiting
@invalidate_cache(namespace="subscriptions", tags=["subscriptions"])
async def create_subscription(
    data: SubscriptionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Tạo đăng ký mới cho người dùng.

    - Rate limiting: 5 request/phút để ngăn spam
    - Xác thực: Yêu cầu người dùng đăng nhập
    - Vô hiệu hóa cache: Đảm bảo dữ liệu mới nhất
    """
    subscription_service = SubscriptionService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Tạo đăng ký mới - User: {current_user.id}, Plan: {data.plan_id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra gói đăng ký có tồn tại không
        plan = await subscription_service.get_subscription_plan_by_id(data.plan_id)

        if not plan:
            raise NotFoundException(
                detail=f"Không tìm thấy gói đăng ký với ID: {data.plan_id}"
            )

        # Kiểm tra người dùng đã có đăng ký active với gói này chưa
        active_subscription = (
            await subscription_service.get_active_subscription_by_plan(
                current_user.id, data.plan_id
            )
        )

        if active_subscription:
            raise BadRequestException(
                detail="Bạn đã có đăng ký với gói này và còn hiệu lực"
            )

        # Tạo đăng ký mới
        subscription = await subscription_service.create_subscription(
            current_user.id, data.model_dump()
        )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "subscription_create",
            f"Người dùng đã đăng ký gói {data.plan_id}",
            metadata={
                "user_id": current_user.id,
                "plan_id": data.plan_id,
                "subscription_id": (
                    subscription.id if hasattr(subscription, "id") else None
                ),
                "amount": data.amount if hasattr(data, "amount") else None,
            },
        )

        # Tăng counter cho metrics
        increment_counter("subscriptions_created_total")

        return subscription
    except (NotFoundException, BadRequestException):
        raise
    except Exception as e:
        logger.error(
            f"Lỗi khi tạo đăng ký mới cho người dùng {current_user.id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi tạo đăng ký mới",
        )


@router.get("/", response_model=SubscriptionListResponse)
@track_request_time(endpoint="list_user_subscriptions")
@cache_response(ttl=300, vary_by=["current_user.id", "status"])  # Cache for 5 minutes
async def list_user_subscriptions(
    status: Optional[str] = Query(
        None, description="Lọc theo trạng thái (active, expired, cancelled)"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy danh sách đăng ký của người dùng hiện tại.

    - Tối ưu hiệu suất: Cache kết quả trong 5 phút
    - Hỗ trợ lọc theo trạng thái
    - Xác thực: Yêu cầu người dùng đăng nhập
    """
    subscription_service = SubscriptionService(db)

    try:
        # Validate status parameter
        if status and status not in ["active", "expired", "cancelled"]:
            raise BadRequestException(
                detail="Giá trị status không hợp lệ. Các giá trị hợp lệ: active, expired, cancelled"
            )

        subscriptions, total = await subscription_service.list_user_subscriptions(
            current_user.id, status=status
        )

        return {"items": subscriptions, "total": total}
    except BadRequestException:
        raise
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy danh sách đăng ký của người dùng {current_user.id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy danh sách đăng ký",
        )


@router.get("/active", response_model=List[SubscriptionResponse])
@track_request_time(endpoint="get_active_subscriptions")
@cache_response(ttl=300, vary_by=["current_user.id"])  # Cache for 5 minutes
async def get_active_subscriptions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy danh sách đăng ký đang hoạt động của người dùng hiện tại.

    - Tối ưu hiệu suất: Cache kết quả trong 5 phút
    - API chuyên biệt: Chỉ lấy các đăng ký đang hoạt động
    - Xác thực: Yêu cầu người dùng đăng nhập
    """
    subscription_service = SubscriptionService(db)

    try:
        active_subscriptions = await subscription_service.get_active_subscriptions(
            current_user.id
        )
        return active_subscriptions
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy danh sách đăng ký đang hoạt động của người dùng {current_user.id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy danh sách đăng ký đang hoạt động",
        )


@router.get("/{subscription_id}", response_model=SubscriptionResponse)
@track_request_time(endpoint="get_subscription")
@cache_response(
    ttl=300, vary_by=["subscription_id", "current_user.id"]
)  # Cache for 5 minutes
async def get_subscription(
    subscription_id: int = Path(..., gt=0, description="ID của đăng ký"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy thông tin chi tiết của một đăng ký.

    - Tối ưu hiệu suất: Cache kết quả trong 5 phút
    - Bảo mật: Chỉ người dùng sở hữu mới có thể xem
    - Xác thực: Yêu cầu người dùng đăng nhập
    """
    subscription_service = SubscriptionService(db)

    try:
        subscription = await subscription_service.get_subscription_by_id(
            subscription_id, current_user.id
        )

        if not subscription:
            raise NotFoundException(
                detail=f"Không tìm thấy đăng ký với ID: {subscription_id} hoặc bạn không có quyền xem"
            )

        return subscription
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy thông tin đăng ký {subscription_id} của người dùng {current_user.id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy thông tin đăng ký",
        )


@router.post("/{subscription_id}/cancel", response_model=SubscriptionResponse)
@track_request_time(endpoint="cancel_subscription")
@throttle_requests(max_requests=5, window_seconds=60)  # Rate limiting
@invalidate_cache(namespace="subscriptions", tags=["subscriptions"])
async def cancel_subscription(
    subscription_id: int = Path(..., gt=0, description="ID của đăng ký"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Hủy đăng ký.

    - Rate limiting: 5 request/phút để ngăn lạm dụng
    - Vô hiệu hóa cache: Đảm bảo dữ liệu mới nhất
    - Xác thực: Chỉ người dùng sở hữu mới có thể hủy
    """
    subscription_service = SubscriptionService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Hủy đăng ký - ID: {subscription_id}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra đăng ký có tồn tại không và thuộc về người dùng hiện tại
        subscription = await subscription_service.get_subscription_by_id(
            subscription_id, current_user.id
        )

        if not subscription:
            raise NotFoundException(
                detail=f"Không tìm thấy đăng ký với ID: {subscription_id} hoặc bạn không có quyền hủy"
            )

        # Kiểm tra đăng ký đã bị hủy chưa
        if subscription.status == "cancelled":
            raise BadRequestException(detail="Đăng ký này đã bị hủy trước đó")

        # Kiểm tra đăng ký đã hết hạn chưa
        if subscription.status == "expired":
            raise BadRequestException(detail="Đăng ký này đã hết hạn và không thể hủy")

        updated_subscription = await subscription_service.cancel_subscription(
            subscription_id, current_user.id
        )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "subscription_cancel",
            f"Người dùng đã hủy đăng ký {subscription_id}",
            metadata={"user_id": current_user.id, "subscription_id": subscription_id},
        )

        # Tăng counter cho metrics
        increment_counter("subscriptions_cancelled_total")

        return updated_subscription
    except (NotFoundException, BadRequestException):
        raise
    except Exception as e:
        logger.error(
            f"Lỗi khi hủy đăng ký {subscription_id} của người dùng {current_user.id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi hủy đăng ký",
        )


@router.get("/check-access/{feature}", response_model=Dict[str, bool])
@track_request_time(endpoint="check_feature_access")
@cache_response(ttl=300, vary_by=["feature", "current_user.id"])  # Cache for 5 minutes
async def check_feature_access(
    feature: str = Path(..., description="Tên tính năng cần kiểm tra"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Kiểm tra quyền truy cập vào một tính năng dựa trên đăng ký của người dùng.

    - Tối ưu hiệu suất: Cache kết quả trong 5 phút
    - Xác thực: Yêu cầu người dùng đăng nhập
    - Feature check: Kiểm tra quyền truy cập dựa trên đăng ký của người dùng
    """
    subscription_service = SubscriptionService(db)

    try:
        # Validate feature parameter
        valid_features = await subscription_service.get_available_features()
        if feature not in valid_features:
            raise BadRequestException(
                detail=f"Tính năng không hợp lệ. Các tính năng hợp lệ: {', '.join(valid_features)}"
            )

        has_access = await subscription_service.check_feature_access(
            current_user.id, feature
        )

        # Ghi log sự kiện kiểm tra quyền truy cập
        logger.debug(
            f"Feature access check - User: {current_user.id}, Feature: {feature}, Result: {has_access}"
        )

        return {"has_access": has_access, "feature": feature}
    except BadRequestException:
        raise
    except Exception as e:
        logger.error(
            f"Lỗi khi kiểm tra quyền truy cập tính năng {feature} cho người dùng {current_user.id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi kiểm tra quyền truy cập",
        )


@router.post("/{subscription_id}/extend", response_model=SubscriptionResponse)
@track_request_time(endpoint="extend_subscription")
@throttle_requests(max_requests=3, window_seconds=60)  # Very strict rate limiting
@invalidate_cache(namespace="subscriptions", tags=["subscriptions"])
async def extend_subscription(
    data: SubscriptionExtendRequest,
    subscription_id: int = Path(..., gt=0, description="ID của đăng ký"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Gia hạn đăng ký hiện tại.

    - Rate limiting: 3 request/phút để ngăn lạm dụng
    - Vô hiệu hóa cache: Đảm bảo dữ liệu mới nhất
    - Xác thực: Chỉ người dùng sở hữu mới có thể gia hạn
    """
    subscription_service = SubscriptionService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Gia hạn đăng ký - ID: {subscription_id}, User: {current_user.id}, Duration: {data.duration} tháng, IP: {client_ip}"
    )

    try:
        # Kiểm tra đăng ký có tồn tại không và thuộc về người dùng hiện tại
        subscription = await subscription_service.get_subscription_by_id(
            subscription_id, current_user.id
        )

        if not subscription:
            raise NotFoundException(
                detail=f"Không tìm thấy đăng ký với ID: {subscription_id} hoặc bạn không có quyền gia hạn"
            )

        # Kiểm tra đăng ký đã bị hủy chưa
        if subscription.status == "cancelled":
            raise BadRequestException(
                detail="Đăng ký đã bị hủy không thể gia hạn. Vui lòng tạo đăng ký mới."
            )

        # Validate duration (e.g., must be between 1-12 months)
        if data.duration < 1 or data.duration > 12:
            raise BadRequestException(detail="Thời gian gia hạn phải từ 1 đến 12 tháng")

        extended_subscription = await subscription_service.extend_subscription(
            subscription_id=subscription_id,
            user_id=current_user.id,
            months=data.duration,
            payment_method=data.payment_method,
        )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "subscription_extend",
            f"Người dùng đã gia hạn đăng ký {subscription_id} thêm {data.duration} tháng",
            metadata={
                "user_id": current_user.id,
                "subscription_id": subscription_id,
                "duration": data.duration,
                "payment_method": data.payment_method,
                "amount": data.amount if hasattr(data, "amount") else None,
            },
        )

        # Tăng counter cho metrics
        increment_counter("subscriptions_extended_total")

        return extended_subscription
    except (NotFoundException, BadRequestException):
        raise
    except Exception as e:
        logger.error(
            f"Lỗi khi gia hạn đăng ký {subscription_id} của người dùng {current_user.id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi gia hạn đăng ký",
        )


@router.get("/usage", response_model=SubscriptionUsageResponse)
@track_request_time(endpoint="get_subscription_usage")
@cache_response(ttl=60, vary_by=["current_user.id"])  # Short cache for fresh data
async def get_subscription_usage(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy thông tin sử dụng đăng ký của người dùng hiện tại.

    - Tối ưu hiệu suất: Cache kết quả trong 1 phút
    - Xác thực: Yêu cầu người dùng đăng nhập
    - Theo dõi sử dụng: Cung cấp thông tin chi tiết về mức sử dụng
    """
    subscription_service = SubscriptionService(db)

    try:
        usage = await subscription_service.get_subscription_usage(current_user.id)
        return usage
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy thông tin sử dụng đăng ký của người dùng {current_user.id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy thông tin sử dụng đăng ký",
        )


@router.get("/summary", response_model=Dict[str, Any])
@track_request_time(endpoint="get_subscription_summary")
@cache_response(ttl=300, vary_by=["current_user.id"])  # Cache for 5 minutes
async def get_subscription_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy thông tin tóm tắt về đăng ký của người dùng.

    - Tối ưu hiệu suất: Cache kết quả trong 5 phút
    - Xác thực: Yêu cầu người dùng đăng nhập
    - Tổng quan: Cung cấp thông tin tóm tắt về đăng ký hiện tại
    """
    subscription_service = SubscriptionService(db)

    try:
        active_subscriptions = await subscription_service.get_active_subscriptions(
            current_user.id
        )

        if not active_subscriptions:
            return {
                "has_active_subscription": False,
                "plan_name": None,
                "expiry_date": None,
                "days_remaining": 0,
                "features": [],
            }

        # Lấy thông tin đăng ký đầu tiên trong danh sách
        subscription = active_subscriptions[0]

        # Tính số ngày còn lại
        expiry_date = subscription.expiry_date
        days_remaining = 0

        if expiry_date:
            now = datetime.now(timezone.utc)
            delta = expiry_date - now
            days_remaining = max(0, delta.days)

        # Lấy danh sách tính năng
        features = await subscription_service.get_plan_features(subscription.plan_id)

        return {
            "has_active_subscription": True,
            "subscription_id": subscription.id,
            "plan_id": subscription.plan_id,
            "plan_name": (
                subscription.plan_name
                if hasattr(subscription, "plan_name")
                else "Unknown Plan"
            ),
            "expiry_date": expiry_date,
            "days_remaining": days_remaining,
            "features": features,
            "is_auto_renew": (
                subscription.is_auto_renew
                if hasattr(subscription, "is_auto_renew")
                else False
            ),
        }
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy thông tin tóm tắt đăng ký của người dùng {current_user.id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy thông tin tóm tắt đăng ký",
        )
