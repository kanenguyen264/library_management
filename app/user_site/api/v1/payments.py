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
from app.user_site.api.v1 import throttle_requests
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.db.session import get_db
from app.user_site.api.deps import get_current_active_user
from app.user_site.models.user import User
from app.user_site.schemas.payment import (
    PaymentCreate,
    PaymentResponse,
    PaymentMethodCreate,
    PaymentMethodResponse,
    PaymentListResponse,
    PaymentMethodListResponse,
    PaymentStatusUpdate,
    PaymentRefund,
    PaymentStatsResponse,
    PaymentSearchParams,
)
from app.user_site.services.payment_service import PaymentService
from app.logging.setup import get_logger
from app.monitoring.metrics import track_request_time
from app.cache.decorators import cache_response, invalidate_cache
from app.security.audit.audit_trails import AuditLogger
from app.core.exceptions import (
    NotFoundException,
    ForbiddenException,
    InvalidOperationException,
    ServerException,
)
from app.user_site.services.transaction_service import TransactionService

router = APIRouter()
logger = get_logger("payments_api")
audit_logger = AuditLogger()


@router.post(
    "/methods",
    response_model=PaymentMethodResponse,
    status_code=status.HTTP_201_CREATED,
)
@track_request_time(endpoint="create_payment_method")
async def create_payment_method(
    data: PaymentMethodCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Tạo phương thức thanh toán mới cho người dùng.

    Hỗ trợ nhiều loại phương thức thanh toán như thẻ tín dụng, ví điện tử, ngân hàng trực tuyến.
    Thông tin nhạy cảm sẽ được mã hóa trước khi lưu trữ.
    """
    payment_service = PaymentService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Tạo phương thức thanh toán - User: {current_user.id}, Type: {data.payment_type}, IP: {client_ip}"
    )

    try:
        # Giới hạn tốc độ tạo phương thức thanh toán
        await throttle_requests(
            "create_payment_method",
            limit=5,
            period=3600,
            current_user=current_user,
            request=request,
            db=db,
        )

        # Kiểm tra số lượng phương thức thanh toán hiện tại của người dùng
        current_methods = await payment_service.get_user_payment_methods(
            current_user.id
        )

        # Giới hạn số lượng phương thức thanh toán (có thể điều chỉnh theo chính sách)
        if len(current_methods) >= 5:
            raise InvalidOperationException(
                detail="Đã đạt giới hạn số lượng phương thức thanh toán (tối đa 5)",
                code="max_payment_methods_reached",
            )

        # Mã hóa thông tin thanh toán nhạy cảm
        method = await payment_service.create_payment_method(current_user.id, data)

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "payment_method_create",
            f"Người dùng đã thêm phương thức thanh toán mới",
            metadata={"user_id": current_user.id, "payment_type": data.payment_type},
        )

        return method
    except InvalidOperationException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi tạo phương thức thanh toán: {str(e)}")
        raise ServerException(detail="Lỗi khi tạo phương thức thanh toán")


@router.get("/methods", response_model=PaymentMethodListResponse)
@track_request_time(endpoint="list_payment_methods")
@cache_response(ttl=300, vary_by=["current_user.id"])
async def list_payment_methods(
    payment_type: Optional[str] = Query(
        None, description="Lọc theo loại phương thức thanh toán"
    ),
    is_default: Optional[bool] = Query(
        None, description="Lọc theo phương thức thanh toán mặc định"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy danh sách phương thức thanh toán của người dùng hiện tại.

    Có thể lọc theo loại phương thức thanh toán hoặc trạng thái mặc định.
    """
    payment_service = PaymentService(db)

    try:
        methods = await payment_service.get_user_payment_methods(
            user_id=current_user.id, payment_type=payment_type, is_default=is_default
        )
        return {"items": methods, "total": len(methods)}
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy danh sách phương thức thanh toán cho người dùng {current_user.id}: {str(e)}"
        )
        raise ServerException(detail="Lỗi khi lấy danh sách phương thức thanh toán")


