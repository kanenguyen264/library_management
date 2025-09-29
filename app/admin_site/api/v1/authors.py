from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    Query,
    Path,
    Body,
    Request,
)
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime

from app.common.db.session import get_db
from app.admin_site.api.deps import (
    get_current_admin,
    check_admin_permissions,
    secure_admin_access,
)
from app.admin_site.models import Admin
from app.user_site.schemas.author import (
    AuthorCreate,
    AuthorUpdate,
    AuthorResponse,
    AuthorDetailResponse,
    AuthorListResponse,
)
from app.user_site.schemas.book import BookBrief
from app.admin_site.services.author_service import (
    get_all_authors,
    count_authors,
    get_author_by_id,
    get_author_by_slug,
    create_author,
    update_author,
    delete_author,
    get_author_books,
    count_author_books,
    toggle_featured_status,
    update_book_count,
    get_featured_authors,
)
from app.security.audit.log_admin_action import log_admin_action
from app.cache.decorators import cached, invalidate_cache
from app.logging.setup import get_logger
from app.performance.profiling.api_profiler import profile_endpoint

logger = get_logger(__name__)
router = APIRouter()

# Danh sách endpoints:
# GET /api/v1/admin/authors - Lấy danh sách tác giả
# GET /api/v1/admin/authors/{id} - Lấy thông tin chi tiết tác giả
# GET /api/v1/admin/authors/slug/{slug} - Lấy thông tin chi tiết tác giả theo slug
# POST /api/v1/admin/authors - Tạo tác giả mới
# PUT /api/v1/admin/authors/{id} - Cập nhật thông tin tác giả
# DELETE /api/v1/admin/authors/{id} - Xóa tác giả
# PUT /api/v1/admin/authors/{id}/toggle-featured - Thay đổi trạng thái nổi bật
# GET /api/v1/admin/authors/{id}/books - Lấy danh sách sách của tác giả
# GET /api/v1/admin/authors/featured - Lấy danh sách tác giả nổi bật
# PUT /api/v1/admin/authors/{id}/update-book-count - Cập nhật số lượng sách của tác giả


@router.get("/", response_model=AuthorListResponse)
@profile_endpoint(name="admin:authors:list")
@cached(ttl=300, namespace="admin:authors", key_prefix="authors_list")
@log_admin_action(
    action="view", resource_type="author", description="Xem danh sách tác giả"
)
async def get_authors(
    page: int = Query(1, ge=1, description="Trang hiện tại"),
    size: int = Query(10, ge=1, le=100, description="Số lượng mỗi trang"),
    search: Optional[str] = Query(None, description="Tìm kiếm theo tên, tiểu sử"),
    country: Optional[str] = Query(None, description="Lọc theo quốc gia"),
    order_by: str = Query("name", description="Sắp xếp theo trường"),
    order_desc: bool = Query(False, description="Sắp xếp giảm dần"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["author:read"])),
    request: Request = None,
):
    """
    Lấy danh sách tác giả với các tùy chọn lọc và phân trang.

    - **page**: Trang hiện tại, bắt đầu từ 1
    - **size**: Số lượng mỗi trang
    - **search**: Tìm kiếm theo tên, tiểu sử
    - **country**: Lọc theo quốc gia
    - **order_by**: Sắp xếp theo trường
    - **order_desc**: Sắp xếp giảm dần
    """
    try:
        skip = (page - 1) * size

        authors = await get_all_authors(
            db=db,
            skip=skip,
            limit=size,
            search=search,
            country=country,
            order_by=order_by,
            order_desc=order_desc,
        )

        total = await count_authors(
            db=db,
            search=search,
            country=country,
        )

        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã lấy danh sách {len(authors)} tác giả"
        )

        return {
            "items": authors,
            "total": total,
        }
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách tác giả: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/statistics", response_model=Dict[str, Any])
@profile_endpoint(name="admin:authors:statistics")
@cached(ttl=600, namespace="admin:authors", key_prefix="author_statistics")
@log_admin_action(
    action="view", resource_type="author", description="Xem thống kê tác giả"
)
async def get_author_statistics(
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["author:read"])),
    request: Request = None,
):
    """
    Lấy thống kê về tác giả.
    """
    try:
        stats = await get_author_statistics(db=db)
        logger.info(f"Admin {admin.get('username', 'unknown')} đã xem thống kê tác giả")
        return stats
    except Exception as e:
        logger.error(f"Lỗi khi lấy thống kê tác giả: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/{author_id}", response_model=AuthorDetailResponse)
