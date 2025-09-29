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

from app.common.db.session import get_db
from app.user_site.schemas.category import (
    CategoryCreate,
    CategoryUpdate,
    CategoryInfo,
    CategoryListResponse as CategoryList,
    CategoryTree,
    CategoryStatistics,
)
from app.user_site.schemas.book import BookResponse as BookInfo
from app.admin_site.services import category_service
from app.admin_site.api.deps import secure_admin_access
from app.core.exceptions import (
    NotFoundException,
    ConflictException,
    BadRequestException,
)
from app.security.audit.log_admin_action import log_admin_action
from app.cache.decorators import cached, invalidate_cache
from app.performance.profiling.api_profiler import profile_endpoint
from app.logging.setup import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.get("/", response_model=CategoryList)
@profile_endpoint(name="admin:categories:list")
@cached(key_prefix="admin_categories_list", ttl=300)
@log_admin_action(
    action="view", resource_type="category", description="Xem danh sách danh mục"
)
async def get_categories(
    page: int = Query(1, ge=1, description="Trang hiện tại"),
    size: int = Query(10, ge=1, le=100, description="Số lượng mỗi trang"),
    search: Optional[str] = Query(None, description="Tìm kiếm theo tên, mô tả"),
    parent_id: Optional[int] = Query(None, description="Lọc theo ID danh mục cha"),
    is_active: Optional[bool] = Query(
        None, description="Lọc theo trạng thái hoạt động"
    ),
    is_featured: Optional[bool] = Query(
        None, description="Lọc theo trạng thái nổi bật"
    ),
    order_by: str = Query("display_order", description="Sắp xếp theo trường"),
    order_desc: bool = Query(False, description="Sắp xếp giảm dần"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["category:read"])),
    request: Request = None,
):
    """
    Lấy danh sách danh mục với các tùy chọn lọc và phân trang.

    - **page**: Trang hiện tại, bắt đầu từ 1
    - **size**: Số lượng mỗi trang
    - **search**: Tìm kiếm theo tên, mô tả
    - **parent_id**: Lọc theo ID danh mục cha
    - **is_active**: Lọc theo trạng thái hoạt động
    - **is_featured**: Lọc theo trạng thái nổi bật
    - **order_by**: Sắp xếp theo trường
    - **order_desc**: Sắp xếp giảm dần
    """
    skip = (page - 1) * size

    try:
        categories = await category_service.get_all_categories(
            db=db,
            skip=skip,
            limit=size,
            search=search,
            parent_id=parent_id,
            is_active=is_active,
            is_featured=is_featured,
            order_by=order_by,
            order_desc=order_desc,
        )

        total = await category_service.count_categories(
            db=db,
            search=search,
            parent_id=parent_id,
            is_active=is_active,
            is_featured=is_featured,
        )

        pages = (total + size - 1) // size if size > 0 else 0

        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã lấy danh sách {len(categories)} danh mục"
        )

        return {
            "items": categories,
            "total": total,
            "page": page,
            "size": size,
            "pages": pages,
        }
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách danh mục: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/tree", response_model=CategoryTree)
@profile_endpoint(name="admin:categories:tree")
@cached(key_prefix="admin_category_tree", ttl=600)
@log_admin_action(
    action="view", resource_type="category", description="Xem cây danh mục"
)
async def get_category_tree(
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["category:read"])),
    request: Request = None,
):
    """
    Lấy cây danh mục.
    """
    try:
        tree = await category_service.get_category_tree(db=db)
        total = await category_service.count_categories(db=db)

        logger.info(f"Admin {admin.get('username', 'unknown')} đã xem cây danh mục")

        return {"items": list(tree.values()), "total": total}
    except Exception as e:
        logger.error(f"Lỗi khi lấy cây danh mục: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/root", response_model=List[CategoryInfo])
@profile_endpoint(name="admin:categories:root")
@cached(key_prefix="admin_root_categories", ttl=600)
@log_admin_action(
    action="view", resource_type="category", description="Xem danh mục gốc"
)
async def get_root_categories(
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["category:read"])),
    request: Request = None,
):
    """
    Lấy danh sách danh mục gốc.
    """
    try:
        categories = await category_service.get_root_categories(db=db)
        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã xem danh sách danh mục gốc"
        )
        return categories
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách danh mục gốc: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/statistics", response_model=CategoryStatistics)
@profile_endpoint(name="admin:categories:statistics")
@cached(key_prefix="admin_category_statistics", ttl=600)
@log_admin_action(
    action="view", resource_type="category", description="Xem thống kê danh mục"
)
async def get_category_statistics(
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["category:read"])),
    request: Request = None,
):
    """
    Lấy thống kê về danh mục.
    """
    try:
        stats = await category_service.get_category_statistics(db=db)
        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã xem thống kê danh mục"
        )
        return stats
    except Exception as e:
        logger.error(f"Lỗi khi lấy thống kê danh mục: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/featured", response_model=List[CategoryInfo])
