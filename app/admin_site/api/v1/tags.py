from typing import List, Optional, Dict, Any
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    Path,
    Query,
    Body,
    Request,
)
from sqlalchemy.orm import Session
import logging

from app.user_site.models.tag import Tag
from app.user_site.schemas.tag import (
    TagCreate,
    TagUpdate,
    TagInfo,
    TagResponse,
    TagList,
)
from app.user_site.schemas.book import BookInfo
from app.admin_site.services import tag_service
from app.cache.decorators import cached, invalidate_cache
from app.common.db.session import get_db
from app.admin_site.api.deps import secure_admin_access
from app.security.audit.log_admin_action import log_admin_action
from app.performance.profiling.api_profiler import profile_endpoint
from app.logging.setup import get_logger
from app.common.exceptions import (
    NotFoundException,
    ResourceConflictException,
    BadRequestException,
)

# Tạo router
router = APIRouter()
logger = get_logger(__name__)

# Danh sách endpoints:
# GET /                 - Lấy danh sách tags
# GET /statistics       - Lấy thống kê tags
# GET /popular          - Lấy danh sách tags phổ biến
# GET /{tag_id}         - Lấy thông tin chi tiết tag theo ID
# GET /slug/{slug}      - Lấy thông tin chi tiết tag theo slug
# GET /{tag_id}/books   - Lấy danh sách sách theo tag
# GET /{tag_id}/books/count - Đếm số lượng sách theo tag
# POST /                - Tạo tag mới
# PUT /{tag_id}         - Cập nhật thông tin tag
# DELETE /{tag_id}      - Xóa tag
# PUT /{tag_id}/active  - Thay đổi trạng thái hoạt động của tag
# PUT /{tag_id}/book-count - Cập nhật số lượng sách của tag
# GET /search           - Tìm kiếm tag
# POST /book/{book_id}/tag/{tag_id} - Thêm tag cho sách
# DELETE /book/{book_id}/tag/{tag_id} - Xóa tag khỏi sách
# GET /book/{book_id}/tags - Lấy danh sách tag của sách


@router.get("/", response_model=TagList)
@profile_endpoint(name="admin:tags:list")
@cached(ttl=300, namespace="admin:tags", key_prefix="tags_list")
@log_admin_action(action="view", resource_type="tag", description="Xem danh sách thẻ")
async def get_tags(
    page: int = Query(1, ge=1, description="Trang hiện tại"),
    size: int = Query(10, ge=1, le=100, description="Số lượng mỗi trang"),
    search: Optional[str] = Query(None, description="Tìm kiếm theo tên, mô tả"),
    is_active: Optional[bool] = Query(
        None, description="Lọc theo trạng thái hoạt động"
    ),
    order_by: str = Query("name", description="Sắp xếp theo trường"),
    order_desc: bool = Query(False, description="Sắp xếp giảm dần"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["tag:read"])),
    request: Request = None,
):
    """
    Lấy danh sách thẻ với các tùy chọn lọc và phân trang.

    - **page**: Trang hiện tại, bắt đầu từ 1
    - **size**: Số lượng mỗi trang
    - **search**: Tìm kiếm theo tên, mô tả
    - **is_active**: Lọc theo trạng thái hoạt động
    - **order_by**: Sắp xếp theo trường
    - **order_desc**: Sắp xếp giảm dần
    """
    try:
        skip = (page - 1) * size

        tags = await tag_service.get_all_tags(
            db=db,
            skip=skip,
            limit=size,
            search=search,
            is_active=is_active,
            order_by=order_by,
            order_desc=order_desc,
        )

        total = await tag_service.count_tags(
            db=db,
            search=search,
            is_active=is_active,
        )

        pages = (total + size - 1) // size if size > 0 else 0

        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã lấy danh sách {len(tags)} thẻ"
        )

        return {
            "items": tags,
            "total": total,
            "page": page,
            "size": size,
            "pages": pages,
        }
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách thẻ: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/statistics", response_model=Dict[str, Any])
@profile_endpoint(name="admin:tags:statistics")
@cached(ttl=600, namespace="admin:tags", key_prefix="tag_statistics")
@log_admin_action(action="view", resource_type="tag", description="Xem thống kê thẻ")
async def get_tag_statistics(
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["tag:read"])),
    request: Request = None,
):
    """
    Lấy thống kê về thẻ.
    """
    try:
        stats = await tag_service.get_tag_statistics(db=db)
        logger.info(f"Admin {admin.get('username', 'unknown')} đã xem thống kê thẻ")
        return stats
    except Exception as e:
        logger.error(f"Lỗi khi lấy thống kê thẻ: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/popular", response_model=List[TagInfo])