@profile_endpoint(name="admin:authors:detail")
@cached(ttl=300, namespace="admin:authors", key_prefix="author_detail")
@log_admin_action(action="view", resource_type="author", resource_id="{author_id}")
async def get_author_by_id(
    author_id: int = Path(..., ge=1, description="ID của tác giả"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["author:read"])),
    request: Request = None,
):
    """
    Lấy thông tin chi tiết của tác giả theo ID.

    - **author_id**: ID của tác giả
    """
    try:
        author = await get_author_by_id(db=db, author_id=author_id)
        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã xem thông tin tác giả ID={author_id}"
        )
        return author
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin tác giả ID={author_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/slug/{slug}", response_model=AuthorDetailResponse)
@profile_endpoint(name="admin:authors:detail_by_slug")
@cached(ttl=300, namespace="admin:authors", key_prefix="author_slug")
@log_admin_action(
    action="view", resource_type="author", description="Xem tác giả theo slug"
)
async def get_author_by_slug(
    slug: str = Path(..., description="Slug của tác giả"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["author:read"])),
    request: Request = None,
):
    """
    Lấy thông tin chi tiết của tác giả theo slug.

    - **slug**: Slug của tác giả
    """
    try:
        author = await get_author_by_slug(db=db, slug=slug)
        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã xem thông tin tác giả slug={slug}"
        )
        return author
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin tác giả slug={slug}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/{author_id}/books", response_model=List[BookBrief])
@profile_endpoint(name="admin:authors:books")
@cached(ttl=300, namespace="admin:authors", key_prefix="author_books")
@log_admin_action(
    action="view",
    resource_type="author",
    resource_id="{author_id}",
    description="Xem sách của tác giả",
)
async def get_author_books(
    author_id: int = Path(..., ge=1, description="ID của tác giả"),
    skip: int = Query(0, ge=0, description="Số lượng bản ghi bỏ qua"),
    limit: int = Query(10, ge=1, le=100, description="Số lượng bản ghi tối đa"),
    is_published: Optional[bool] = Query(
        None, description="Lọc theo trạng thái xuất bản"
    ),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["author:read"])),
    request: Request = None,
):
    """
    Lấy danh sách sách của tác giả.

    - **author_id**: ID của tác giả
    - **skip**: Số lượng bản ghi bỏ qua
    - **limit**: Số lượng bản ghi tối đa
    - **is_published**: Lọc theo trạng thái xuất bản
    """
    try:
        books = await get_author_books(
            db=db,
            author_id=author_id,
            skip=skip,
            limit=limit,
            is_published=is_published,
        )
        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã xem danh sách sách của tác giả ID={author_id}"
        )
        return books
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách sách của tác giả ID={author_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/{author_id}/books/count", response_model=int)
@profile_endpoint(name="admin:authors:books_count")
@cached(ttl=300, namespace="admin:authors", key_prefix="author_books_count")
@log_admin_action(
    action="view",
    resource_type="author",
    resource_id="{author_id}",
    description="Đếm số sách của tác giả",
)
async def count_author_books(
    author_id: int = Path(..., ge=1, description="ID của tác giả"),
    is_published: Optional[bool] = Query(
        None, description="Lọc theo trạng thái xuất bản"
    ),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["author:read"])),
    request: Request = None,
):
    """
    Đếm số lượng sách của tác giả.

    - **author_id**: ID của tác giả
    - **is_published**: Lọc theo trạng thái xuất bản
    """
    try:
        count = await count_author_books(
            db=db, author_id=author_id, is_published=is_published
        )
        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã đếm số lượng sách của tác giả ID={author_id}"
        )
        return count
    except Exception as e:
        logger.error(f"Lỗi khi đếm số lượng sách của tác giả ID={author_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post("/", response_model=AuthorResponse, status_code=status.HTTP_201_CREATED)
@profile_endpoint(name="admin:authors:create")
@invalidate_cache(namespace="admin:authors")
@log_admin_action(
    action="create", resource_type="author", description="Tạo tác giả mới"
)
async def create_author(
    author_data: AuthorCreate,
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["author:create"])),
    request: Request = None,
):
    """
    Tạo mới tác giả.
    """
    try:
        author = await create_author(db=db, author_data=author_data.model_dump())
        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã tạo tác giả mới: {author.name}"
        )
        return author
    except Exception as e:
        logger.error(f"Lỗi khi tạo tác giả mới: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.put("/{author_id}", response_model=AuthorResponse)
@profile_endpoint(name="admin:authors:update")
@invalidate_cache(namespace="admin:authors")
@log_admin_action(action="update", resource_type="author", resource_id="{author_id}")
async def update_author(
    author_id: int = Path(..., ge=1, description="ID của tác giả"),
    author_data: AuthorUpdate = Body(...),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["author:update"])),
    request: Request = None,
):
    """
    Cập nhật thông tin tác giả.

    - **author_id**: ID của tác giả
    """
    try:
        updated_author = await update_author(
            db=db,
            author_id=author_id,
            author_data=author_data.model_dump(exclude_unset=True),
        )
        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã cập nhật tác giả: {updated_author.name}"
        )
        return updated_author
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật tác giả ID={author_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.delete("/{author_id}", status_code=status.HTTP_204_NO_CONTENT)
@profile_endpoint(name="admin:authors:delete")
@invalidate_cache(namespace="admin:authors")
@log_admin_action(action="delete", resource_type="author", resource_id="{author_id}")
async def delete_author(
    author_id: int = Path(..., ge=1, description="ID của tác giả"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["author:delete"])),
    request: Request = None,
):
    """
    Xóa tác giả.

    - **author_id**: ID của tác giả
    """
    try:
        # Lấy thông tin tác giả trước khi xóa để ghi log
        author = await get_author_by_id(db=db, author_id=author_id)

        await delete_author(db=db, author_id=author_id)

        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã xóa tác giả: {author.name}"
        )
    except Exception as e:
        logger.error(f"Lỗi khi xóa tác giả ID={author_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.put("/{author_id}/book-count", response_model=AuthorResponse)
@profile_endpoint(name="admin:authors:update_book_count")
@invalidate_cache(namespace="admin:authors")
@log_admin_action(
    action="update",
    resource_type="author",
    resource_id="{author_id}",
    description="Cập nhật số lượng sách",
)
async def update_book_count(
    author_id: int = Path(..., ge=1, description="ID của tác giả"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["author:update"])),
    request: Request = None,
):
    """
    Cập nhật số lượng sách của tác giả.

    - **author_id**: ID của tác giả
    """
    try:
        updated_author = await update_book_count(db=db, author_id=author_id)

        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã cập nhật số lượng sách của tác giả: {updated_author.name}"
        )

        return updated_author
    except Exception as e:
        logger.error(
            f"Lỗi khi cập nhật số lượng sách của tác giả ID={author_id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
