from typing import List, Optional, Dict, Any
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Path,
    status,
    Body,
    Request,
)
from sqlalchemy.orm import Session
from datetime import datetime, date

from app.common.db.session import get_db
from app.user_site.schemas.book import (
    BookCreateRequest as BookCreate,
    BookAdminUpdate as BookUpdate,
    BookDetailResponse as BookInfo,
    BookListResponse as BookList,
    BookStatistics,
    ChapterInfo,
    BookResponse,
    AuthorBrief as AuthorInfo,
    CategoryBrief as CategoryInfo,
    TagBrief as TagInfo,
)
from app.admin_site.services import book_service
from app.admin_site.api.deps import secure_admin_access
from app.security.audit.log_admin_action import log_admin_action
from app.performance.profiling.api_profiler import profile_endpoint
from app.core.exceptions import (
    NotFoundException,
    ConflictException,
    BadRequestException,
)
from app.cache.decorators import cached
from app.logging.setup import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.get("/", response_model=BookList)
@profile_endpoint(name="admin:books:list")
@cached(ttl=300, namespace="admin:books", key_prefix="books_list")
async def get_books(
    page: int = Query(1, ge=1, description="Trang hiện tại"),
    size: int = Query(10, ge=1, le=100, description="Số lượng mỗi trang"),
    search: Optional[str] = Query(
        None, description="Tìm kiếm theo tiêu đề, mô tả, tác giả..."
    ),
    category_id: Optional[int] = Query(None, description="Lọc theo ID danh mục"),
    author_id: Optional[int] = Query(None, description="Lọc theo ID tác giả"),
    tag_id: Optional[int] = Query(None, description="Lọc theo ID tag"),
    is_published: Optional[bool] = Query(
        None, description="Lọc theo trạng thái xuất bản"
    ),
    is_featured: Optional[bool] = Query(
        None, description="Lọc theo trạng thái nổi bật"
    ),
    order_by: str = Query("created_at", description="Sắp xếp theo trường"),
    order_desc: bool = Query(True, description="Sắp xếp giảm dần"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["books:read"])),
    request: Request = None,
):
    """
    Lấy danh sách sách với các tùy chọn lọc và phân trang.

    - **page**: Trang hiện tại, bắt đầu từ 1
    - **size**: Số lượng mỗi trang
    - **search**: Tìm kiếm theo tiêu đề, mô tả, tác giả...
    - **category_id**: Lọc theo ID danh mục
    - **author_id**: Lọc theo ID tác giả
    - **tag_id**: Lọc theo ID tag
    - **is_published**: Lọc theo trạng thái xuất bản
    - **is_featured**: Lọc theo trạng thái nổi bật
    - **order_by**: Sắp xếp theo trường
    - **order_desc**: Sắp xếp giảm dần
    """
    try:
        skip = (page - 1) * size

        books = await book_service.get_all_books(
            db=db,
            skip=skip,
            limit=size,
            search=search,
            category_id=category_id,
            author_id=author_id,
            tag_id=tag_id,
            is_published=is_published,
            is_featured=is_featured,
            order_by=order_by,
            order_desc=order_desc,
        )

        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã xem danh sách sách (trang {page}, số lượng {size})"
        )

        return books
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách sách: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi lấy danh sách sách: " + str(e),
        )


@router.get("/statistics", response_model=BookStatistics)
@profile_endpoint(name="admin:books:statistics")
@cached(ttl=600, namespace="admin:books", key_prefix="books_statistics")
async def get_book_statistics(
    start_date: Optional[date] = Query(None, description="Ngày bắt đầu thống kê"),
    end_date: Optional[date] = Query(None, description="Ngày kết thúc thống kê"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["books:read", "statistics:read"])),
    request: Request = None,
):
    """
    Lấy thống kê tổng quan về sách.

    - **start_date**: Ngày bắt đầu thống kê (không chỉ định sẽ lấy từ đầu)
    - **end_date**: Ngày kết thúc thống kê (không chỉ định sẽ lấy đến hiện tại)
    """
    try:
        stats = await book_service.get_book_statistics(db, start_date, end_date)

        logger.info(f"Admin {admin.get('username', 'unknown')} đã xem thống kê sách")

        return stats
    except Exception as e:
        logger.error(f"Lỗi khi lấy thống kê sách: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi lấy thống kê sách: " + str(e),
        )


@router.get("/{book_id}", response_model=BookInfo)
@profile_endpoint(name="admin:books:detail")
@cached(ttl=300, namespace="admin:books", key_prefix="book_detail")
async def get_book_detail(
    book_id: int = Path(..., description="ID của sách cần lấy thông tin"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["books:read"])),
    request: Request = None,
):
    """
    Lấy thông tin chi tiết của một sách theo ID.

    - **book_id**: ID của sách cần lấy thông tin
    """
    try:
        book = await book_service.get_book_by_id(db, book_id)

        if not book:
            logger.warning(
                f"Admin {admin.get('username', 'unknown')} tìm kiếm sách không tồn tại với ID: {book_id}"
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Không tìm thấy sách với ID: {book_id}",
            )

        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã xem chi tiết sách ID: {book_id}"
        )

        return book
    except NotFoundException as e:
        logger.warning(f"Không tìm thấy sách: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Lỗi khi lấy chi tiết sách: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi lấy chi tiết sách: " + str(e),
        )


