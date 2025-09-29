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

from app.common.db.session import get_db
from app.user_site.api.deps import (
    get_current_active_user,
    get_current_user)
from app.user_site.api.v1 import throttle_requests
from app.user_site.models.user import User
from app.user_site.schemas.book_list import (
    BookListResponse,
    BookListDetailResponse,
    BookListCreate,
    BookListUpdate,
    BookListListResponse,
    BookListItemCreate,
    BookListItemUpdate,
    BookListSearchParams,
)
from app.user_site.services.book_list_service import BookListService
from app.logging.setup import get_logger
from app.monitoring.metrics import track_request_time
from app.cache.decorators import cache_response, invalidate_cache
from app.security.audit.audit_trails import AuditLogger
from app.core.exceptions import (
    NotFoundException,
    ForbiddenException,
    BadRequestException,
    ServerException,
)

router = APIRouter()
logger = get_logger("book_list_api")
audit_logger = AuditLogger()


@router.post("/", response_model=BookListResponse, status_code=status.HTTP_201_CREATED)
@track_request_time(endpoint="create_book_list")
async def create_book_list(
    data: BookListCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Tạo một danh sách sách mới.

    Người dùng có thể tạo danh sách sách cá nhân hoặc công khai, với tiêu đề, mô tả
    và thiết lập quyền riêng tư.
    """
    book_list_service = BookListService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Tạo danh sách sách mới - User: {current_user.id}, Title: {data.title}, IP: {client_ip}"
    )

    try:
        # Giới hạn số lượng danh sách có thể tạo trong một khoảng thời gian
        await throttle_requests(
            "create_book_list",
            limit=10,
            period=3600,
            current_user=current_user,
            request=request,
            db=db,
        )

        book_list = await book_list_service.create_book_list(
            current_user.id, data.model_dump()
        )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "book_list_create",
            f"Người dùng đã tạo danh sách sách mới: {data.title}",
            metadata={"user_id": current_user.id, "list_title": data.title},
        )

        return book_list
    except Exception as e:
        logger.error(f"Lỗi khi tạo danh sách sách: {str(e)}")
        raise ServerException(detail="Lỗi khi tạo danh sách sách")


@router.get("/", response_model=BookListListResponse)
@track_request_time(endpoint="list_book_lists")
@cache_response(
    ttl=300,
    vary_by=[
        "user_id",
        "is_public",
        "page",
        "limit",
        "sort_by",
        "category",
        "current_user.id",
    ],
)
async def list_book_lists(
    user_id: Optional[int] = Query(None, gt=0, description="ID của người dùng"),
    is_public: Optional[bool] = Query(None, description="Chỉ lấy danh sách công khai"),
    category: Optional[str] = Query(None, description="Lọc theo danh mục"),
    tag: Optional[str] = Query(None, description="Lọc theo thẻ"),
    page: int = Query(1, ge=1, description="Số trang"),
    limit: int = Query(20, ge=1, le=100, description="Số lượng kết quả mỗi trang"),
    sort_by: str = Query(
        "created_at",
        regex="^(created_at|updated_at|title|books_count|likes_count)$",
        description="Sắp xếp theo trường",
    ),
    sort_desc: bool = Query(True, description="Sắp xếp giảm dần"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """
    Lấy danh sách các danh sách sách với nhiều tùy chọn lọc và sắp xếp.

    - **user_id**: Lọc theo ID người dùng tạo danh sách
    - **is_public**: Chỉ lấy danh sách công khai (true) hoặc riêng tư (false)
    - **category**: Lọc theo danh mục
    - **tag**: Lọc theo thẻ
    - **page**: Số trang
    - **limit**: Số lượng kết quả mỗi trang
    - **sort_by**: Sắp xếp theo trường (created_at, updated_at, title, books_count, likes_count)
    - **sort_desc**: Sắp xếp giảm dần
    """
    book_list_service = BookListService(db)

    try:
        # Tính toán skip từ page và limit
        skip = (page - 1) * limit

        # Nếu truy vấn danh sách của người dùng cụ thể
        if user_id:
            # Nếu là danh sách của người dùng hiện tại, hiển thị tất cả
            is_own_lists = current_user and current_user.id == user_id

            # Nếu không phải danh sách của người dùng hiện tại, chỉ hiển thị danh sách công khai
            if not is_own_lists:
                is_public = True

        filters = {
            "user_id": user_id,
            "is_public": is_public,
            "category": category,
            "tag": tag,
            "skip": skip,
            "limit": limit,
            "sort_by": sort_by,
            "sort_desc": sort_desc,
            "current_user_id": current_user.id if current_user else None,
        }

        book_lists, total = await book_list_service.list_book_lists(**filters)

        # Tính toán tổng số trang
        total_pages = (total + limit - 1) // limit if total > 0 else 0

        return {
            "items": book_lists,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
        }
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách book lists: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy danh sách book lists")


@router.get("/my-lists", response_model=BookListListResponse)
@track_request_time(endpoint="list_my_book_lists")
@cache_response(ttl=300, vary_by=["current_user.id", "page", "limit", "sort_by"])
async def list_my_book_lists(
    page: int = Query(1, ge=1, description="Số trang"),
    limit: int = Query(20, ge=1, le=100, description="Số lượng kết quả mỗi trang"),
    sort_by: str = Query(
        "updated_at",
        regex="^(created_at|updated_at|title|books_count)$",
        description="Sắp xếp theo trường",
    ),
    sort_desc: bool = Query(True, description="Sắp xếp giảm dần"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy danh sách các danh sách sách của người dùng hiện tại.

    - **page**: Số trang
    - **limit**: Số lượng kết quả mỗi trang
    - **sort_by**: Sắp xếp theo trường (created_at, updated_at, title, books_count)
    - **sort_desc**: Sắp xếp giảm dần
    """
    book_list_service = BookListService(db)

    try:
        # Tính toán skip từ page và limit
        skip = (page - 1) * limit

        book_lists, total = await book_list_service.list_book_lists(
            user_id=current_user.id,
            skip=skip,
            limit=limit,
            sort_by=sort_by,
            sort_desc=sort_desc,
            current_user_id=current_user.id,
        )

        # Tính toán tổng số trang
        total_pages = (total + limit - 1) // limit if total > 0 else 0

        return {
            "items": book_lists,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
        }
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy danh sách book lists của người dùng {current_user.id}: {str(e)}"
        )
        raise ServerException(detail="Lỗi khi lấy danh sách book lists của người dùng")


