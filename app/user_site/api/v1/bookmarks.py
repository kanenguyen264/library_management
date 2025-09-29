from typing import Dict, Any, List, Optional, Tuple
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
from app.cache.decorators import cache_response as cache

from app.common.db.session import get_db
from app.user_site.api.deps import (
    get_current_active_user,
    get_current_user)
from app.user_site.api.v1 import throttle_requests
from app.user_site.models.user import User
from app.user_site.schemas.bookmark import (
    BookmarkCreate,
    BookmarkUpdate,
    BookmarkResponse,
    BookmarkListResponse,
    BookmarkSearchParams,
    BookmarkStatsResponse,
    BookmarkHistoryResponse,
)
from app.user_site.services.bookmark_service import BookmarkService
from app.logging.setup import get_logger
from app.monitoring.metrics import track_request_time
from app.security.audit.audit_trails import AuditLogger
from app.core.exceptions import (
    NotFoundException,
    ForbiddenException,
    BadRequestException,
    ServerException,
)

router = APIRouter()
logger = get_logger("bookmark_api")
audit_logger = AuditLogger()


@router.post("/", response_model=BookmarkResponse, status_code=status.HTTP_201_CREATED)
@track_request_time(endpoint="create_bookmark")
async def create_bookmark(
    data: BookmarkCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Tạo một bookmark mới.

    Người dùng có thể đánh dấu một vị trí cụ thể trong sách để dễ dàng quay lại sau này.
    Bookmark có thể chứa các thông tin như tiêu đề, ghi chú và vị trí trong sách.
    """
    bookmark_service = BookmarkService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Tạo bookmark mới - User: {current_user.id}, Book: {data.book_id}, IP: {client_ip}"
    )

    try:
        # Giới hạn tốc độ tạo bookmark
        await throttle_requests(
            "create_bookmark",
            limit=20,
            period=60,
            current_user=current_user,
            request=request,
            db=db,
        )

        # Kiểm tra sách/chương có tồn tại không
        if not await bookmark_service.validate_book_chapter(
            data.book_id, data.chapter_id
        ):
            raise BadRequestException(
                detail="Sách hoặc chương không tồn tại", code="invalid_book_chapter"
            )

        bookmark = await bookmark_service.create_bookmark(
            current_user.id, data.model_dump()
        )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "bookmark_create",
            f"Người dùng đã tạo bookmark mới cho sách {data.book_id}",
            metadata={"user_id": current_user.id, "book_id": data.book_id},
        )

        return bookmark
    except BadRequestException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi tạo bookmark: {str(e)}")
        raise ServerException(detail="Lỗi khi tạo bookmark")


@router.get("/", response_model=BookmarkListResponse)
@track_request_time(endpoint="list_bookmarks")
@cache(ttl=300, namespace="bookmarks")
async def list_bookmarks(
    book_id: Optional[int] = Query(None, gt=0, description="ID của sách"),
    chapter_id: Optional[int] = Query(None, gt=0, description="ID của chương"),
    is_favorite: Optional[bool] = Query(
        None, description="Lọc theo trạng thái yêu thích"
    ),
    page: int = Query(1, ge=1, description="Số trang"),
    limit: int = Query(20, ge=1, le=100, description="Số lượng kết quả mỗi trang"),
    sort_by: str = Query(
        "created_at",
        regex="^(created_at|updated_at|title|position)$",
        description="Sắp xếp theo trường",
    ),
    sort_desc: bool = Query(True, description="Sắp xếp giảm dần"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy danh sách bookmark của người dùng hiện tại với nhiều tùy chọn lọc và sắp xếp.

    - **book_id**: Lọc theo ID sách
    - **chapter_id**: Lọc theo ID chương
    - **is_favorite**: Lọc theo trạng thái yêu thích
    - **page**: Số trang
    - **limit**: Số lượng kết quả mỗi trang
    - **sort_by**: Sắp xếp theo trường (created_at, updated_at, title, position)
    - **sort_desc**: Sắp xếp giảm dần
    """
    bookmark_service = BookmarkService(db)

    try:
        # Tính toán skip từ page và limit
        skip = (page - 1) * limit

        # Tạo dict các tham số filter
        filters = {
            "user_id": current_user.id,
            "book_id": book_id,
            "chapter_id": chapter_id,
            "is_favorite": is_favorite,
            "skip": skip,
            "limit": limit,
            "sort_by": sort_by,
            "sort_desc": sort_desc,
        }

        bookmarks, total = await bookmark_service.list_bookmarks(**filters)

        # Tính toán tổng số trang
        total_pages = (total + limit - 1) // limit if total > 0 else 0

        return {
            "items": bookmarks,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
        }
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách bookmark: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy danh sách bookmark")


@router.get("/recent", response_model=List[BookmarkResponse])
@track_request_time(endpoint="get_recent_bookmarks")
@cache(ttl=300, namespace="recent_bookmarks")
async def get_recent_bookmarks(
    limit: int = Query(5, ge=1, le=20, description="Số lượng kết quả trả về"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy danh sách bookmark gần đây của người dùng.

    Trả về các bookmark được tạo hoặc truy cập gần đây nhất để tiếp tục đọc.
    """
    bookmark_service = BookmarkService(db)

    try:
        bookmarks = await bookmark_service.list_recent_bookmarks(
            user_id=current_user.id, limit=limit
        )

        return bookmarks
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách bookmark gần đây: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy danh sách bookmark gần đây")


@router.get("/{bookmark_id}", response_model=BookmarkResponse)
@track_request_time(endpoint="get_bookmark")
async def get_bookmark(
    bookmark_id: int = Path(..., gt=0, description="ID của bookmark"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy thông tin chi tiết của một bookmark.

    Trả về thông tin đầy đủ về bookmark bao gồm vị trí, ghi chú và thời gian tạo.
    """
    bookmark_service = BookmarkService(db)

    try:
        bookmark = await bookmark_service.get_bookmark_by_id(
            bookmark_id, current_user.id
        )

        if not bookmark:
            raise NotFoundException(
                detail=f"Không tìm thấy bookmark với ID: {bookmark_id}",
                code="bookmark_not_found",
            )

        # Cập nhật thời gian truy cập gần nhất
        await bookmark_service.update_last_accessed(bookmark_id)

        return bookmark
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin bookmark {bookmark_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy thông tin bookmark")


@router.put("/{bookmark_id}", response_model=BookmarkResponse)
@track_request_time(endpoint="update_bookmark")
async def update_bookmark(
    data: BookmarkUpdate,
    bookmark_id: int = Path(..., gt=0, description="ID của bookmark"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Cập nhật thông tin bookmark.

    Cho phép cập nhật tiêu đề, ghi chú, vị trí và trạng thái yêu thích của bookmark.
    """
    bookmark_service = BookmarkService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Cập nhật bookmark - ID: {bookmark_id}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra bookmark có tồn tại và thuộc về người dùng hiện tại không
        bookmark = await bookmark_service.get_bookmark_by_id(
            bookmark_id, current_user.id
        )

        if not bookmark:
            raise NotFoundException(
                detail=f"Không tìm thấy bookmark với ID: {bookmark_id}",
                code="bookmark_not_found",
            )

        updated_bookmark = await bookmark_service.update_bookmark(
            bookmark_id=bookmark_id,
            user_id=current_user.id,
            data=data.model_dump(exclude_unset=True),
        )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "bookmark_update",
            f"Người dùng đã cập nhật bookmark {bookmark_id}",
            metadata={"user_id": current_user.id, "bookmark_id": bookmark_id},
        )

        return updated_bookmark
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật bookmark {bookmark_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi cập nhật bookmark")


@router.delete("/{bookmark_id}", status_code=status.HTTP_204_NO_CONTENT)
@track_request_time(endpoint="delete_bookmark")
async def delete_bookmark(
    bookmark_id: int = Path(..., gt=0, description="ID của bookmark"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Xóa bookmark.

    Xóa vĩnh viễn một bookmark khỏi hệ thống.
    """
    bookmark_service = BookmarkService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Xóa bookmark - ID: {bookmark_id}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra bookmark có tồn tại và thuộc về người dùng hiện tại không
        bookmark = await bookmark_service.get_bookmark_by_id(
            bookmark_id, current_user.id
        )

        if not bookmark:
            raise NotFoundException(
                detail=f"Không tìm thấy bookmark với ID: {bookmark_id}",
                code="bookmark_not_found",
            )

        await bookmark_service.delete_bookmark(bookmark_id, current_user.id)

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "bookmark_delete",
            f"Người dùng đã xóa bookmark {bookmark_id}",
            metadata={"user_id": current_user.id, "bookmark_id": bookmark_id},
        )

        return None
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi xóa bookmark {bookmark_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi xóa bookmark")


@router.post("/chapter/{chapter_id}", response_model=BookmarkResponse)
@track_request_time(endpoint="create_or_update_chapter_bookmark")
async def create_or_update_chapter_bookmark(
    chapter_id: int = Path(..., gt=0, description="ID của chương"),
    data: BookmarkUpdate = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Tạo hoặc cập nhật bookmark cho một chương.

    Nếu bookmark cho chương đã tồn tại, sẽ cập nhật vị trí. Nếu chưa, sẽ tạo mới.
    Đây là endpoint tiện lợi để lưu tiến độ đọc.
    """
    bookmark_service = BookmarkService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Tạo/cập nhật bookmark chương - Chapter: {chapter_id}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra chương có tồn tại không
        if not await bookmark_service.chapter_exists(chapter_id):
            raise NotFoundException(
                detail=f"Không tìm thấy chương với ID: {chapter_id}",
                code="chapter_not_found",
            )

        bookmark = await bookmark_service.get_or_create_bookmark(
            user_id=current_user.id,
            chapter_id=chapter_id,
            data=data.model_dump(exclude_unset=True),
        )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "chapter_bookmark_update",
            f"Người dùng đã tạo/cập nhật bookmark cho chương {chapter_id}",
            metadata={"user_id": current_user.id, "chapter_id": chapter_id},
        )

        return bookmark
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi tạo/cập nhật bookmark cho chương {chapter_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi tạo/cập nhật bookmark cho chương")


@router.post("/search", response_model=BookmarkListResponse)
@track_request_time(endpoint="search_bookmarks")
async def search_bookmarks(
    search_params: BookmarkSearchParams,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Tìm kiếm nâng cao các bookmark với nhiều điều kiện lọc.

    Cho phép tìm kiếm theo tiêu đề, ghi chú, khoảng thời gian, và nhiều tiêu chí khác.
    """
    bookmark_service = BookmarkService(db)

    try:
        # Tính toán skip từ page và limit
        skip = (search_params.page - 1) * search_params.limit

        # Tạo dict tham số tìm kiếm
        search_dict = search_params.model_dump(exclude={"page", "limit"})
        search_dict["user_id"] = current_user.id
        search_dict["skip"] = skip
        search_dict["limit"] = search_params.limit

        bookmarks, total = await bookmark_service.search_bookmarks(**search_dict)

        # Tính toán tổng số trang
        total_pages = (
            (total + search_params.limit - 1) // search_params.limit if total > 0 else 0
        )

        return {
            "items": bookmarks,
            "total": total,
            "page": search_params.page,
            "limit": search_params.limit,
            "total_pages": total_pages,
        }
    except Exception as e:
        logger.error(f"Lỗi khi tìm kiếm bookmark: {str(e)}")
        raise ServerException(detail="Lỗi khi tìm kiếm bookmark")


@router.get("/stats", response_model=BookmarkStatsResponse)
@track_request_time(endpoint="get_bookmark_stats")
@cache(ttl=300, namespace="bookmark_stats")
async def get_bookmark_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy thống kê về bookmark của người dùng.

    Trả về tổng số bookmark, phân phối theo sách, thể loại, và thời gian.
    """
    bookmark_service = BookmarkService(db)

    try:
        stats = await bookmark_service.get_bookmark_stats(current_user.id)
        return stats
    except Exception as e:
        logger.error(f"Lỗi khi lấy thống kê bookmark: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy thống kê bookmark")


@router.get("/history", response_model=BookmarkHistoryResponse)
@track_request_time(endpoint="get_bookmark_history")
@cache(ttl=300, namespace="bookmark_history")
async def get_bookmark_history(
    days: int = Query(30, ge=1, le=365, description="Số ngày lấy lịch sử"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy lịch sử hoạt động bookmark của người dùng.

    Trả về thông tin về việc tạo và truy cập bookmark trong khoảng thời gian chỉ định.
    """
    bookmark_service = BookmarkService(db)

    try:
        history = await bookmark_service.get_bookmark_history(current_user.id, days)
        return history
    except Exception as e:
        logger.error(f"Lỗi khi lấy lịch sử bookmark: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy lịch sử bookmark")


@router.post("/favorites/toggle/{bookmark_id}", response_model=BookmarkResponse)
@track_request_time(endpoint="toggle_favorite_bookmark")
async def toggle_favorite_bookmark(
    bookmark_id: int = Path(..., gt=0, description="ID của bookmark"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Bật/tắt trạng thái yêu thích của một bookmark.

    Endpoint tiện lợi để đánh dấu hoặc bỏ đánh dấu một bookmark là yêu thích.
    """
    bookmark_service = BookmarkService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Đổi trạng thái yêu thích bookmark - ID: {bookmark_id}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra bookmark có tồn tại và thuộc về người dùng hiện tại không
        bookmark = await bookmark_service.get_bookmark_by_id(
            bookmark_id, current_user.id
        )

        if not bookmark:
            raise NotFoundException(
                detail=f"Không tìm thấy bookmark với ID: {bookmark_id}",
                code="bookmark_not_found",
            )

        updated_bookmark = await bookmark_service.toggle_favorite(
            bookmark_id, current_user.id
        )

        # Ghi nhật ký audit
        action = (
            "bookmark_add_favorite"
            if updated_bookmark.is_favorite
            else "bookmark_remove_favorite"
        )
        message = f"Người dùng đã {'thêm' if updated_bookmark.is_favorite else 'bỏ'} bookmark {bookmark_id} khỏi danh sách yêu thích"

        audit_logger.log_activity(
            current_user.id,
            action,
            message,
            metadata={"user_id": current_user.id, "bookmark_id": bookmark_id},
        )

        return updated_bookmark
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(
            f"Lỗi khi đổi trạng thái yêu thích bookmark {bookmark_id}: {str(e)}"
        )
        raise ServerException(detail="Lỗi khi đổi trạng thái yêu thích bookmark")


@router.delete("/bulk", status_code=status.HTTP_204_NO_CONTENT)
@track_request_time(endpoint="bulk_delete_bookmarks")
async def bulk_delete_bookmarks(
    bookmark_ids: List[int] = Body(..., description="Danh sách ID bookmark cần xóa"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Xóa hàng loạt các bookmark.

    Cho phép xóa nhiều bookmark cùng một lúc.
    """
    bookmark_service = BookmarkService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Xóa hàng loạt bookmark - User: {current_user.id}, Count: {len(bookmark_ids)}, IP: {client_ip}"
    )

    try:
        # Giới hạn số lượng bookmark có thể xóa cùng lúc
        if len(bookmark_ids) > 50:
            raise BadRequestException(
                detail="Không thể xóa quá 50 bookmark cùng lúc",
                code="too_many_bookmarks",
            )

        deleted_count = await bookmark_service.bulk_delete_bookmarks(
            current_user.id, bookmark_ids
        )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "bookmark_bulk_delete",
            f"Người dùng đã xóa hàng loạt {deleted_count} bookmark",
            metadata={"user_id": current_user.id, "deleted_count": deleted_count},
        )

        return None
    except BadRequestException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi xóa hàng loạt bookmark: {str(e)}")
        raise ServerException(detail="Lỗi khi xóa hàng loạt bookmark")


@router.get("/book/{book_id}/last", response_model=BookmarkResponse)
@track_request_time(endpoint="get_last_bookmark_for_book")
@cache(ttl=300, namespace="last_bookmark")
async def get_last_bookmark_for_book(
    book_id: int = Path(..., gt=0, description="ID của sách"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy bookmark gần nhất của người dùng cho một cuốn sách cụ thể.

    Hữu ích để tiếp tục đọc từ vị trí đã dừng lại.
    """
    bookmark_service = BookmarkService(db)

    try:
        # Kiểm tra sách có tồn tại không
        if not await bookmark_service.book_exists(book_id):
            raise NotFoundException(
                detail=f"Không tìm thấy sách với ID: {book_id}", code="book_not_found"
            )

        bookmark = await bookmark_service.get_last_bookmark_for_book(
            current_user.id, book_id
        )

        if not bookmark:
            raise NotFoundException(
                detail=f"Không tìm thấy bookmark cho sách với ID: {book_id}",
                code="bookmark_not_found",
            )

        # Cập nhật thời gian truy cập gần nhất
        await bookmark_service.update_last_accessed(bookmark.id)

        return bookmark
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy bookmark gần nhất cho sách {book_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy bookmark gần nhất cho sách")