@router.get("/methods/{method_id}", response_model=PaymentMethodResponse)
@track_request_time(endpoint="get_payment_method")
@cache_response(ttl=300, vary_by=["method_id", "current_user.id"])
async def get_payment_method(
    method_id: int = Path(..., gt=0, description="ID của phương thức thanh toán"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy thông tin chi tiết của một phương thức thanh toán.

    Thông tin nhạy cảm như số thẻ sẽ được ẩn một phần để bảo vệ thông tin người dùng.
    """
    payment_service = PaymentService(db)

    try:
        method = await payment_service.get_payment_method(method_id)

        if not method:
            raise NotFoundException(
                detail=f"Không tìm thấy phương thức thanh toán với ID: {method_id}"
            )

        # Kiểm tra quyền truy cập
        if method.user_id != current_user.id:
            raise ForbiddenException(
                detail="Bạn không có quyền xem phương thức thanh toán này"
            )

        return method
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy thông tin phương thức thanh toán {method_id}: {str(e)}"
        )
        raise ServerException(detail="Lỗi khi lấy thông tin phương thức thanh toán")


@router.post("/methods/{method_id}/default", response_model=PaymentMethodResponse)
@track_request_time(endpoint="set_default_payment_method")
async def set_default_payment_method(
    method_id: int = Path(..., gt=0, description="ID của phương thức thanh toán"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Đặt phương thức thanh toán làm mặc định.

    Chỉ có thể có một phương thức thanh toán mặc định cho mỗi người dùng.
    """
    payment_service = PaymentService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Đặt phương thức thanh toán mặc định - ID: {method_id}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        method = await payment_service.get_payment_method(method_id)

        if not method:
            raise NotFoundException(
                detail=f"Không tìm thấy phương thức thanh toán với ID: {method_id}"
            )

        # Kiểm tra quyền truy cập
        if method.user_id != current_user.id:
            raise ForbiddenException(
                detail="Bạn không có quyền chỉnh sửa phương thức thanh toán này"
            )

        updated_method = await payment_service.set_default_payment_method(
            method_id, current_user.id
        )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "payment_method_set_default",
            f"Người dùng đã đặt phương thức thanh toán {method_id} làm mặc định",
            metadata={"user_id": current_user.id, "method_id": method_id},
        )

        return updated_method
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        logger.error(
            f"Lỗi khi đặt phương thức thanh toán mặc định {method_id}: {str(e)}"
        )
        raise ServerException(detail="Lỗi khi đặt phương thức thanh toán mặc định")


@router.delete("/methods/{method_id}", status_code=status.HTTP_204_NO_CONTENT)
@track_request_time(endpoint="delete_payment_method")
async def delete_payment_method(
    method_id: int = Path(..., gt=0, description="ID của phương thức thanh toán"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Xóa phương thức thanh toán.

    Phương thức thanh toán đang được sử dụng cho các giao dịch đang hoạt động
    sẽ không thể bị xóa để đảm bảo tính toàn vẹn dữ liệu.
    """
    payment_service = PaymentService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Xóa phương thức thanh toán - ID: {method_id}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        method = await payment_service.get_payment_method(method_id)

        if not method:
            raise NotFoundException(
                detail=f"Không tìm thấy phương thức thanh toán với ID: {method_id}"
            )

        # Kiểm tra quyền truy cập
        if method.user_id != current_user.id:
            raise ForbiddenException(
                detail="Bạn không có quyền xóa phương thức thanh toán này"
            )

        # Kiểm tra xem có thể xóa phương thức này không
        can_delete = await payment_service.can_delete_payment_method(method_id)

        if not can_delete:
            raise InvalidOperationException(
                detail="Không thể xóa phương thức thanh toán này vì đang được sử dụng cho các thanh toán đang hoạt động",
                code="method_in_use",
            )

        await payment_service.delete_payment_method(method_id)

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "payment_method_delete",
            f"Người dùng đã xóa phương thức thanh toán {method_id}",
            metadata={"user_id": current_user.id, "method_id": method_id},
        )

        return None
    except (NotFoundException, ForbiddenException, InvalidOperationException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi xóa phương thức thanh toán {method_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi xóa phương thức thanh toán")


@router.post("/", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
@track_request_time(endpoint="create_payment")
async def create_payment(
    data: PaymentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Tạo một giao dịch thanh toán mới.

    Hỗ trợ thanh toán cho sách, gói dịch vụ và các sản phẩm khác.
    Thanh toán sẽ được xử lý thông qua các cổng thanh toán tích hợp.
    """
    payment_service = PaymentService(db)
    transaction_service = TransactionService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Tạo giao dịch thanh toán - User: {current_user.id}, Amount: {data.amount}, IP: {client_ip}"
    )

    try:
        # Giới hạn tốc độ tạo thanh toán
        await throttle_requests(
            "create_payment",
            limit=10,
            period=3600,
            current_user=current_user,
            request=request,
            db=db,
        )

        # Kiểm tra phương thức thanh toán có hợp lệ không
        if data.payment_method_id:
            method = await payment_service.get_payment_method(data.payment_method_id)

            if not method:
                raise NotFoundException(
                    detail=f"Không tìm thấy phương thức thanh toán với ID: {data.payment_method_id}",
                    code="payment_method_not_found",
                )

            if method.user_id != current_user.id:
                raise ForbiddenException(
                    detail="Bạn không có quyền sử dụng phương thức thanh toán này",
                    code="not_owner_of_payment_method",
                )

        # Kiểm tra item_id (sách, gói đăng ký) có tồn tại không
        item_exists = await payment_service.is_item_exists(data.item_type, data.item_id)

        if not item_exists:
            raise NotFoundException(
                detail=f"Không tìm thấy {data.item_type} với ID: {data.item_id}",
                code="item_not_found",
            )

        # Bắt đầu giao dịch để đảm bảo tính nhất quán dữ liệu
        async with transaction_service.start_transaction():
            payment = await payment_service.create_payment(current_user.id, data)

            # Tích hợp với cổng thanh toán bên ngoài nếu cần
            if data.process_immediately and data.payment_method_id:
                await payment_service.process_payment_with_gateway(payment.id)

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "payment_create",
            f"Người dùng đã tạo giao dịch thanh toán mới",
            metadata={
                "user_id": current_user.id,
                "amount": str(data.amount),
                "currency": data.currency,
                "item_type": data.item_type,
                "item_id": data.item_id,
            },
        )

        return payment
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi tạo giao dịch thanh toán: {str(e)}")
        raise ServerException(detail="Lỗi khi tạo giao dịch thanh toán")


@router.get("/", response_model=PaymentListResponse)
@track_request_time(endpoint="list_payments")
@cache_response(
    ttl=300,
    vary_by=[
        "current_user.id",
        "page",
        "limit",
        "status",
        "item_type",
        "start_date",
        "end_date",
    ],
)
async def list_payments(
    page: int = Query(1, ge=1, description="Trang hiện tại"),
    limit: int = Query(20, ge=1, le=100, description="Số lượng kết quả mỗi trang"),
    status: Optional[str] = Query(None, description="Lọc theo trạng thái thanh toán"),
    item_type: Optional[str] = Query(None, description="Lọc theo loại mục"),
    start_date: Optional[str] = Query(
        None, description="Ngày bắt đầu (format: YYYY-MM-DD)"
    ),
    end_date: Optional[str] = Query(
        None, description="Ngày kết thúc (format: YYYY-MM-DD)"
    ),
    sort_by: str = Query(
        "created_at",
        regex="^(created_at|amount|status)$",
        description="Sắp xếp theo trường",
    ),
    sort_desc: bool = Query(True, description="Sắp xếp giảm dần"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy danh sách các giao dịch thanh toán của người dùng hiện tại với nhiều tùy chọn lọc và sắp xếp.

    - **page**: Trang hiện tại
    - **limit**: Số lượng kết quả mỗi trang
    - **status**: Lọc theo trạng thái (pending, completed, failed, refunded, etc.)
    - **item_type**: Lọc theo loại mục (book, subscription, etc.)
    - **start_date**: Lọc từ ngày
    - **end_date**: Lọc đến ngày
    - **sort_by**: Sắp xếp theo trường (created_at, amount, status)
    - **sort_desc**: Sắp xếp giảm dần
    """
    payment_service = PaymentService(db)

    try:
        # Tính toán skip từ page và limit
        skip = (page - 1) * limit

        # Tạo dict các tham số filter
        filters = {
            "user_id": current_user.id,
            "status": status,
            "item_type": item_type,
            "start_date": start_date,
            "end_date": end_date,
            "skip": skip,
            "limit": limit,
            "sort_by": sort_by,
            "sort_desc": sort_desc,
        }

        payments, total = await payment_service.list_user_payments(**filters)

        # Tính toán tổng số trang
        total_pages = (total + limit - 1) // limit if total > 0 else 0

        return {
            "items": payments,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
        }
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy danh sách giao dịch thanh toán cho người dùng {current_user.id}: {str(e)}"
        )
        raise ServerException(detail="Lỗi khi lấy danh sách giao dịch thanh toán")


@router.post("/search", response_model=PaymentListResponse)
@track_request_time(endpoint="search_payments")
async def search_payments(
    search_params: PaymentSearchParams,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Tìm kiếm nâng cao các giao dịch thanh toán với nhiều điều kiện lọc.

    Cho phép tìm kiếm theo nhiều tiêu chí như khoảng số tiền, loại thanh toán,
    trạng thái, và khoảng thời gian.
    """
    payment_service = PaymentService(db)

    try:
        # Tính toán skip từ page và limit
        skip = (search_params.page - 1) * search_params.limit

        # Tạo dict tham số tìm kiếm
        search_dict = search_params.model_dump(exclude={"page", "limit"})
        search_dict["user_id"] = current_user.id
        search_dict["skip"] = skip
        search_dict["limit"] = search_params.limit

        payments, total = await payment_service.search_payments(**search_dict)

        # Tính toán tổng số trang
        total_pages = (
            (total + search_params.limit - 1) // search_params.limit if total > 0 else 0
        )

        return {
            "items": payments,
            "total": total,
            "page": search_params.page,
            "limit": search_params.limit,
            "total_pages": total_pages,
        }
    except Exception as e:
        logger.error(f"Lỗi khi tìm kiếm giao dịch thanh toán: {str(e)}")
        raise ServerException(detail="Lỗi khi tìm kiếm giao dịch thanh toán")


@router.get("/{payment_id}", response_model=PaymentResponse)
@track_request_time(endpoint="get_payment")
@cache_response(ttl=300, vary_by=["payment_id", "current_user.id"])
async def get_payment(
    payment_id: str = Path(..., description="ID của giao dịch thanh toán"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy thông tin chi tiết của một giao dịch thanh toán.

    Bao gồm thông tin về trạng thái thanh toán, phương thức thanh toán được sử dụng
    và mục được thanh toán.
    """
    payment_service = PaymentService(db)

    try:
        payment = await payment_service.get_payment(payment_id)

        if not payment:
            raise NotFoundException(
                detail=f"Không tìm thấy giao dịch thanh toán với ID: {payment_id}",
                code="payment_not_found",
            )

        # Kiểm tra quyền truy cập
        if payment.user_id != current_user.id:
            raise ForbiddenException(
                detail="Bạn không có quyền xem giao dịch thanh toán này",
                code="not_payment_owner",
            )

        return payment
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy thông tin giao dịch thanh toán {payment_id}: {str(e)}"
        )
        raise ServerException(detail="Lỗi khi lấy thông tin giao dịch thanh toán")


@router.put("/{payment_id}/status", response_model=PaymentResponse)
@track_request_time(endpoint="update_payment_status")
@invalidate_cache(namespace="payments", tags=["user_payments"])
async def update_payment_status(
    data: PaymentStatusUpdate,
    payment_id: str = Path(..., description="ID của giao dịch thanh toán"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Cập nhật trạng thái thanh toán (chỉ cho các bước xác nhận từ phía người dùng).

    Người dùng có thể hủy hoặc xác nhận giao dịch tùy thuộc vào trạng thái hiện tại.
    Các trạng thái hệ thống (như completed, processed) chỉ được cập nhật bởi hệ thống.
    """
    payment_service = PaymentService(db)
    transaction_service = TransactionService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Cập nhật trạng thái thanh toán - ID: {payment_id}, Status: {data.status}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        payment = await payment_service.get_payment(payment_id)

        if not payment:
            raise NotFoundException(
                detail=f"Không tìm thấy giao dịch thanh toán với ID: {payment_id}",
                code="payment_not_found",
            )

        # Kiểm tra quyền truy cập
        if payment.user_id != current_user.id:
            raise ForbiddenException(
                detail="Bạn không có quyền cập nhật giao dịch thanh toán này",
                code="not_payment_owner",
            )

        # Kiểm tra trạng thái có hợp lệ không
        allowed_status_updates = ["cancelled", "confirmed"]
        if data.status not in allowed_status_updates:
            raise InvalidOperationException(
                detail=f"Không thể cập nhật trạng thái thanh toán thành '{data.status}'. Chỉ cho phép: {', '.join(allowed_status_updates)}",
                code="invalid_status_update",
            )

        # Bắt đầu giao dịch để đảm bảo tính nhất quán dữ liệu
        async with transaction_service.start_transaction():
            updated_payment = await payment_service.update_payment_status(
                payment_id, data.status
            )

            # Nếu xác nhận thanh toán, xử lý các tác vụ liên quan
            if data.status == "confirmed" and payment.payment_method_id:
                await payment_service.process_payment_with_gateway(payment_id)

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "payment_status_update",
            f"Người dùng đã cập nhật trạng thái giao dịch thanh toán {payment_id} thành {data.status}",
            metadata={
                "user_id": current_user.id,
                "payment_id": payment_id,
                "status": data.status,
            },
        )

        return updated_payment
    except (NotFoundException, ForbiddenException, InvalidOperationException):
        raise
    except Exception as e:
        logger.error(
            f"Lỗi khi cập nhật trạng thái giao dịch thanh toán {payment_id}: {str(e)}"
        )
        raise ServerException(detail="Lỗi khi cập nhật trạng thái giao dịch thanh toán")


@router.post("/{payment_id}/refund", response_model=PaymentResponse)
@track_request_time(endpoint="request_refund")
@invalidate_cache(namespace="payments", tags=["user_payments"])
async def request_refund(
    data: PaymentRefund,
    payment_id: str = Path(..., description="ID của giao dịch thanh toán"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Yêu cầu hoàn tiền cho một giao dịch thanh toán.

    Chỉ có thể yêu cầu hoàn tiền cho các giao dịch đã hoàn thành hoặc đã được xác thực.
    Hoàn tiền thường được xử lý theo chính sách của cửa hàng và có thể mất vài ngày.
    """
    payment_service = PaymentService(db)
    transaction_service = TransactionService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Yêu cầu hoàn tiền - ID: {payment_id}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Giới hạn tốc độ yêu cầu hoàn tiền
        await throttle_requests(
            "request_refund",
            limit=5,
            period=86400,
            current_user=current_user,
            request=request,
            db=db,
        )

        payment = await payment_service.get_payment(payment_id)

        if not payment:
            raise NotFoundException(
                detail=f"Không tìm thấy giao dịch thanh toán với ID: {payment_id}",
                code="payment_not_found",
            )

        # Kiểm tra quyền truy cập
        if payment.user_id != current_user.id:
            raise ForbiddenException(
                detail="Bạn không có quyền yêu cầu hoàn tiền cho giao dịch thanh toán này",
                code="not_payment_owner",
            )

        # Kiểm tra xem giao dịch có thể yêu cầu hoàn tiền không
        if payment.status not in ["completed", "authorized"]:
            raise InvalidOperationException(
                detail="Chỉ có thể yêu cầu hoàn tiền cho các giao dịch đã hoàn thành hoặc đã được xác thực",
                code="invalid_payment_status_for_refund",
            )

        # Kiểm tra thời gian yêu cầu hoàn tiền (VD: trong vòng 30 ngày)
        is_refundable = await payment_service.is_payment_refundable(payment_id)

        if not is_refundable:
            raise InvalidOperationException(
                detail="Giao dịch này đã quá thời hạn hoàn tiền hoặc không đủ điều kiện để hoàn tiền",
                code="not_refundable",
            )

        # Bắt đầu giao dịch để đảm bảo tính nhất quán dữ liệu
        async with transaction_service.start_transaction():
            updated_payment = await payment_service.request_refund(
                payment_id, data.reason
            )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "payment_refund_request",
            f"Người dùng đã yêu cầu hoàn tiền cho giao dịch thanh toán {payment_id}",
            metadata={
                "user_id": current_user.id,
                "payment_id": payment_id,
                "reason": data.reason,
            },
        )

        return updated_payment
    except (NotFoundException, ForbiddenException, InvalidOperationException):
        raise
    except Exception as e:
        logger.error(
            f"Lỗi khi yêu cầu hoàn tiền cho giao dịch thanh toán {payment_id}: {str(e)}"
        )
        raise ServerException(detail="Lỗi khi yêu cầu hoàn tiền")


@router.get("/stats", response_model=PaymentStatsResponse)
@track_request_time(endpoint="get_payment_stats")
@cache_response(ttl=600, vary_by=["current_user.id", "period"])
async def get_payment_stats(
    period: str = Query(
        "month",
        regex="^(week|month|year|all)$",
        description="Khoảng thời gian thống kê",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy thống kê chi tiêu của người dùng.

    Bao gồm tổng số tiền đã chi, số lượng giao dịch theo từng trạng thái,
    và phân tích chi tiêu theo loại mục.
    """
    payment_service = PaymentService(db)

    try:
        stats = await payment_service.get_payment_stats(current_user.id, period)
        return stats
    except Exception as e:
        logger.error(f"Lỗi khi lấy thống kê thanh toán: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy thống kê thanh toán")


@router.get("/invoices/{payment_id}", response_model=Dict[str, Any])
@track_request_time(endpoint="get_payment_invoice")
async def get_payment_invoice(
    payment_id: str = Path(..., description="ID của giao dịch thanh toán"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy thông tin hóa đơn cho một giao dịch thanh toán.

    Trả về thông tin chi tiết về hóa đơn bao gồm người mua, người bán,
    các mục thanh toán, thuế và tổng cộng.
    """
    payment_service = PaymentService(db)

    try:
        payment = await payment_service.get_payment(payment_id)

        if not payment:
            raise NotFoundException(
                detail=f"Không tìm thấy giao dịch thanh toán với ID: {payment_id}",
                code="payment_not_found",
            )

        # Kiểm tra quyền truy cập
        if payment.user_id != current_user.id:
            raise ForbiddenException(
                detail="Bạn không có quyền xem hóa đơn này", code="not_payment_owner"
            )

        invoice = await payment_service.generate_invoice(payment_id)
        return invoice
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy hóa đơn cho giao dịch {payment_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy hóa đơn")