@router.post("/", response_model=BookInfo, status_code=status.HTTP_201_CREATED)
@profile_endpoint(name="admin:books:create")
@log_admin_action(action="create", resource_type="book", description="Tạo sách mới")
async def create_book(
    book_data: BookCreate,
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["books:create"])),
    request: Request = None,
):
    """
    Tạo một sách mới.

    - **book_data**: Dữ liệu sách cần tạo
    """
    try:
        book = await book_service.create_book(db, book_data)

        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã tạo sách mới: {book.title} (ID: {book.id})"
        )

        return book
    except ConflictException as e:
        logger.warning(f"Xung đột tài nguyên khi tạo sách: {str(e)}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except BadRequestException as e:
        logger.warning(f"Dữ liệu không hợp lệ khi tạo sách: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Lỗi khi tạo sách mới: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi tạo sách mới: " + str(e),
        )


@router.put("/{book_id}", response_model=BookInfo)
@profile_endpoint(name="admin:books:update")
@log_admin_action(
    action="update", resource_type="book", description="Cập nhật thông tin sách"
)
async def update_book(
    book_id: int = Path(..., description="ID của sách cần cập nhật"),
    book_data: BookUpdate = Body(..., description="Dữ liệu cập nhật"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["books:update"])),
    request: Request = None,
):
    """
    Cập nhật thông tin của một sách.

    - **book_id**: ID của sách cần cập nhật
    - **book_data**: Dữ liệu cập nhật
    """
    try:
        book = await book_service.update_book(db, book_id, book_data)

        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã cập nhật sách ID: {book_id}"
        )

        return book
    except NotFoundException as e:
        logger.warning(f"Không tìm thấy sách khi cập nhật: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ConflictException as e:
        logger.warning(f"Xung đột tài nguyên khi cập nhật sách: {str(e)}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except BadRequestException as e:
        logger.warning(f"Dữ liệu không hợp lệ khi cập nhật sách: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật sách: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi cập nhật sách: " + str(e),
        )


@router.delete("/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
@profile_endpoint(name="admin:books:delete")
@log_admin_action(action="delete", resource_type="book", description="Xóa sách")
async def delete_book(
    book_id: int = Path(..., description="ID của sách cần xóa"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["books:delete"])),
    request: Request = None,
):
    """
    Xóa một sách.

    - **book_id**: ID của sách cần xóa
    """
    try:
        await book_service.delete_book(db, book_id)

        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã xóa sách ID: {book_id}"
        )

        return None
    except NotFoundException as e:
        logger.warning(f"Không tìm thấy sách khi xóa: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Lỗi khi xóa sách: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi xóa sách: " + str(e),
        )


@router.put("/{book_id}/publish", response_model=BookInfo)
@profile_endpoint(name="admin:books:publish")
@log_admin_action(
    action="publish", resource_type="book", description="Xuất bản/hủy xuất bản sách"
)
async def toggle_book_publish_status(
    book_id: int = Path(..., description="ID của sách cần thay đổi trạng thái"),
    is_published: bool = Body(..., embed=True, description="Trạng thái xuất bản mới"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["books:publish"])),
    request: Request = None,
):
    """
    Thay đổi trạng thái xuất bản của sách.

    - **book_id**: ID của sách cần thay đổi trạng thái
    - **is_published**: Trạng thái xuất bản mới (true/false)
    """
    try:
        book = await book_service.toggle_book_publish_status(db, book_id, is_published)

        action = "xuất bản" if is_published else "hủy xuất bản"
        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã {action} sách ID: {book_id}"
        )

        return book
    except NotFoundException as e:
        logger.warning(
            f"Không tìm thấy sách khi thay đổi trạng thái xuất bản: {str(e)}"
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Lỗi khi thay đổi trạng thái xuất bản sách: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi thay đổi trạng thái xuất bản sách: " + str(e),
        )


@router.put("/{book_id}/feature", response_model=BookInfo)
@profile_endpoint(name="admin:books:feature")
@log_admin_action(
    action="feature", resource_type="book", description="Đánh dấu/hủy đánh dấu nổi bật"
)
async def toggle_book_feature_status(
    book_id: int = Path(..., description="ID của sách cần thay đổi trạng thái"),
    is_featured: bool = Body(..., embed=True, description="Trạng thái nổi bật mới"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["books:update"])),
    request: Request = None,
):
    """
    Thay đổi trạng thái nổi bật của sách.

    - **book_id**: ID của sách cần thay đổi trạng thái
    - **is_featured**: Trạng thái nổi bật mới (true/false)
    """
    try:
        book = await book_service.toggle_book_feature_status(db, book_id, is_featured)

        action = "đánh dấu nổi bật" if is_featured else "hủy đánh dấu nổi bật"
        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã {action} sách ID: {book_id}"
        )

        return book
    except NotFoundException as e:
        logger.warning(f"Không tìm thấy sách khi thay đổi trạng thái nổi bật: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Lỗi khi thay đổi trạng thái nổi bật sách: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi thay đổi trạng thái nổi bật sách: " + str(e),
        )


@router.get("/{book_id}/chapters", response_model=List[ChapterInfo])
@profile_endpoint(name="admin:books:chapters")
@cached(ttl=300, namespace="admin:books", key_prefix="book_chapters")
async def get_book_chapters(
    book_id: int = Path(..., description="ID của sách cần lấy danh sách chương"),
    is_published: Optional[bool] = Query(
        None, description="Lọc theo trạng thái xuất bản"
    ),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["books:read", "chapters:read"])),
    request: Request = None,
):
    """
    Lấy danh sách các chương của một sách.

    - **book_id**: ID của sách cần lấy danh sách chương
    - **is_published**: Lọc theo trạng thái xuất bản
    """
    try:
        chapters = await book_service.get_book_chapters(db, book_id, is_published)

        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã xem danh sách chương của sách ID: {book_id}"
        )

        return chapters
    except NotFoundException as e:
        logger.warning(f"Không tìm thấy sách khi lấy danh sách chương: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách chương của sách: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi lấy danh sách chương của sách: " + str(e),
        )
