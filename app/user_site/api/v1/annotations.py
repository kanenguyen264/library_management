from typing import Optional, List, Dict, Any
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Path,
    Query,
    status,
    Request,
    Body,
)
from sqlalchemy.ext.asyncio import AsyncSession
from app.cache.decorators import cache_response as cache

from app.common.db.session import get_db
from app.user_site.api.deps import (
    get_current_active_user,
    get_current_user)
from app.user_site.api.v1 import throttle_requests
from app.user_site.models.user import User
from app.user_site.schemas.annotation import (
    AnnotationResponse,
    AnnotationCreate,
    AnnotationUpdate,
    AnnotationListResponse,
    AnnotationSearchParams,
    AnnotationStatsResponse,
)
from app.user_site.services.annotation_service import AnnotationService
from app.logging.setup import get_logger
from app.monitoring.metrics import track_request_time
from app.security.audit.audit_trails import AuditLogger
from app.core.exceptions import (
    NotFoundException,
    ForbiddenException,
    BadRequestException,
)

router = APIRouter()
logger = get_logger("annotation_api")
audit_logger = AuditLogger()


@router.post(
    "/", response_model=AnnotationResponse, status_code=status.HTTP_201_CREATED
)
@track_request_time(endpoint="create_annotation")
async def create_annotation(
    data: AnnotationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Tạo một chú thích mới.

    Người dùng có thể tạo chú thích cho một cuốn sách hoặc chương sách cụ thể.
    Chú thích có thể chứa văn bản, highlight, vị trí trong sách và các metadata khác.
    """
    annotation_service = AnnotationService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Tạo chú thích mới - User: {current_user.id}, Book: {data.book_id}, IP: {client_ip}"
    )

    try:
        # Giới hạn tốc độ tạo chú thích để tránh spam
        await throttle_requests(
            "create_annotation",
            limit=20,
            period=60,
            current_user=current_user,
            request=request,
            db=db,
        )

        # Kiểm tra sách/chương có tồn tại không
        if not await annotation_service.validate_book_chapter(
            data.book_id, data.chapter_id
        ):
            raise BadRequestException(
                detail="Sách hoặc chương không tồn tại", code="invalid_book_chapter"
            )

        annotation = await annotation_service.create_annotation(
            current_user.id, data.model_dump()
        )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "annotation_create",
            f"Người dùng đã tạo chú thích mới cho sách {data.book_id}",
            metadata={"user_id": current_user.id, "book_id": data.book_id},
        )

        return annotation
    except BadRequestException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi tạo chú thích: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi tạo chú thích. Vui lòng thử lại sau.",
        )


@router.get("/", response_model=AnnotationListResponse)
@track_request_time(endpoint="list_annotations")
@cache(ttl=300, namespace="annotations")
async def list_annotations(
    book_id: Optional[int] = Query(None, gt=0, description="ID của sách"),
    chapter_id: Optional[int] = Query(None, gt=0, description="ID của chương"),
    type: Optional[str] = Query(
        None, description="Loại chú thích (highlight, note, bookmark)"
    ),
    color: Optional[str] = Query(None, description="Màu của highlight"),
    start_date: Optional[str] = Query(
        None, description="Ngày bắt đầu (format: YYYY-MM-DD)"
    ),
    end_date: Optional[str] = Query(
        None, description="Ngày kết thúc (format: YYYY-MM-DD)"
    ),
    page: int = Query(1, ge=1, description="Số trang"),
    limit: int = Query(20, ge=1, le=100, description="Số lượng kết quả mỗi trang"),
    sort_by: str = Query(
        "created_at",
        regex="^(created_at|updated_at|position)$",
        description="Sắp xếp theo trường",
    ),
    sort_desc: bool = Query(True, description="Sắp xếp giảm dần"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy danh sách chú thích của người dùng hiện tại với nhiều tùy chọn lọc và sắp xếp.

    - **book_id**: Lọc theo ID sách
    - **chapter_id**: Lọc theo ID chương
    - **type**: Lọc theo loại chú thích
    - **color**: Lọc theo màu của highlight
    - **start_date**: Lọc từ ngày
    - **end_date**: Lọc đến ngày
    - **page**: Số trang
    - **limit**: Số lượng kết quả mỗi trang
    - **sort_by**: Sắp xếp theo trường
    - **sort_desc**: Sắp xếp giảm dần
    """
    annotation_service = AnnotationService(db)

    try:
        # Tính toán skip từ page và limit
        skip = (page - 1) * limit

        # Tạo dict các tham số filter
        filters = {
            "book_id": book_id,
            "chapter_id": chapter_id,
            "type": type,
            "color": color,
            "start_date": start_date,
            "end_date": end_date,
        }

        annotations, total = await annotation_service.list_annotations(
            user_id=current_user.id,
            skip=skip,
            limit=limit,
            sort_by=sort_by,
            sort_desc=sort_desc,
            **{k: v for k, v in filters.items() if v is not None},
        )

        # Tính toán tổng số trang
        total_pages = (total + limit - 1) // limit if total > 0 else 0

        return {
            "items": annotations,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
        }
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách chú thích: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy danh sách chú thích. Vui lòng thử lại sau.",
        )