@router.get("/{list_id}", response_model=BookListDetailResponse)
@track_request_time(endpoint="get_book_list")
@cache_response(ttl=300, vary_by=["list_id", "current_user.id"])
async def get_book_list(
    list_id: int = Path(..., gt=0, description="ID của danh sách sách"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """
    Lấy thông tin chi tiết của một danh sách sách.

    Trả về thông tin đầy đủ về danh sách sách bao gồm tất cả các sách trong danh sách.
    Nếu danh sách là riêng tư, chỉ chủ sở hữu mới có thể xem.
    """
    book_list_service = BookListService(db)

    try:
        book_list = await book_list_service.get_book_list_by_id(
            list_id, current_user_id=current_user.id if current_user else None
        )

        if not book_list:
            raise NotFoundException(
                detail=f"Không tìm thấy danh sách sách với ID: {list_id}",
                code="book_list_not_found",
            )

        # Kiểm tra quyền truy cập nếu danh sách là riêng tư
        if not book_list.is_public and (
            not current_user or book_list.user_id != current_user.id
        ):
            raise ForbiddenException(
                detail="Bạn không có quyền xem danh sách sách này", code="access_denied"
            )

        return book_list
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin danh sách sách {list_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy thông tin danh sách sách")


@router.put("/{list_id}", response_model=BookListResponse)
@track_request_time(endpoint="update_book_list")
@invalidate_cache(namespace="book_lists", tags=["user_book_lists"])
async def update_book_list(
    data: BookListUpdate,
    list_id: int = Path(..., gt=0, description="ID của danh sách sách"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Cập nhật thông tin danh sách sách.

    Cho phép thay đổi tiêu đề, mô tả, thiết lập quyền riêng tư và các thông tin khác.
    Chỉ chủ sở hữu mới có quyền cập nhật.
    """
    book_list_service = BookListService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Cập nhật danh sách sách - ID: {list_id}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra danh sách sách có tồn tại và thuộc về người dùng hiện tại không
        book_list = await book_list_service.get_book_list_by_id(
            list_id, current_user.id
        )

        if not book_list:
            raise NotFoundException(
                detail=f"Không tìm thấy danh sách sách với ID: {list_id}",
                code="book_list_not_found",
            )

        # Kiểm tra quyền sở hữu
        if book_list.user_id != current_user.id:
            raise ForbiddenException(
                detail="Bạn không có quyền cập nhật danh sách sách này",
                code="not_owner",
            )

        updated_book_list = await book_list_service.update_book_list(
            list_id, current_user.id, data.model_dump(exclude_unset=True)
        )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "book_list_update",
            f"Người dùng đã cập nhật danh sách sách {list_id}",
            metadata={"user_id": current_user.id, "list_id": list_id},
        )

        return updated_book_list
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật danh sách sách {list_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi cập nhật danh sách sách")


@router.delete("/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
@track_request_time(endpoint="delete_book_list")
@invalidate_cache(namespace="book_lists", tags=["user_book_lists"])
async def delete_book_list(
    list_id: int = Path(..., gt=0, description="ID của danh sách sách"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Xóa danh sách sách.

    Chỉ chủ sở hữu mới có quyền xóa danh sách. Khi xóa danh sách, tất cả sách trong danh sách cũng sẽ bị xóa.
    """
    book_list_service = BookListService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Xóa danh sách sách - ID: {list_id}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra danh sách sách có tồn tại và thuộc về người dùng hiện tại không
        book_list = await book_list_service.get_book_list_by_id(
            list_id, current_user.id
        )

        if not book_list:
            raise NotFoundException(
                detail=f"Không tìm thấy danh sách sách với ID: {list_id}",
                code="book_list_not_found",
            )

        # Kiểm tra quyền sở hữu
        if book_list.user_id != current_user.id:
            raise ForbiddenException(
                detail="Bạn không có quyền xóa danh sách sách này", code="not_owner"
            )

        await book_list_service.delete_book_list(list_id, current_user.id)

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "book_list_delete",
            f"Người dùng đã xóa danh sách sách {list_id}",
            metadata={"user_id": current_user.id, "list_id": list_id},
        )

        return None
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi xóa danh sách sách {list_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi xóa danh sách sách")


@router.post("/{list_id}/books", response_model=BookListDetailResponse)
@track_request_time(endpoint="add_book_to_list")
@invalidate_cache(namespace="book_lists", tags=["book_list_items"])
async def add_book_to_list(
    data: BookListItemCreate,
    list_id: int = Path(..., gt=0, description="ID của danh sách sách"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Thêm sách vào danh sách.

    Cho phép thêm sách vào danh sách với một ghi chú tùy chọn và thứ tự sắp xếp.
    Chỉ chủ sở hữu mới có quyền thêm sách.
    """
    book_list_service = BookListService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Thêm sách vào danh sách - List ID: {list_id}, Book ID: {data.book_id}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra danh sách sách có tồn tại và thuộc về người dùng hiện tại không
        book_list = await book_list_service.get_book_list_by_id(
            list_id, current_user.id
        )

        if not book_list:
            raise NotFoundException(
                detail=f"Không tìm thấy danh sách sách với ID: {list_id}",
                code="book_list_not_found",
            )

        # Kiểm tra quyền sở hữu
        if book_list.user_id != current_user.id:
            raise ForbiddenException(
                detail="Bạn không có quyền thêm sách vào danh sách này",
                code="not_owner",
            )

        # Kiểm tra sách có tồn tại không
        if not await book_list_service.book_exists(data.book_id):
            raise NotFoundException(
                detail=f"Không tìm thấy sách với ID: {data.book_id}",
                code="book_not_found",
            )

        updated_list = await book_list_service.add_book_to_list(
            list_id, current_user.id, data.model_dump()
        )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "book_list_add_book",
            f"Người dùng đã thêm sách {data.book_id} vào danh sách {list_id}",
            metadata={
                "user_id": current_user.id,
                "list_id": list_id,
                "book_id": data.book_id,
            },
        )

        return updated_list
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi thêm sách vào danh sách {list_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi thêm sách vào danh sách")


@router.put("/{list_id}/books/{item_id}", response_model=BookListDetailResponse)
@track_request_time(endpoint="update_book_list_item")
@invalidate_cache(namespace="book_lists", tags=["book_list_items"])
async def update_book_list_item(
    data: BookListItemUpdate,
    list_id: int = Path(..., gt=0, description="ID của danh sách sách"),
    item_id: int = Path(..., gt=0, description="ID của mục trong danh sách"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Cập nhật thông tin sách trong danh sách.

    Cho phép cập nhật ghi chú và thứ tự sắp xếp của sách trong danh sách.
    Chỉ chủ sở hữu mới có quyền cập nhật.
    """
    book_list_service = BookListService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Cập nhật thông tin sách trong danh sách - List ID: {list_id}, Item ID: {item_id}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra danh sách sách có tồn tại và thuộc về người dùng hiện tại không
        book_list = await book_list_service.get_book_list_by_id(
            list_id, current_user.id
        )

        if not book_list:
            raise NotFoundException(
                detail=f"Không tìm thấy danh sách sách với ID: {list_id}",
                code="book_list_not_found",
            )

        # Kiểm tra quyền sở hữu
        if book_list.user_id != current_user.id:
            raise ForbiddenException(
                detail="Bạn không có quyền cập nhật danh sách sách này",
                code="not_owner",
            )

        updated_list = await book_list_service.update_book_list_item(
            list_id, item_id, current_user.id, data.model_dump(exclude_unset=True)
        )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "book_list_update_item",
            f"Người dùng đã cập nhật thông tin sách trong danh sách {list_id}",
            metadata={
                "user_id": current_user.id,
                "list_id": list_id,
                "item_id": item_id,
            },
        )

        return updated_list
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        logger.error(
            f"Lỗi khi cập nhật thông tin sách trong danh sách {list_id}: {str(e)}"
        )
        raise ServerException(detail="Lỗi khi cập nhật thông tin sách trong danh sách")


@router.delete("/{list_id}/books/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
@track_request_time(endpoint="remove_book_from_list")
@invalidate_cache(namespace="book_lists", tags=["book_list_items"])
async def remove_book_from_list(
    list_id: int = Path(..., gt=0, description="ID của danh sách sách"),
    item_id: int = Path(..., gt=0, description="ID của mục trong danh sách"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Xóa sách khỏi danh sách.

    Chỉ chủ sở hữu mới có quyền xóa sách khỏi danh sách.
    """
    book_list_service = BookListService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Xóa sách khỏi danh sách - List ID: {list_id}, Item ID: {item_id}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra danh sách sách có tồn tại và thuộc về người dùng hiện tại không
        book_list = await book_list_service.get_book_list_by_id(
            list_id, current_user.id
        )

        if not book_list:
            raise NotFoundException(
                detail=f"Không tìm thấy danh sách sách với ID: {list_id}",
                code="book_list_not_found",
            )

        # Kiểm tra quyền sở hữu
        if book_list.user_id != current_user.id:
            raise ForbiddenException(
                detail="Bạn không có quyền xóa sách khỏi danh sách này",
                code="not_owner",
            )

        await book_list_service.remove_book_from_list(list_id, item_id, current_user.id)

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "book_list_remove_book",
            f"Người dùng đã xóa sách khỏi danh sách {list_id}",
            metadata={
                "user_id": current_user.id,
                "list_id": list_id,
                "item_id": item_id,
            },
        )

        return None
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi xóa sách khỏi danh sách {list_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi xóa sách khỏi danh sách")


@router.post("/search", response_model=BookListListResponse)
@track_request_time(endpoint="search_book_lists")
async def search_book_lists(
    search_params: BookListSearchParams,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """
    Tìm kiếm nâng cao các danh sách sách với nhiều điều kiện lọc.

    Cho phép tìm kiếm theo từ khóa, thể loại, tác giả, số lượng sách, và nhiều tiêu chí khác.
    Danh sách riêng tư chỉ hiển thị cho chủ sở hữu.
    """
    book_list_service = BookListService(db)

    try:
        # Tính toán skip từ page và limit
        skip = (search_params.page - 1) * search_params.limit

        # Thêm current_user_id vào tham số tìm kiếm
        search_params_dict = search_params.model_dump(exclude={"page", "limit"})
        search_params_dict["skip"] = skip
        search_params_dict["limit"] = search_params.limit
        search_params_dict["current_user_id"] = (
            current_user.id if current_user else None
        )

        book_lists, total = await book_list_service.search_book_lists(
            **search_params_dict
        )

        # Tính toán tổng số trang
        total_pages = (
            (total + search_params.limit - 1) // search_params.limit if total > 0 else 0
        )

        return {
            "items": book_lists,
            "total": total,
            "page": search_params.page,
            "limit": search_params.limit,
            "total_pages": total_pages,
        }
    except Exception as e:
        logger.error(f"Lỗi khi tìm kiếm danh sách sách: {str(e)}")
        raise ServerException(detail="Lỗi khi tìm kiếm danh sách sách")


@router.post("/{list_id}/like", status_code=status.HTTP_200_OK)
@track_request_time(endpoint="like_book_list")
@invalidate_cache(namespace="book_lists", tags=["book_list_likes"])
async def like_book_list(
    list_id: int = Path(..., gt=0, description="ID của danh sách sách"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Thích một danh sách sách.

    Người dùng đã đăng nhập có thể thích các danh sách sách công khai.
    """
    book_list_service = BookListService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Thích danh sách sách - ID: {list_id}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra danh sách sách có tồn tại không
        book_list = await book_list_service.get_book_list_by_id(list_id)

        if not book_list:
            raise NotFoundException(
                detail=f"Không tìm thấy danh sách sách với ID: {list_id}",
                code="book_list_not_found",
            )

        # Kiểm tra danh sách có công khai không
        if not book_list.is_public:
            raise ForbiddenException(
                detail="Bạn không thể thích danh sách sách riêng tư",
                code="private_list",
            )

        result = await book_list_service.like_book_list(list_id, current_user.id)

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "book_list_like",
            f"Người dùng đã thích danh sách sách {list_id}",
            metadata={"user_id": current_user.id, "list_id": list_id},
        )

        return {
            "success": True,
            "is_new_like": result["is_new"],
            "likes_count": result["count"],
        }
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi thích danh sách sách {list_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi thích danh sách sách")


@router.delete("/{list_id}/like", status_code=status.HTTP_200_OK)
@track_request_time(endpoint="unlike_book_list")
@invalidate_cache(namespace="book_lists", tags=["book_list_likes"])
async def unlike_book_list(
    list_id: int = Path(..., gt=0, description="ID của danh sách sách"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Bỏ thích một danh sách sách.

    Người dùng có thể bỏ thích danh sách sách mà họ đã thích trước đó.
    """
    book_list_service = BookListService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Bỏ thích danh sách sách - ID: {list_id}, User: {current_user.id}, IP: {client_ip}"
    )

    try:
        # Kiểm tra danh sách sách có tồn tại không
        book_list = await book_list_service.get_book_list_by_id(list_id)

        if not book_list:
            raise NotFoundException(
                detail=f"Không tìm thấy danh sách sách với ID: {list_id}",
                code="book_list_not_found",
            )

        count = await book_list_service.unlike_book_list(list_id, current_user.id)

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "book_list_unlike",
            f"Người dùng đã bỏ thích danh sách sách {list_id}",
            metadata={"user_id": current_user.id, "list_id": list_id},
        )

        return {"success": True, "likes_count": count}
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi bỏ thích danh sách sách {list_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi bỏ thích danh sách sách")


@router.get("/popular", response_model=BookListListResponse)
@track_request_time(endpoint="get_popular_book_lists")
@cache_response(ttl=1800, vary_by=["category", "limit"])
async def get_popular_book_lists(
    category: Optional[str] = Query(None, description="Lọc theo danh mục"),
    limit: int = Query(10, ge=1, le=50, description="Số lượng kết quả trả về"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """
    Lấy danh sách các danh sách sách phổ biến.

    Trả về các danh sách sách công khai được yêu thích nhiều nhất, có thể lọc theo danh mục.
    """
    book_list_service = BookListService(db)

    try:
        book_lists, total = await book_list_service.get_popular_book_lists(
            category=category,
            limit=limit,
            current_user_id=current_user.id if current_user else None,
        )

        return {
            "items": book_lists,
            "total": total,
            "page": 1,
            "limit": limit,
            "total_pages": 1,
        }
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách sách phổ biến: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy danh sách sách phổ biến")


@router.get("/recommended", response_model=BookListListResponse)
@track_request_time(endpoint="get_recommended_book_lists")
@cache_response(ttl=1800, vary_by=["current_user.id", "limit"])
async def get_recommended_book_lists(
    limit: int = Query(10, ge=1, le=50, description="Số lượng kết quả trả về"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy danh sách các danh sách sách được đề xuất cho người dùng hiện tại.

    Đề xuất dựa trên sở thích, lịch sử đọc, và các tương tác trước đây của người dùng.
    """
    book_list_service = BookListService(db)

    try:
        book_lists, total = await book_list_service.get_recommended_book_lists(
            user_id=current_user.id, limit=limit
        )

        return {
            "items": book_lists,
            "total": total,
            "page": 1,
            "limit": limit,
            "total_pages": 1,
        }
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách sách đề xuất: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy danh sách sách đề xuất")


@router.get("/user/{user_id}", response_model=BookListListResponse)
@track_request_time(endpoint="list_user_public_book_lists")
@cache_response(ttl=600, vary_by=["user_id", "page", "limit", "current_user.id"])
async def list_user_public_book_lists(
    user_id: int = Path(..., gt=0, description="ID của người dùng"),
    page: int = Query(1, ge=1, description="Trang hiện tại"),
    limit: int = Query(20, ge=1, le=50, description="Số lượng kết quả mỗi trang"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """
    Lấy danh sách các danh sách sách công khai của một người dùng cụ thể.

    Người dùng có thể xem danh sách sách công khai của bất kỳ người dùng nào khác.
    """
    book_list_service = BookListService(db)

    try:
        # Kiểm tra người dùng có tồn tại không
        if not await book_list_service.user_exists(user_id):
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID: {user_id}",
                code="user_not_found",
            )

        # Tính toán skip từ page và limit
        skip = (page - 1) * limit

        # Nếu đang xem danh sách của chính mình, hiển thị tất cả
        is_own_profile = current_user and current_user.id == user_id
        is_public = None if is_own_profile else True

        book_lists, total = await book_list_service.list_book_lists(
            user_id=user_id,
            is_public=is_public,
            skip=skip,
            limit=limit,
            current_user_id=current_user.id if current_user else None,
        )

        # Tính toán tổng số trang
        total_pages = (total + limit - 1) // limit if total > 0 else 0

        return {
            "items": book_lists,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
        }
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy danh sách sách công khai của người dùng {user_id}: {str(e)}"
        )
        raise ServerException(
            detail="Lỗi khi lấy danh sách sách công khai của người dùng"
        )
