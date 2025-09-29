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
from app.user_site.api.deps import get_current_user, get_current_active_user
from app.user_site.api.v1 import throttle_requests
from app.user_site.models.user import User
from app.user_site.schemas.bookshelf import (
    BookshelfCreate,
    BookshelfUpdate,
    BookshelfResponse,
    BookshelfDetailResponse,
    BookshelfItemCreate,
    BookshelfItemUpdate,
    BookshelfItemResponse,
)
from app.user_site.services.bookshelf_service import BookshelfService
from app.logging.setup import get_logger
from app.monitoring.metrics import track_request_time
from app.cache.decorators import cache_response, invalidate_cache
from app.security.audit.audit_trails import log_data_operation
from app.core.exceptions import (
    BadRequestException,
    UnauthorizedException,
    ForbiddenException,
    NotFoundException,
    ConflictException,
    ServerException,
)

router = APIRouter()
logger = get_logger("bookshelf_api")


@router.post("/", response_model=BookshelfResponse, status_code=status.HTTP_201_CREATED)
@track_request_time(endpoint="create_bookshelf")
@invalidate_cache(namespace="bookshelves", tags=["user_bookshelves"])
async def create_bookshelf(
    bookshelf_data: BookshelfCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """
    Tạo kệ sách mới.

    - **name**: Tên kệ sách
    - **description**: Mô tả kệ sách (tùy chọn)
    - **is_public**: Kệ sách có công khai không (mặc định: false)
    """
    # Giới hạn số lượng kệ sách tạo ra trong 1 giờ
    await throttle_requests(
        "create_bookshelf",
        limit=10,
        period=3600,
        request=request,
        current_user=current_user,
        db=db,
    )

    bookshelf_service = BookshelfService(db)
    client_ip = request.client.host if request else None
    user_agent = request.headers.get("User-Agent", "") if request else None

    try:
        # Kiểm tra xem tên kệ đã tồn tại chưa
        existing = await bookshelf_service.get_by_name_and_user(
            user_id=current_user.id, name=bookshelf_data.name
        )

        if existing:
            raise ConflictException(
                detail="Bạn đã có kệ sách với tên này",
                field="name",
                code="bookshelf_name_exists",
            )

        # Tạo kệ sách mới
        bookshelf = await bookshelf_service.create_bookshelf(
            user_id=current_user.id,
            name=bookshelf_data.name,
            description=bookshelf_data.description,
            is_public=bookshelf_data.is_public,
        )

        # Ghi log
        logger.info(f"Tạo kệ sách mới: {bookshelf.id}, user: {current_user.id}")

        # Ghi log audit
        if request:
            await log_data_operation(
                operation="create",
                resource_type="bookshelf",
                resource_id=str(bookshelf.id),
                user_id=str(current_user.id),
                user_type="user",
                status="success",
                ip_address=client_ip,
                user_agent=user_agent,
                changes={
                    "name": bookshelf_data.name,
                    "is_public": bookshelf_data.is_public,
                },
            )

        return bookshelf
    except ConflictException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi tạo kệ sách: {str(e)}")
        raise ServerException(detail="Lỗi khi tạo kệ sách mới")


@router.get("/", response_model=Dict[str, Any])
@track_request_time(endpoint="list_user_bookshelves")
@cache_response(ttl=300, vary_by=["current_user.id", "page", "page_size"])
async def list_user_bookshelves(
    page: int = Query(1, ge=1, description="Trang hiện tại"),
    page_size: int = Query(20, ge=1, le=50, description="Số lượng kệ sách mỗi trang"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách kệ sách của người dùng hiện tại.

    - **page**: Trang hiện tại
    - **page_size**: Số lượng kệ sách mỗi trang
    """
    bookshelf_service = BookshelfService(db)

    try:
        # Tính toán skip từ page và page_size
        skip = (page - 1) * page_size

        # Lấy danh sách kệ sách
        bookshelves, total = await bookshelf_service.list_user_bookshelves(
            user_id=current_user.id, skip=skip, limit=page_size
        )

        # Tính toán thông tin phân trang
        total_pages = (total + page_size - 1) // page_size  # Làm tròn lên

        return {
            "items": bookshelves,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy danh sách kệ sách của người dùng {current_user.id}: {str(e)}"
        )
        raise ServerException(detail="Lỗi khi lấy danh sách kệ sách")


@router.get("/public", response_model=Dict[str, Any])
@track_request_time(endpoint="list_public_bookshelves")
@cache_response(ttl=600, vary_by=["page", "page_size", "search"])
async def list_public_bookshelves(
    page: int = Query(1, ge=1, description="Trang hiện tại"),
    page_size: int = Query(20, ge=1, le=50, description="Số lượng kệ sách mỗi trang"),
    search: Optional[str] = Query(None, description="Tìm kiếm theo từ khóa"),
    order_by: str = Query(
        "created_at", regex="^(created_at|updated_at|name|book_count)$"
    ),
    order_desc: bool = Query(True, description="Sắp xếp giảm dần"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách kệ sách công khai.

    - **page**: Trang hiện tại
    - **page_size**: Số lượng kệ sách mỗi trang
    - **search**: Tìm kiếm theo từ khóa (tên, mô tả)
    - **order_by**: Sắp xếp theo trường (created_at, updated_at, name, book_count)
    - **order_desc**: Sắp xếp giảm dần (True) hoặc tăng dần (False)
    """
    bookshelf_service = BookshelfService(db)

    try:
        # Tính toán skip từ page và page_size
        skip = (page - 1) * page_size

        # Lấy danh sách kệ sách công khai
        bookshelves, total = await bookshelf_service.list_public_bookshelves(
            skip=skip,
            limit=page_size,
            search=search,
            order_by=order_by,
            order_desc=order_desc,
        )

        # Tính toán thông tin phân trang
        total_pages = (total + page_size - 1) // page_size  # Làm tròn lên

        return {
            "items": bookshelves,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách kệ sách công khai: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy danh sách kệ sách công khai")


@router.get("/{bookshelf_id}", response_model=BookshelfDetailResponse)
@track_request_time(endpoint="get_bookshelf")
@cache_response(ttl=300, vary_by=["bookshelf_id", "current_user.id"])
async def get_bookshelf(
    bookshelf_id: int = Path(..., description="ID của kệ sách"),
    current_user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy thông tin chi tiết của một kệ sách.

    - **bookshelf_id**: ID của kệ sách
    """
    bookshelf_service = BookshelfService(db)

    try:
        # Lấy thông tin kệ sách
        bookshelf = await bookshelf_service.get_bookshelf_by_id(bookshelf_id)

        if not bookshelf:
            raise NotFoundException(
                detail=f"Không tìm thấy kệ sách với ID: {bookshelf_id}",
                code="bookshelf_not_found",
            )

        # Kiểm tra quyền truy cập nếu kệ sách không công khai
        if not bookshelf.is_public and (
            not current_user or current_user.id != bookshelf.user_id
        ):
            raise ForbiddenException(
                detail="Kệ sách này không công khai", code="private_bookshelf"
            )

        return bookshelf
    except NotFoundException:
        raise
    except ForbiddenException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin kệ sách {bookshelf_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy thông tin kệ sách")


@router.put("/{bookshelf_id}", response_model=BookshelfResponse)
@track_request_time(endpoint="update_bookshelf")
@invalidate_cache(namespace="bookshelves", tags=["user_bookshelves"])
async def update_bookshelf(
    bookshelf_data: BookshelfUpdate,
    bookshelf_id: int = Path(..., description="ID của kệ sách"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """
    Cập nhật thông tin kệ sách.

    - **bookshelf_id**: ID của kệ sách
    - **name**: Tên kệ sách mới
    - **description**: Mô tả kệ sách mới
    - **is_public**: Cập nhật trạng thái công khai
    """
    bookshelf_service = BookshelfService(db)
    client_ip = request.client.host if request else None
    user_agent = request.headers.get("User-Agent", "") if request else None

    try:
        # Kiểm tra kệ sách có tồn tại không
        bookshelf = await bookshelf_service.get_bookshelf_by_id(bookshelf_id)

        if not bookshelf:
            raise NotFoundException(
                detail=f"Không tìm thấy kệ sách với ID: {bookshelf_id}",
                code="bookshelf_not_found",
            )

        # Kiểm tra quyền sở hữu
        if bookshelf.user_id != current_user.id:
            raise ForbiddenException(
                detail="Bạn không có quyền cập nhật kệ sách này", code="not_owner"
            )

        # Kiểm tra tên kệ sách mới có bị trùng không
        if bookshelf_data.name and bookshelf_data.name != bookshelf.name:
            existing = await bookshelf_service.get_by_name_and_user(
                user_id=current_user.id, name=bookshelf_data.name
            )

            if existing and existing.id != bookshelf_id:
                raise ConflictException(
                    detail="Bạn đã có kệ sách với tên này",
                    field="name",
                    code="bookshelf_name_exists",
                )

        # Cập nhật kệ sách
        update_data = bookshelf_data.model_dump(exclude_unset=True)
        updated_bookshelf = await bookshelf_service.update_bookshelf(
            bookshelf_id=bookshelf_id, update_data=update_data
        )

        # Ghi log
        logger.info(f"Cập nhật kệ sách: {bookshelf_id}, user: {current_user.id}")

        # Ghi log audit
        if request and update_data:
            await log_data_operation(
                operation="update",
                resource_type="bookshelf",
                resource_id=str(bookshelf_id),
                user_id=str(current_user.id),
                user_type="user",
                status="success",
                ip_address=client_ip,
                user_agent=user_agent,
                changes=update_data,
            )

        return updated_bookshelf
    except NotFoundException:
        raise
    except ForbiddenException:
        raise
    except ConflictException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật kệ sách {bookshelf_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi cập nhật kệ sách")


@router.delete("/{bookshelf_id}", status_code=status.HTTP_204_NO_CONTENT)
@track_request_time(endpoint="delete_bookshelf")
@invalidate_cache(namespace="bookshelves", tags=["user_bookshelves"])
async def delete_bookshelf(
    bookshelf_id: int = Path(..., description="ID của kệ sách"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """
    Xóa kệ sách.

    - **bookshelf_id**: ID của kệ sách cần xóa
    """
    bookshelf_service = BookshelfService(db)
    client_ip = request.client.host if request else None
    user_agent = request.headers.get("User-Agent", "") if request else None

    try:
        # Kiểm tra kệ sách có tồn tại không
        bookshelf = await bookshelf_service.get_bookshelf_by_id(bookshelf_id)

        if not bookshelf:
            raise NotFoundException(
                detail=f"Không tìm thấy kệ sách với ID: {bookshelf_id}",
                code="bookshelf_not_found",
            )

        # Kiểm tra quyền sở hữu
        if bookshelf.user_id != current_user.id:
            raise ForbiddenException(
                detail="Bạn không có quyền xóa kệ sách này", code="not_owner"
            )

        # Xóa kệ sách
        await bookshelf_service.delete_bookshelf(bookshelf_id)

        # Ghi log
        logger.info(f"Xóa kệ sách: {bookshelf_id}, user: {current_user.id}")

        # Ghi log audit
        if request:
            await log_data_operation(
                operation="delete",
                resource_type="bookshelf",
                resource_id=str(bookshelf_id),
                user_id=str(current_user.id),
                user_type="user",
                status="success",
                ip_address=client_ip,
                user_agent=user_agent,
            )

        return None
    except NotFoundException:
        raise
    except ForbiddenException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi xóa kệ sách {bookshelf_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi xóa kệ sách")


@router.post("/{bookshelf_id}/books", response_model=BookshelfItemResponse)
@track_request_time(endpoint="add_book_to_bookshelf")
@invalidate_cache(namespace="bookshelves", tags=["bookshelf_items"])
async def add_book_to_bookshelf(
    bookshelf_id: int,
    item_data: BookshelfItemCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """
    Thêm sách vào kệ sách.

    - **bookshelf_id**: ID của kệ sách
    - **book_id**: ID của sách cần thêm
    - **notes**: Ghi chú cho sách (tùy chọn)
    """
    bookshelf_service = BookshelfService(db)
    client_ip = request.client.host if request else None
    user_agent = request.headers.get("User-Agent", "") if request else None

    try:
        # Kiểm tra kệ sách có tồn tại không
        bookshelf = await bookshelf_service.get_bookshelf_by_id(bookshelf_id)

        if not bookshelf:
            raise NotFoundException(
                detail=f"Không tìm thấy kệ sách với ID: {bookshelf_id}",
                code="bookshelf_not_found",
            )

        # Kiểm tra quyền sở hữu
        if bookshelf.user_id != current_user.id:
            raise ForbiddenException(
                detail="Bạn không có quyền thêm sách vào kệ sách này", code="not_owner"
            )

        # Kiểm tra sách đã tồn tại trong kệ chưa
        existing_item = await bookshelf_service.get_bookshelf_item(
            bookshelf_id=bookshelf_id, book_id=item_data.book_id
        )

        if existing_item:
            raise ConflictException(
                detail="Sách này đã có trong kệ sách",
                field="book_id",
                code="book_already_exists",
            )

        # Thêm sách vào kệ
        item = await bookshelf_service.add_book_to_bookshelf(
            bookshelf_id=bookshelf_id, book_id=item_data.book_id, notes=item_data.notes
        )

        # Ghi log
        logger.info(f"Thêm sách {item_data.book_id} vào kệ sách {bookshelf_id}")

        # Ghi log audit
        if request:
            await log_data_operation(
                operation="add_book",
                resource_type="bookshelf_item",
                resource_id=f"{bookshelf_id}_{item_data.book_id}",
                user_id=str(current_user.id),
                user_type="user",
                status="success",
                ip_address=client_ip,
                user_agent=user_agent,
                changes={
                    "bookshelf_id": bookshelf_id,
                    "book_id": item_data.book_id,
                    "notes": item_data.notes,
                },
            )

        return item
    except NotFoundException:
        raise
    except ForbiddenException:
        raise
    except ConflictException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi thêm sách vào kệ sách: {str(e)}")
        raise ServerException(detail="Lỗi khi thêm sách vào kệ sách")


@router.delete(
    "/{bookshelf_id}/books/{book_id}", status_code=status.HTTP_204_NO_CONTENT
)
@track_request_time(endpoint="remove_book_from_bookshelf")
@invalidate_cache(namespace="bookshelves", tags=["bookshelf_items"])
async def remove_book_from_bookshelf(
    bookshelf_id: int,
    book_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """
    Xóa sách khỏi kệ sách.

    - **bookshelf_id**: ID của kệ sách
    - **book_id**: ID của sách cần xóa
    """
    bookshelf_service = BookshelfService(db)
    client_ip = request.client.host if request else None
    user_agent = request.headers.get("User-Agent", "") if request else None

    try:
        # Kiểm tra kệ sách có tồn tại không
        bookshelf = await bookshelf_service.get_bookshelf_by_id(bookshelf_id)

        if not bookshelf:
            raise NotFoundException(
                detail=f"Không tìm thấy kệ sách với ID: {bookshelf_id}",
                code="bookshelf_not_found",
            )

        # Kiểm tra quyền sở hữu
        if bookshelf.user_id != current_user.id:
            raise ForbiddenException(
                detail="Bạn không có quyền xóa sách khỏi kệ sách này", code="not_owner"
            )

        # Kiểm tra sách có trong kệ không
        item = await bookshelf_service.get_bookshelf_item(
            bookshelf_id=bookshelf_id, book_id=book_id
        )

        if not item:
            raise NotFoundException(
                detail="Sách này không có trong kệ sách", code="book_not_in_bookshelf"
            )

        # Xóa sách khỏi kệ
        await bookshelf_service.remove_book_from_bookshelf(
            bookshelf_id=bookshelf_id, book_id=book_id
        )

        # Ghi log
        logger.info(f"Xóa sách {book_id} khỏi kệ sách {bookshelf_id}")

        # Ghi log audit
        if request:
            await log_data_operation(
                operation="remove_book",
                resource_type="bookshelf_item",
                resource_id=f"{bookshelf_id}_{book_id}",
                user_id=str(current_user.id),
                user_type="user",
                status="success",
                ip_address=client_ip,
                user_agent=user_agent,
            )

        return None
    except NotFoundException:
        raise
    except ForbiddenException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi xóa sách khỏi kệ sách: {str(e)}")
        raise ServerException(detail="Lỗi khi xóa sách khỏi kệ sách")


@router.get("/{bookshelf_id}/books", response_model=Dict[str, Any])
@track_request_time(endpoint="list_bookshelf_books")
@cache_response(
    ttl=300, vary_by=["bookshelf_id", "page", "page_size", "current_user.id"]
)
async def list_bookshelf_books(
    bookshelf_id: int,
    page: int = Query(1, ge=1, description="Trang hiện tại"),
    page_size: int = Query(20, ge=1, le=50, description="Số lượng sách mỗi trang"),
    sort_by: str = Query("added_at", regex="^(added_at|title|author|rating)$"),
    sort_desc: bool = Query(True, description="Sắp xếp giảm dần"),
    current_user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách sách trong kệ sách.

    - **bookshelf_id**: ID của kệ sách
    - **page**: Trang hiện tại
    - **page_size**: Số lượng sách mỗi trang
    - **sort_by**: Sắp xếp theo trường (added_at, title, author, rating)
    - **sort_desc**: Sắp xếp giảm dần (True) hoặc tăng dần (False)
    """
    bookshelf_service = BookshelfService(db)

    try:
        # Kiểm tra kệ sách có tồn tại không
        bookshelf = await bookshelf_service.get_bookshelf_by_id(bookshelf_id)

        if not bookshelf:
            raise NotFoundException(
                detail=f"Không tìm thấy kệ sách với ID: {bookshelf_id}",
                code="bookshelf_not_found",
            )

        # Kiểm tra quyền truy cập nếu kệ sách không công khai
        if not bookshelf.is_public and (
            not current_user or current_user.id != bookshelf.user_id
        ):
            raise ForbiddenException(
                detail="Kệ sách này không công khai", code="private_bookshelf"
            )

        # Tính toán skip từ page và page_size
        skip = (page - 1) * page_size

        # Lấy danh sách sách
        books, total = await bookshelf_service.list_bookshelf_books(
            bookshelf_id=bookshelf_id,
            skip=skip,
            limit=page_size,
            sort_by=sort_by,
            sort_desc=sort_desc,
        )

        # Tính toán thông tin phân trang
        total_pages = (total + page_size - 1) // page_size  # Làm tròn lên

        return {
            "items": books,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "bookshelf": {
                "id": bookshelf.id,
                "name": bookshelf.name,
                "user_id": bookshelf.user_id,
            },
        }
    except NotFoundException:
        raise
    except ForbiddenException:
        raise
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy danh sách sách trong kệ sách {bookshelf_id}: {str(e)}"
        )
        raise ServerException(detail="Lỗi khi lấy danh sách sách trong kệ sách")


@router.put("/{bookshelf_id}/books/{item_id}", response_model=BookshelfItemResponse)
@track_request_time(endpoint="update_bookshelf_item")
@invalidate_cache(namespace="bookshelves", tags=["bookshelf_items"])
async def update_bookshelf_item(
    bookshelf_id: int,
    item_id: int,
    item_data: BookshelfItemUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """
    Cập nhật thông tin sách trong kệ sách.

    - **bookshelf_id**: ID của kệ sách
    - **item_id**: ID của mục trong kệ sách
    - **notes**: Ghi chú mới cho sách
    """
    bookshelf_service = BookshelfService(db)
    client_ip = request.client.host if request else None
    user_agent = request.headers.get("User-Agent", "") if request else None

    try:
        # Kiểm tra kệ sách có tồn tại không
        bookshelf = await bookshelf_service.get_bookshelf_by_id(bookshelf_id)

        if not bookshelf:
            raise NotFoundException(
                detail=f"Không tìm thấy kệ sách với ID: {bookshelf_id}",
                code="bookshelf_not_found",
            )

        # Kiểm tra quyền sở hữu
        if bookshelf.user_id != current_user.id:
            raise ForbiddenException(
                detail="Bạn không có quyền cập nhật sách trong kệ sách này",
                code="not_owner",
            )

        # Kiểm tra item có tồn tại không
        item = await bookshelf_service.get_bookshelf_item_by_id(item_id)

        if not item or item.bookshelf_id != bookshelf_id:
            raise NotFoundException(
                detail="Không tìm thấy mục trong kệ sách", code="item_not_found"
            )

        # Cập nhật item
        update_data = item_data.model_dump(exclude_unset=True)
        updated_item = await bookshelf_service.update_bookshelf_item(
            item_id=item_id, update_data=update_data
        )

        # Ghi log
        logger.info(f"Cập nhật mục {item_id} trong kệ sách {bookshelf_id}")

        # Ghi log audit
        if request and update_data:
            await log_data_operation(
                operation="update_book",
                resource_type="bookshelf_item",
                resource_id=str(item_id),
                user_id=str(current_user.id),
                user_type="user",
                status="success",
                ip_address=client_ip,
                user_agent=user_agent,
                changes=update_data,
            )

        return updated_item
    except NotFoundException:
        raise
    except ForbiddenException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật mục trong kệ sách: {str(e)}")
        raise ServerException(detail="Lỗi khi cập nhật mục trong kệ sách")


@router.get("/user/{user_id}", response_model=Dict[str, Any])
@track_request_time(endpoint="list_user_public_bookshelves")
@cache_response(ttl=600, vary_by=["user_id", "page", "page_size"])
async def list_user_public_bookshelves(
    user_id: int = Path(..., gt=0),
    page: int = Query(1, ge=1, description="Trang hiện tại"),
    page_size: int = Query(20, ge=1, le=50, description="Số lượng kệ sách mỗi trang"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách kệ sách công khai của một người dùng.

    - **user_id**: ID của người dùng
    - **page**: Trang hiện tại
    - **page_size**: Số lượng kệ sách mỗi trang
    """
    bookshelf_service = BookshelfService(db)

    try:
        # Tính toán skip từ page và page_size
        skip = (page - 1) * page_size

        # Lấy danh sách kệ sách công khai
        bookshelves, total = await bookshelf_service.list_public_bookshelves_by_user(
            user_id=user_id, skip=skip, limit=page_size
        )

        # Tính toán thông tin phân trang
        total_pages = (total + page_size - 1) // page_size  # Làm tròn lên

        return {
            "items": bookshelves,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "user_id": user_id,
        }
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy danh sách kệ sách công khai của người dùng {user_id}: {str(e)}"
        )
        raise ServerException(detail="Lỗi khi lấy danh sách kệ sách")