@router.get("/{annotation_id}", response_model=AnnotationResponse)
@track_request_time(endpoint="get_annotation")
async def get_annotation(
    annotation_id: int = Path(..., gt=0, description="ID của chú thích"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy thông tin chi tiết của một chú thích.

    Chỉ chủ sở hữu mới có thể xem chú thích.
    """
    annotation_service = AnnotationService(db)

    try:
        annotation = await annotation_service.get_annotation_by_id(
            annotation_id, current_user.id
        )

        if not annotation:
            raise NotFoundException(
                detail=f"Không tìm thấy chú thích với ID: {annotation_id}",
                code="annotation_not_found",
            )

        return annotation
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin chú thích {annotation_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy thông tin chú thích. Vui lòng thử lại sau.",
        )


@router.put("/{annotation_id}", response_model=AnnotationResponse)
@track_request_time(endpoint="update_annotation")
async def update_annotation(
    data: AnnotationUpdate,
    annotation_id: int = Path(..., gt=0, description="ID của chú thích"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Cập nhật thông tin chú thích.

    Chỉ chủ sở hữu mới có thể cập nhật chú thích.
    """
    annotation_service = AnnotationService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Cập nhật chú thích - ID: {annotation_id}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra chú thích có tồn tại và thuộc về người dùng hiện tại không
        annotation = await annotation_service.get_annotation_by_id(
            annotation_id, current_user.id
        )

        if not annotation:
            raise NotFoundException(
                detail=f"Không tìm thấy chú thích với ID: {annotation_id}",
                code="annotation_not_found",
            )

        updated_annotation = await annotation_service.update_annotation(
            annotation_id=annotation_id,
            user_id=current_user.id,
            data=data.model_dump(exclude_unset=True),
        )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "annotation_update",
            f"Người dùng đã cập nhật chú thích {annotation_id}",
            metadata={"user_id": current_user.id, "annotation_id": annotation_id},
        )

        return updated_annotation
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật chú thích {annotation_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi cập nhật chú thích. Vui lòng thử lại sau.",
        )


@router.delete("/{annotation_id}", status_code=status.HTTP_204_NO_CONTENT)
@track_request_time(endpoint="delete_annotation")
async def delete_annotation(
    annotation_id: int = Path(..., gt=0, description="ID của chú thích"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Xóa chú thích.

    Chỉ chủ sở hữu mới có thể xóa chú thích.
    """
    annotation_service = AnnotationService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Xóa chú thích - ID: {annotation_id}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra chú thích có tồn tại và thuộc về người dùng hiện tại không
        annotation = await annotation_service.get_annotation_by_id(
            annotation_id, current_user.id
        )

        if not annotation:
            raise NotFoundException(
                detail=f"Không tìm thấy chú thích với ID: {annotation_id}",
                code="annotation_not_found",
            )

        await annotation_service.delete_annotation(annotation_id, current_user.id)

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "annotation_delete",
            f"Người dùng đã xóa chú thích {annotation_id}",
            metadata={"user_id": current_user.id, "annotation_id": annotation_id},
        )

        return None
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi xóa chú thích {annotation_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi xóa chú thích. Vui lòng thử lại sau.",
        )


@router.post("/search", response_model=AnnotationListResponse)
@track_request_time(endpoint="search_annotations")
async def search_annotations(
    search_params: AnnotationSearchParams,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Tìm kiếm nâng cao các chú thích.

    Cho phép tìm kiếm theo nội dung, từ khóa, màu sắc, sách, chương và khoảng thời gian.
    """
    annotation_service = AnnotationService(db)

    try:
        # Tính toán skip từ page và limit
        skip = (search_params.page - 1) * search_params.limit

        annotations, total = await annotation_service.search_annotations(
            user_id=current_user.id,
            search_params=search_params.model_dump(),
            skip=skip,
            limit=search_params.limit,
        )

        # Tính toán tổng số trang
        total_pages = (
            (total + search_params.limit - 1) // search_params.limit if total > 0 else 0
        )

        return {
            "items": annotations,
            "total": total,
            "page": search_params.page,
            "limit": search_params.limit,
            "total_pages": total_pages,
        }
    except Exception as e:
        logger.error(f"Lỗi khi tìm kiếm chú thích: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi tìm kiếm chú thích. Vui lòng thử lại sau.",
        )


@router.delete("/bulk", status_code=status.HTTP_204_NO_CONTENT)
@track_request_time(endpoint="bulk_delete_annotations")
async def bulk_delete_annotations(
    annotation_ids: List[int] = Body(..., description="Danh sách ID chú thích cần xóa"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Xóa hàng loạt các chú thích.

    Chỉ xóa các chú thích thuộc sở hữu của người dùng hiện tại.
    """
    annotation_service = AnnotationService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Xóa hàng loạt chú thích - User: {current_user.id}, Count: {len(annotation_ids)}, IP: {client_ip}"
    )

    try:
        # Giới hạn số lượng chú thích có thể xóa cùng lúc
        if len(annotation_ids) > 100:
            raise BadRequestException(
                detail="Không thể xóa quá 100 chú thích cùng lúc",
                code="too_many_annotations",
            )

        deleted_count = await annotation_service.bulk_delete_annotations(
            user_id=current_user.id, annotation_ids=annotation_ids
        )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "annotation_bulk_delete",
            f"Người dùng đã xóa hàng loạt {deleted_count} chú thích",
            metadata={"user_id": current_user.id, "deleted_count": deleted_count},
        )

        return None
    except BadRequestException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi xóa hàng loạt chú thích: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi xóa hàng loạt chú thích. Vui lòng thử lại sau.",
        )


@router.get("/stats", response_model=AnnotationStatsResponse)
@track_request_time(endpoint="get_annotation_stats")
@cache(ttl=300, namespace="annotation_stats")
async def get_annotation_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy thống kê về các chú thích của người dùng.

    Bao gồm tổng số chú thích, phân loại theo loại, màu sắc, và thống kê theo sách.
    """
    annotation_service = AnnotationService(db)

    try:
        stats = await annotation_service.get_annotation_stats(current_user.id)
        return stats
    except Exception as e:
        logger.error(f"Lỗi khi lấy thống kê chú thích: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy thống kê chú thích. Vui lòng thử lại sau.",
        )


@router.get("/book/{book_id}/all", response_model=AnnotationListResponse)
@track_request_time(endpoint="get_book_annotations")
@cache(ttl=300, namespace="book_annotations")
async def get_book_annotations(
    book_id: int = Path(..., gt=0, description="ID của sách"),
    type: Optional[str] = Query(
        None, description="Loại chú thích (highlight, note, bookmark)"
    ),
    page: int = Query(1, ge=1, description="Số trang"),
    limit: int = Query(50, ge=1, le=200, description="Số lượng kết quả mỗi trang"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy tất cả chú thích của người dùng cho một cuốn sách cụ thể.

    Hữu ích khi cần tải tất cả chú thích cho hiển thị trên reader.
    """
    annotation_service = AnnotationService(db)

    try:
        # Tính toán skip từ page và limit
        skip = (page - 1) * limit

        annotations, total = await annotation_service.get_book_annotations(
            user_id=current_user.id, book_id=book_id, type=type, skip=skip, limit=limit
        )

        # Tính toán tổng số trang
        total_pages = (total + limit - 1) // limit if total > 0 else 0

        return {
            "items": annotations,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
        }
    except Exception as e:
        logger.error(f"Lỗi khi lấy chú thích của sách {book_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy chú thích của sách. Vui lòng thử lại sau.",
        )