@profile_endpoint(name="admin:tags:popular")
@cached(ttl=300, namespace="admin:tags", key_prefix="popular_tags")
@log_admin_action(action="view", resource_type="tag", description="Xem thẻ phổ biến")
async def get_popular_tags(
    limit: int = Query(10, ge=1, le=50, description="Số lượng thẻ tối đa"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["tag:read"])),
    request: Request = None,
):
    """
    Lấy danh sách thẻ phổ biến.

    - **limit**: Số lượng thẻ tối đa trả về
    """
    try:
        tags = await tag_service.get_popular_tags(db=db, limit=limit)
        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã xem {len(tags)} thẻ phổ biến"
        )
        return tags
    except Exception as e:
        logger.error(f"Lỗi khi lấy thẻ phổ biến: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/{tag_id}", response_model=TagInfo)
@profile_endpoint(name="admin:tags:detail")
@cached(ttl=300, namespace="admin:tags", key_prefix="tag_detail")
@log_admin_action(action="view", resource_type="tag", resource_id="{tag_id}")
async def get_tag_by_id(
    tag_id: int = Path(..., ge=1, description="ID của thẻ"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["tag:read"])),
    request: Request = None,
):
    """
    Lấy thông tin chi tiết của thẻ theo ID.

    - **tag_id**: ID của thẻ
    """
    try:
        tag = await tag_service.get_tag_by_id(
            db=db, tag_id=tag_id, admin_id=admin.get("id")
        )
        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã xem thông tin thẻ ID={tag_id}"
        )
        return tag
    except NotFoundException as e:
        logger.warning(
            f"Admin {admin.get('username', 'unknown')} cố gắng truy cập thẻ không tồn tại ID={tag_id}"
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin thẻ ID={tag_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/slug/{slug}", response_model=TagInfo)
@profile_endpoint(name="admin:tags:detail_by_slug")
@cached(ttl=300, namespace="admin:tags", key_prefix="tag_slug")
@log_admin_action(action="view", resource_type="tag", description="Xem thẻ theo slug")
async def get_tag_by_slug(
    slug: str = Path(..., description="Slug của thẻ"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["tag:read"])),
    request: Request = None,
):
    """
    Lấy thông tin chi tiết của thẻ theo slug.

    - **slug**: Slug của thẻ
    """
    try:
        tag = await tag_service.get_tag_by_slug(db=db, slug=slug)
        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã xem thông tin thẻ slug={slug}"
        )
        return tag
    except NotFoundException as e:
        logger.warning(
            f"Admin {admin.get('username', 'unknown')} cố gắng truy cập thẻ không tồn tại slug={slug}"
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin thẻ slug={slug}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/{tag_id}/books", response_model=List[BookInfo])
@profile_endpoint(name="admin:tags:books")
@cached(ttl=300, namespace="admin:tags", key_prefix="tag_books")
@log_admin_action(
    action="view",
    resource_type="tag",
    resource_id="{tag_id}",
    description="Xem sách được gắn thẻ",
)
async def get_tag_books(
    tag_id: int = Path(..., ge=1, description="ID của thẻ"),
    skip: int = Query(0, ge=0, description="Số lượng bản ghi bỏ qua"),
    limit: int = Query(10, ge=1, le=100, description="Số lượng bản ghi tối đa"),
    is_published: Optional[bool] = Query(
        None, description="Lọc theo trạng thái xuất bản"
    ),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["tag:read"])),
    request: Request = None,
):
    """
    Lấy danh sách sách được gắn thẻ.

    - **tag_id**: ID của thẻ
    - **skip**: Số lượng bản ghi bỏ qua
    - **limit**: Số lượng bản ghi tối đa
    - **is_published**: Lọc theo trạng thái xuất bản
    """
    try:
        books = await tag_service.get_tag_books(
            db=db,
            tag_id=tag_id,
            skip=skip,
            limit=limit,
            is_published=is_published,
        )
        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã xem danh sách sách với thẻ ID={tag_id}"
        )
        return books
    except NotFoundException as e:
        logger.warning(
            f"Admin {admin.get('username', 'unknown')} cố gắng xem sách của thẻ không tồn tại ID={tag_id}"
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách sách với thẻ ID={tag_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/{tag_id}/books/count", response_model=int)
@profile_endpoint(name="admin:tags:books_count")
@cached(ttl=300, namespace="admin:tags", key_prefix="tag_books_count")
@log_admin_action(
    action="view",
    resource_type="tag",
    resource_id="{tag_id}",
    description="Đếm số sách được gắn thẻ",
)
async def count_tag_books(
    tag_id: int = Path(..., ge=1, description="ID của thẻ"),
    is_published: Optional[bool] = Query(
        None, description="Lọc theo trạng thái xuất bản"
    ),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["tag:read"])),
    request: Request = None,
):
    """
    Đếm số lượng sách được gắn thẻ.

    - **tag_id**: ID của thẻ
    - **is_published**: Lọc theo trạng thái xuất bản
    """
    try:
        count = await tag_service.count_tag_books(
            db=db, tag_id=tag_id, is_published=is_published
        )
        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã đếm số lượng sách với thẻ ID={tag_id}"
        )
        return count
    except NotFoundException as e:
        logger.warning(
            f"Admin {admin.get('username', 'unknown')} cố gắng đếm sách của thẻ không tồn tại ID={tag_id}"
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Lỗi khi đếm số lượng sách với thẻ ID={tag_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post("/", response_model=TagInfo, status_code=status.HTTP_201_CREATED)
@profile_endpoint(name="admin:tags:create")
@invalidate_cache(namespace="admin:tags")
@log_admin_action(action="create", resource_type="tag", description="Tạo thẻ mới")
async def create_tag(
    tag: TagCreate,
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["tag:create"])),
    request: Request = None,
):
    """
    Tạo mới thẻ.
    """
    try:
        new_tag = await tag_service.create_tag(
            db=db, tag_data=tag.model_dump(), admin_id=admin.get("id")
        )
        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã tạo thẻ mới: {new_tag.name}"
        )
        return new_tag
    except ResourceConflictException as e:
        logger.warning(
            f"Admin {admin.get('username', 'unknown')} cố gắng tạo thẻ bị xung đột: {str(e)}"
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        logger.error(f"Lỗi khi tạo thẻ mới: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.put("/{tag_id}", response_model=TagInfo)
@profile_endpoint(name="admin:tags:update")
@invalidate_cache(namespace="admin:tags")
@log_admin_action(action="update", resource_type="tag", resource_id="{tag_id}")
async def update_tag(
    tag_id: int = Path(..., ge=1, description="ID của thẻ"),
    tag: TagUpdate = Body(...),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["tag:update"])),
    request: Request = None,
):
    """
    Cập nhật thông tin thẻ.

    - **tag_id**: ID của thẻ
    """
    try:
        updated_tag = await tag_service.update_tag(
            db=db,
            tag_id=tag_id,
            tag_data=tag.model_dump(exclude_unset=True),
            admin_id=admin.get("id"),
        )
        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã cập nhật thẻ: {updated_tag.name}"
        )
        return updated_tag
    except NotFoundException as e:
        logger.warning(
            f"Admin {admin.get('username', 'unknown')} cố gắng cập nhật thẻ không tồn tại ID={tag_id}"
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ResourceConflictException as e:
        logger.warning(
            f"Admin {admin.get('username', 'unknown')} cố gắng cập nhật thẻ bị xung đột: {str(e)}"
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật thẻ ID={tag_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
@profile_endpoint(name="admin:tags:delete")
@invalidate_cache(namespace="admin:tags")
@log_admin_action(action="delete", resource_type="tag", resource_id="{tag_id}")
async def delete_tag(
    tag_id: int = Path(..., ge=1, description="ID của thẻ"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["tag:delete"])),
    request: Request = None,
):
    """
    Xóa thẻ.

    - **tag_id**: ID của thẻ
    """
    try:
        # Lấy thông tin thẻ trước khi xóa để ghi log
        tag = await tag_service.get_tag_by_id(db=db, tag_id=tag_id)

        await tag_service.delete_tag(db=db, tag_id=tag_id, admin_id=admin.get("id"))

        logger.info(f"Admin {admin.get('username', 'unknown')} đã xóa thẻ: {tag.name}")
    except NotFoundException as e:
        logger.warning(
            f"Admin {admin.get('username', 'unknown')} cố gắng xóa thẻ không tồn tại ID={tag_id}"
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except BadRequestException as e:
        logger.warning(
            f"Admin {admin.get('username', 'unknown')} gửi yêu cầu không hợp lệ khi xóa thẻ: {str(e)}"
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Lỗi khi xóa thẻ ID={tag_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.put("/{tag_id}/active", response_model=TagInfo)
@profile_endpoint(name="admin:tags:toggle_active")
@invalidate_cache(namespace="admin:tags")
@log_admin_action(
    action="update",
    resource_type="tag",
    resource_id="{tag_id}",
    description="Thay đổi trạng thái hoạt động",
)
async def toggle_tag_active_status(
    tag_id: int = Path(..., ge=1, description="ID của thẻ"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["tag:update"])),
    request: Request = None,
):
    """
    Chuyển đổi trạng thái hoạt động của thẻ.

    - **tag_id**: ID của thẻ
    """
    try:
        updated_tag = await tag_service.toggle_tag_active_status(db=db, tag_id=tag_id)

        status_text = "kích hoạt" if updated_tag.is_active else "vô hiệu hóa"
        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã {status_text} thẻ: {updated_tag.name}"
        )

        return updated_tag
    except NotFoundException as e:
        logger.warning(
            f"Admin {admin.get('username', 'unknown')} cố gắng thay đổi trạng thái thẻ không tồn tại ID={tag_id}"
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(
            f"Lỗi khi thay đổi trạng thái hoạt động của thẻ ID={tag_id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.put("/{tag_id}/book-count", response_model=TagInfo)
@profile_endpoint(name="admin:tags:update_book_count")
@invalidate_cache(namespace="admin:tags")
@log_admin_action(
    action="update",
    resource_type="tag",
    resource_id="{tag_id}",
    description="Cập nhật số lượng sách",
)
async def update_book_count(
    tag_id: int = Path(..., ge=1, description="ID của thẻ"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["tag:update"])),
    request: Request = None,
):
    """
    Cập nhật số lượng sách được gắn thẻ.

    - **tag_id**: ID của thẻ
    """
    try:
        updated_tag = await tag_service.update_book_count(db=db, tag_id=tag_id)

        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã cập nhật số lượng sách với thẻ: {updated_tag.name}"
        )

        return updated_tag
    except NotFoundException as e:
        logger.warning(
            f"Admin {admin.get('username', 'unknown')} cố gắng cập nhật số lượng sách của thẻ không tồn tại ID={tag_id}"
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật số lượng sách với thẻ ID={tag_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/search", response_model=List[TagInfo])
@profile_endpoint(name="admin:tags:search")
@cached(ttl=60, namespace="admin:tags", key_prefix="tag_search")
@log_admin_action(action="search", resource_type="tag", description="Tìm kiếm thẻ")
async def search_tags(
    query: str = Query(..., min_length=1, description="Từ khóa tìm kiếm"),
    limit: int = Query(10, ge=1, le=50, description="Số lượng kết quả tối đa"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["tag:read"])),
    request: Request = None,
):
    """
    Tìm kiếm thẻ theo từ khóa.

    - **query**: Từ khóa tìm kiếm
    - **limit**: Số lượng kết quả tối đa
    """
    try:
        tags = await tag_service.search_tags(db=db, query=query, limit=limit)
        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã tìm kiếm thẻ với từ khóa '{query}'"
        )
        return tags
    except Exception as e:
        logger.error(f"Lỗi khi tìm kiếm thẻ: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post("/book/{book_id}/tag/{tag_id}", status_code=status.HTTP_201_CREATED)
@profile_endpoint(name="admin:tags:add_to_book")
@invalidate_cache(namespace="admin:tags")
@log_admin_action(
    action="create",
    resource_type="book_tag",
    resource_id="{book_id}",
    description="Thêm thẻ cho sách",
)
async def add_tag_to_book(
    book_id: int = Path(..., ge=1, description="ID của sách"),
    tag_id: int = Path(..., ge=1, description="ID của thẻ"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["tag:create", "book:update"])),
    request: Request = None,
):
    """
    Thêm thẻ cho sách.

    - **book_id**: ID của sách
    - **tag_id**: ID của thẻ
    """
    try:
        result = await tag_service.add_book_tag(
            db=db, book_id=book_id, tag_id=tag_id, admin_id=admin.get("id")
        )
        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã thêm thẻ ID={tag_id} cho sách ID={book_id}"
        )
        return {"success": True, "message": "Đã thêm thẻ cho sách thành công"}
    except Exception as e:
        logger.error(f"Lỗi khi thêm thẻ cho sách: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.delete("/book/{book_id}/tag/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
@profile_endpoint(name="admin:tags:remove_from_book")
@invalidate_cache(namespace="admin:tags")
@log_admin_action(
    action="delete",
    resource_type="book_tag",
    resource_id="{book_id}",
    description="Xóa thẻ khỏi sách",
)
async def remove_tag_from_book(
    book_id: int = Path(..., ge=1, description="ID của sách"),
    tag_id: int = Path(..., ge=1, description="ID của thẻ"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["tag:delete", "book:update"])),
    request: Request = None,
):
    """
    Xóa thẻ khỏi sách.

    - **book_id**: ID của sách
    - **tag_id**: ID của thẻ
    """
    try:
        await tag_service.remove_book_tag(
            db=db, book_id=book_id, tag_id=tag_id, admin_id=admin.get("id")
        )
        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã xóa thẻ ID={tag_id} khỏi sách ID={book_id}"
        )
    except Exception as e:
        logger.error(f"Lỗi khi xóa thẻ khỏi sách: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/book/{book_id}/tags", response_model=List[TagInfo])
@profile_endpoint(name="admin:tags:get_book_tags")
@cached(ttl=300, namespace="admin:tags", key_prefix="book_tags")
@log_admin_action(
    action="view",
    resource_type="book_tags",
    resource_id="{book_id}",
    description="Xem thẻ của sách",
)
async def get_book_tags(
    book_id: int = Path(..., ge=1, description="ID của sách"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["tag:read", "book:read"])),
    request: Request = None,
):
    """
    Lấy danh sách thẻ của sách.

    - **book_id**: ID của sách
    """
    try:
        tags = await tag_service.get_tags_by_book(db=db, book_id=book_id)
        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã xem danh sách thẻ của sách ID={book_id}"
        )
        return tags
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách thẻ của sách ID={book_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