@profile_endpoint(name="admin:categories:featured")
@cached(key_prefix="admin_featured_categories", ttl=600)
@log_admin_action(
    action="view", resource_type="category", description="Xem danh mục nổi bật"
)
async def get_featured_categories(
    limit: int = Query(10, ge=1, le=50, description="Số lượng tối đa"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["category:read"])),
    request: Request = None,
):
    """
    Lấy danh sách danh mục nổi bật.

    - **limit**: Số lượng danh mục nổi bật tối đa
    """
    try:
        categories = await category_service.get_featured_categories(db=db, limit=limit)
        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã xem danh sách danh mục nổi bật"
        )
        return categories
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách danh mục nổi bật: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/{category_id}", response_model=CategoryInfo)
@profile_endpoint(name="admin:categories:detail")
@cached(key_prefix="admin_category_detail", ttl=300)
@log_admin_action(action="view", resource_type="category", resource_id="{category_id}")
async def get_category_by_id(
    category_id: int = Path(..., ge=1, description="ID của danh mục"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["category:read"])),
    request: Request = None,
):
    """
    Lấy thông tin chi tiết của danh mục theo ID.

    - **category_id**: ID của danh mục
    """
    try:
        category = await category_service.get_category_by_id(
            db=db, category_id=category_id
        )
        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã xem thông tin danh mục ID={category_id}"
        )
        return category
    except NotFoundException as e:
        logger.warning(
            f"Admin {admin.get('username', 'unknown')} cố gắng truy cập danh mục không tồn tại ID={category_id}"
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin danh mục ID={category_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/slug/{slug}", response_model=CategoryInfo)
@profile_endpoint(name="admin:categories:detail_by_slug")
@cached(key_prefix="admin_category_slug", ttl=300)
@log_admin_action(
    action="view", resource_type="category", description="Xem danh mục theo slug"
)
async def get_category_by_slug(
    slug: str = Path(..., description="Slug của danh mục"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["category:read"])),
    request: Request = None,
):
    """
    Lấy thông tin chi tiết của danh mục theo slug.

    - **slug**: Slug của danh mục
    """
    try:
        category = await category_service.get_category_by_slug(db=db, slug=slug)
        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã xem thông tin danh mục slug={slug}"
        )
        return category
    except NotFoundException as e:
        logger.warning(
            f"Admin {admin.get('username', 'unknown')} cố gắng truy cập danh mục không tồn tại slug={slug}"
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin danh mục slug={slug}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/{category_id}/children", response_model=List[CategoryInfo])
@profile_endpoint(name="admin:categories:children")
@cached(key_prefix="admin_category_children", ttl=300)
@log_admin_action(
    action="view",
    resource_type="category",
    resource_id="{category_id}",
    description="Xem danh mục con",
)
async def get_category_children(
    category_id: int = Path(..., ge=1, description="ID của danh mục"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["category:read"])),
    request: Request = None,
):
    """
    Lấy danh sách danh mục con.

    - **category_id**: ID của danh mục cha
    """
    try:
        categories = await category_service.get_category_children(
            db=db, category_id=category_id
        )
        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã xem danh sách danh mục con của danh mục ID={category_id}"
        )
        return categories
    except NotFoundException as e:
        logger.warning(
            f"Admin {admin.get('username', 'unknown')} cố gắng xem danh mục con của danh mục không tồn tại ID={category_id}"
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy danh sách danh mục con của danh mục ID={category_id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/{category_id}/parent", response_model=Optional[CategoryInfo])
@profile_endpoint(name="admin:categories:parent")
@cached(key_prefix="admin_category_parent", ttl=300)
@log_admin_action(
    action="view",
    resource_type="category",
    resource_id="{category_id}",
    description="Xem danh mục cha",
)
async def get_category_parent(
    category_id: int = Path(..., ge=1, description="ID của danh mục"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["category:read"])),
    request: Request = None,
):
    """
    Lấy danh mục cha.

    - **category_id**: ID của danh mục
    """
    try:
        parent = await category_service.get_category_parent(
            db=db, category_id=category_id
        )
        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã xem danh mục cha của danh mục ID={category_id}"
        )
        return parent
    except NotFoundException as e:
        logger.warning(
            f"Admin {admin.get('username', 'unknown')} cố gắng xem danh mục cha của danh mục không tồn tại ID={category_id}"
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy danh mục cha của danh mục ID={category_id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/{category_id}/books", response_model=List[BookInfo])
@profile_endpoint(name="admin:categories:books")
@cached(key_prefix="admin_category_books", ttl=300)
@log_admin_action(
    action="view",
    resource_type="category",
    resource_id="{category_id}",
    description="Xem sách trong danh mục",
)
async def get_category_books(
    category_id: int = Path(..., ge=1, description="ID của danh mục"),
    skip: int = Query(0, ge=0, description="Số lượng bản ghi bỏ qua"),
    limit: int = Query(10, ge=1, le=100, description="Số lượng bản ghi tối đa"),
    is_published: Optional[bool] = Query(
        None, description="Lọc theo trạng thái xuất bản"
    ),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["category:read"])),
    request: Request = None,
):
    """
    Lấy danh sách sách thuộc danh mục.

    - **category_id**: ID của danh mục
    - **skip**: Số lượng bản ghi bỏ qua
    - **limit**: Số lượng bản ghi tối đa
    - **is_published**: Lọc theo trạng thái xuất bản
    """
    try:
        books = await category_service.get_category_books(
            db=db,
            category_id=category_id,
            skip=skip,
            limit=limit,
            is_published=is_published,
        )
        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã xem danh sách sách thuộc danh mục ID={category_id}"
        )
        return books
    except NotFoundException as e:
        logger.warning(
            f"Admin {admin.get('username', 'unknown')} cố gắng xem sách của danh mục không tồn tại ID={category_id}"
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy danh sách sách thuộc danh mục ID={category_id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/{category_id}/books/count", response_model=int)
@profile_endpoint(name="admin:categories:books_count")
@cached(key_prefix="admin_category_books_count", ttl=300)
@log_admin_action(
    action="view",
    resource_type="category",
    resource_id="{category_id}",
    description="Đếm số sách trong danh mục",
)
async def count_category_books(
    category_id: int = Path(..., ge=1, description="ID của danh mục"),
    is_published: Optional[bool] = Query(
        None, description="Lọc theo trạng thái xuất bản"
    ),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["category:read"])),
    request: Request = None,
):
    """
    Đếm số lượng sách thuộc danh mục.

    - **category_id**: ID của danh mục
    - **is_published**: Lọc theo trạng thái xuất bản
    """
    try:
        count = await category_service.count_category_books(
            db=db, category_id=category_id, is_published=is_published
        )
        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã đếm số lượng sách thuộc danh mục ID={category_id}"
        )
        return count
    except NotFoundException as e:
        logger.warning(
            f"Admin {admin.get('username', 'unknown')} cố gắng đếm sách của danh mục không tồn tại ID={category_id}"
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(
            f"Lỗi khi đếm số lượng sách thuộc danh mục ID={category_id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post("/", response_model=CategoryInfo, status_code=status.HTTP_201_CREATED)
@profile_endpoint(name="admin:categories:create")
@invalidate_cache(namespace="admin:categories")
@log_admin_action(
    action="create", resource_type="category", description="Tạo danh mục mới"
)
async def create_category(
    category: CategoryCreate,
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["category:create"])),
    request: Request = None,
):
    """
    Tạo mới danh mục.
    """
    try:
        new_category = await category_service.create_category(
            db=db, category_data=category.model_dump()
        )
        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã tạo danh mục mới: {new_category.name}"
        )
        return new_category
    except ConflictException as e:
        logger.warning(
            f"Admin {admin.get('username', 'unknown')} cố gắng tạo danh mục bị xung đột: {str(e)}"
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except NotFoundException as e:
        logger.warning(
            f"Admin {admin.get('username', 'unknown')} cố gắng tạo danh mục với tham chiếu không tồn tại: {str(e)}"
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Lỗi khi tạo danh mục mới: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.put("/{category_id}", response_model=CategoryInfo)
@profile_endpoint(name="admin:categories:update")
@invalidate_cache(namespace="admin:categories")
@log_admin_action(
    action="update", resource_type="category", resource_id="{category_id}"
)
async def update_category(
    category_id: int = Path(..., ge=1, description="ID của danh mục"),
    category: CategoryUpdate = Body(...),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["category:update"])),
    request: Request = None,
):
    """
    Cập nhật thông tin danh mục.

    - **category_id**: ID của danh mục
    """
    try:
        updated_category = await category_service.update_category(
            db=db,
            category_id=category_id,
            category_data=category.model_dump(exclude_unset=True),
        )
        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã cập nhật danh mục: {updated_category.name}"
        )
        return updated_category
    except NotFoundException as e:
        logger.warning(
            f"Admin {admin.get('username', 'unknown')} cố gắng cập nhật danh mục không tồn tại ID={category_id}"
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ConflictException as e:
        logger.warning(
            f"Admin {admin.get('username', 'unknown')} cố gắng cập nhật danh mục bị xung đột: {str(e)}"
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except BadRequestException as e:
        logger.warning(
            f"Admin {admin.get('username', 'unknown')} gửi yêu cầu không hợp lệ khi cập nhật danh mục: {str(e)}"
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật danh mục ID={category_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
@profile_endpoint(name="admin:categories:delete")
@invalidate_cache(namespace="admin:categories")
@log_admin_action(
    action="delete", resource_type="category", resource_id="{category_id}"
)
async def delete_category(
    category_id: int = Path(..., ge=1, description="ID của danh mục"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["category:delete"])),
    request: Request = None,
):
    """
    Xóa danh mục.

    - **category_id**: ID của danh mục
    """
    try:
        # Lấy thông tin danh mục trước khi xóa để ghi log
        category = await category_service.get_category_by_id(
            db=db, category_id=category_id
        )

        await category_service.delete_category(db=db, category_id=category_id)

        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã xóa danh mục: {category.name}"
        )
    except NotFoundException as e:
        logger.warning(
            f"Admin {admin.get('username', 'unknown')} cố gắng xóa danh mục không tồn tại ID={category_id}"
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except BadRequestException as e:
        logger.warning(
            f"Admin {admin.get('username', 'unknown')} gửi yêu cầu không hợp lệ khi xóa danh mục: {str(e)}"
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Lỗi khi xóa danh mục ID={category_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.put("/{category_id}/active", response_model=CategoryInfo)
@profile_endpoint(name="admin:categories:toggle_active")
@invalidate_cache(namespace="admin:categories")
@log_admin_action(
    action="update",
    resource_type="category",
    resource_id="{category_id}",
    description="Thay đổi trạng thái hoạt động",
)
async def toggle_category_active_status(
    category_id: int = Path(..., ge=1, description="ID của danh mục"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["category:update"])),
    request: Request = None,
):
    """
    Chuyển đổi trạng thái hoạt động của danh mục.

    - **category_id**: ID của danh mục
    """
    try:
        updated_category = await category_service.toggle_category_active_status(
            db=db, category_id=category_id
        )

        status_text = "kích hoạt" if updated_category.is_active else "vô hiệu hóa"
        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã {status_text} danh mục: {updated_category.name}"
        )

        return updated_category
    except NotFoundException as e:
        logger.warning(
            f"Admin {admin.get('username', 'unknown')} cố gắng thay đổi trạng thái danh mục không tồn tại ID={category_id}"
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(
            f"Lỗi khi thay đổi trạng thái hoạt động của danh mục ID={category_id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.put("/{category_id}/feature", response_model=CategoryInfo)
@profile_endpoint(name="admin:categories:toggle_featured")
@invalidate_cache(namespace="admin:categories")
@log_admin_action(
    action="update",
    resource_type="category",
    resource_id="{category_id}",
    description="Thay đổi trạng thái nổi bật",
)
async def toggle_category_featured_status(
    category_id: int = Path(..., ge=1, description="ID của danh mục"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["category:update"])),
    request: Request = None,
):
    """
    Chuyển đổi trạng thái nổi bật của danh mục.

    - **category_id**: ID của danh mục
    """
    try:
        updated_category = await category_service.toggle_category_featured_status(
            db=db, category_id=category_id
        )

        status_text = "đặt nổi bật" if updated_category.is_featured else "bỏ nổi bật"
        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã {status_text} danh mục: {updated_category.name}"
        )

        return updated_category
    except NotFoundException as e:
        logger.warning(
            f"Admin {admin.get('username', 'unknown')} cố gắng thay đổi trạng thái nổi bật của danh mục không tồn tại ID={category_id}"
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(
            f"Lỗi khi thay đổi trạng thái nổi bật của danh mục ID={category_id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.put("/{category_id}/book-count", response_model=CategoryInfo)
@profile_endpoint(name="admin:categories:update_book_count")
@invalidate_cache(namespace="admin:categories")
@log_admin_action(
    action="update",
    resource_type="category",
    resource_id="{category_id}",
    description="Cập nhật số lượng sách",
)
async def update_book_count(
    category_id: int = Path(..., ge=1, description="ID của danh mục"),
    db: Session = Depends(get_db),
    admin: Dict = Depends(secure_admin_access(["category:update"])),
    request: Request = None,
):
    """
    Cập nhật số lượng sách trong danh mục.

    - **category_id**: ID của danh mục
    """
    try:
        updated_category = await category_service.update_book_count(
            db=db, category_id=category_id
        )

        logger.info(
            f"Admin {admin.get('username', 'unknown')} đã cập nhật số lượng sách trong danh mục: {updated_category.name}"
        )

        return updated_category
    except NotFoundException as e:
        logger.warning(
            f"Admin {admin.get('username', 'unknown')} cố gắng cập nhật số lượng sách của danh mục không tồn tại ID={category_id}"
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(
            f"Lỗi khi cập nhật số lượng sách trong danh mục ID={category_id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
