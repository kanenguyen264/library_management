from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from datetime import datetime
import logging

from app.user_site.repositories.category_repo import CategoryRepository
from app.user_site.models.category import Category
from app.user_site.models.book import Book
from app.core.exceptions import (
    NotFoundException,
    ConflictException,
    ForbiddenException,
)
from app.logging.setup import get_logger
from app.cache.decorators import cached, invalidate_cache
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate

logger = get_logger(__name__)


async def get_all_categories(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    search_query: Optional[str] = None,
    parent_id: Optional[int] = None,
    is_active: Optional[bool] = None,
    sort_by: str = "name",
    sort_desc: bool = False,
    admin_id: Optional[int] = None,
) -> List[Category]:
    """
    Lấy danh sách danh mục với bộ lọc.

    Args:
        db: Database session
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về
        search_query: Chuỗi tìm kiếm
        parent_id: ID danh mục cha
        is_active: Lọc theo trạng thái
        sort_by: Sắp xếp theo trường
        sort_desc: Sắp xếp giảm dần
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách danh mục
    """
    try:
        repo = CategoryRepository(db)

        if parent_id is not None:
            categories = await repo.list_subcategories(parent_id, skip, limit)
        elif search_query:
            categories = await repo.search_categories(search_query, skip, limit)
        else:
            categories = await repo.list_categories(skip, limit)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="CATEGORIES",
                        entity_id=0,
                        description="Viewed category list",
                        metadata={
                            "skip": skip,
                            "limit": limit,
                            "search": search_query,
                            "parent_id": parent_id,
                            "is_active": is_active,
                            "sort_by": sort_by,
                            "sort_desc": sort_desc,
                            "results_count": len(categories),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return categories
    except Exception as e:
        logger.error(f"Error retrieving categories: {str(e)}")
        raise


async def count_categories(
    db: Session, search_query: Optional[str] = None, parent_id: Optional[int] = None
) -> int:
    """
    Đếm số lượng danh mục.

    Args:
        db: Database session
        search_query: Chuỗi tìm kiếm
        parent_id: ID danh mục cha

    Returns:
        Số lượng danh mục
    """
    try:
        repo = CategoryRepository(db)

        if parent_id is not None:
            return await repo.count_subcategories(parent_id)
        elif search_query:
            return await repo.count_search_results(search_query)
        else:
            return await repo.count_categories()
    except Exception as e:
        logger.error(f"Lỗi khi đếm số lượng danh mục: {str(e)}")
        raise


@cached(key_prefix="admin_category", ttl=300)
async def get_category_by_id(
    db: Session, category_id: int, admin_id: Optional[int] = None
) -> Category:
    """
    Lấy thông tin danh mục theo ID.

    Args:
        db: Database session
        category_id: ID của danh mục
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin danh mục

    Raises:
        NotFoundException: Nếu không tìm thấy danh mục
    """
    try:
        repo = CategoryRepository(db)
        category = await repo.get_category_by_id(category_id)

        if not category:
            logger.warning(f"Không tìm thấy danh mục với ID {category_id}")
            raise NotFoundException(
                detail=f"Không tìm thấy danh mục với ID {category_id}"
            )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="CATEGORY",
                        entity_id=category_id,
                        description=f"Viewed category details: {category.name}",
                        metadata={
                            "name": category.name,
                            "slug": category.slug,
                            "description": category.description,
                            "parent_id": category.parent_id,
                            "is_active": category.is_active,
                            "books_count": (
                                len(category.books) if hasattr(category, "books") else 0
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return category
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving category: {str(e)}")
        raise


@cached(key_prefix="admin_category_by_slug", ttl=300)
async def get_category_by_slug(db: Session, slug: str) -> Category:
    """
    Lấy thông tin danh mục theo slug.

    Args:
        db: Database session
        slug: Slug của danh mục

    Returns:
        Thông tin danh mục

    Raises:
        NotFoundException: Nếu không tìm thấy danh mục
    """
    try:
        repo = CategoryRepository(db)
        category = await repo.get_category_by_slug(slug)

        if not category:
            logger.warning(f"Không tìm thấy danh mục với slug {slug}")
            raise NotFoundException(detail=f"Không tìm thấy danh mục với slug {slug}")

        return category
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin danh mục: {str(e)}")
        raise


async def create_category(
    db: Session, category_data: Dict[str, Any], admin_id: Optional[int] = None
) -> Category:
    """
    Tạo danh mục mới.

    Args:
        db: Database session
        category_data: Dữ liệu danh mục
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin danh mục đã tạo

    Raises:
        NotFoundException: Nếu không tìm thấy danh mục cha
        ForbiddenException: Nếu tên hoặc slug đã tồn tại
    """
    try:
        repo = CategoryRepository(db)

        # Kiểm tra danh mục cha tồn tại
        if "parent_id" in category_data and category_data["parent_id"]:
            parent = await repo.get_category_by_id(category_data["parent_id"])

            if not parent:
                logger.warning(
                    f"Không tìm thấy danh mục cha với ID {category_data['parent_id']}"
                )
                raise NotFoundException(
                    detail=f"Không tìm thấy danh mục cha với ID {category_data['parent_id']}"
                )

        # Kiểm tra tên đã tồn tại
        if "name" in category_data:
            existing_by_name = await repo.get_category_by_name(category_data["name"])

            if existing_by_name:
                logger.warning(f"Danh mục với tên {category_data['name']} đã tồn tại")
                raise ForbiddenException(
                    detail=f"Danh mục với tên {category_data['name']} đã tồn tại"
                )

        # Kiểm tra slug đã tồn tại
        if "slug" in category_data:
            existing_by_slug = await repo.get_category_by_slug(category_data["slug"])

            if existing_by_slug:
                logger.warning(f"Danh mục với slug {category_data['slug']} đã tồn tại")
                raise ForbiddenException(
                    detail=f"Danh mục với slug {category_data['slug']} đã tồn tại"
                )

        # Tạo danh mục mới
        category = await repo.create_category(category_data)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="CREATE",
                        entity_type="CATEGORY",
                        entity_id=category.id,
                        description=f"Created new category: {category.name}",
                        metadata={
                            "name": category.name,
                            "slug": category.slug,
                            "description": category.description,
                            "parent_id": category.parent_id,
                            "is_active": category.is_active,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Đã tạo danh mục mới với ID {category.id}")
        return category
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        logger.error(f"Error creating category: {str(e)}")
        raise


async def update_category(
    db: Session,
    category_id: int,
    category_data: Dict[str, Any],
    admin_id: Optional[int] = None,
) -> Category:
    """
    Cập nhật thông tin danh mục.

    Args:
        db: Database session
        category_id: ID của danh mục
        category_data: Dữ liệu cập nhật
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin danh mục đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy danh mục
        ForbiddenException: Nếu tên hoặc slug đã tồn tại
    """
    try:
        # Kiểm tra danh mục tồn tại
        current_category = await get_category_by_id(db, category_id)

        repo = CategoryRepository(db)

        # Kiểm tra xung đột tên nếu đổi tên
        if "name" in category_data and category_data["name"] != current_category.name:
            existing_by_name = await repo.get_category_by_name(category_data["name"])

            if existing_by_name and existing_by_name.id != category_id:
                logger.warning(
                    f"Danh mục khác với tên {category_data['name']} đã tồn tại"
                )
                raise ForbiddenException(
                    detail=f"Danh mục khác với tên {category_data['name']} đã tồn tại"
                )

        # Kiểm tra xung đột slug nếu đổi slug
        if "slug" in category_data and category_data["slug"] != current_category.slug:
            existing_by_slug = await repo.get_category_by_slug(category_data["slug"])

            if existing_by_slug and existing_by_slug.id != category_id:
                logger.warning(
                    f"Danh mục khác với slug {category_data['slug']} đã tồn tại"
                )
                raise ForbiddenException(
                    detail=f"Danh mục khác với slug {category_data['slug']} đã tồn tại"
                )

        # Kiểm tra danh mục cha tồn tại và tránh trường hợp chọn chính nó làm cha
        if "parent_id" in category_data:
            if category_data["parent_id"] == category_id:
                logger.warning(f"Không thể chọn chính danh mục làm danh mục cha")
                raise ForbiddenException(
                    detail=f"Không thể chọn chính danh mục làm danh mục cha"
                )

            if category_data["parent_id"]:
                parent = await repo.get_category_by_id(category_data["parent_id"])

                if not parent:
                    logger.warning(
                        f"Không tìm thấy danh mục cha với ID {category_data['parent_id']}"
                    )
                    raise NotFoundException(
                        detail=f"Không tìm thấy danh mục cha với ID {category_data['parent_id']}"
                    )

        # Cập nhật danh mục
        updated_category = await repo.update_category(category_id, category_data)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="CATEGORY",
                        entity_id=current_category.id,
                        description=f"Updated category - ID: {current_category.id}",
                        metadata={
                            "category_id": current_category.id,
                            "old_data": {
                                k: getattr(current_category, k)
                                for k in category_data.keys()
                            },
                            "new_data": {
                                k: getattr(updated_category, k)
                                for k in category_data.keys()
                            },
                            "changes": {
                                k: updated_category.__dict__[k]
                                for k in category_data.keys()
                                if getattr(current_category, k)
                                != getattr(updated_category, k)
                            },
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Đã cập nhật danh mục với ID {category_id}")
        return updated_category
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        logger.error(f"Error updating category: {str(e)}")
        raise


async def delete_category(
    db: Session, category_id: int, admin_id: Optional[int] = None
) -> bool:
    """
    Xóa danh mục.

    Args:
        db: Database session
        category_id: ID của danh mục
        admin_id: ID của admin thực hiện hành động

    Returns:
        True nếu xóa thành công

    Raises:
        NotFoundException: Nếu không tìm thấy danh mục
        ForbiddenException: Nếu danh mục có sách
    """
    try:
        # Kiểm tra danh mục tồn tại
        current_category = await get_category_by_id(db, category_id)

        # Kiểm tra danh mục có sách không
        books_count = await count_category_books(db, category_id, True)

        if books_count > 0:
            logger.warning(
                f"Không thể xóa danh mục ID={category_id} vì có {books_count} sách"
            )
            raise ForbiddenException(
                detail=f"Không thể xóa danh mục có sách. Vui lòng gỡ sách khỏi danh mục trước."
            )

        # Xóa danh mục
        repo = CategoryRepository(db)
        result = await repo.delete_category(category_id)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="DELETE",
                        entity_type="CATEGORY",
                        entity_id=category_id,
                        description=f"Deleted category: {current_category.name}",
                        metadata={
                            "name": current_category.name,
                            "slug": current_category.slug,
                            "description": current_category.description,
                            "parent_id": current_category.parent_id,
                            "is_active": current_category.is_active,
                            "books_count": books_count,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Đã xóa danh mục với ID {category_id}")
        return result
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        logger.error(f"Error deleting category: {str(e)}")
        raise


@cached(key_prefix="admin_root_categories", ttl=300)
async def get_root_categories(db: Session) -> List[Category]:
    """
    Lấy danh sách danh mục gốc (không có danh mục cha).

    Args:
        db: Database session

    Returns:
        Danh sách danh mục gốc
    """
    try:
        repo = CategoryRepository(db)
        categories = await repo.list_root_categories()

        return categories
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách danh mục gốc: {str(e)}")
        raise


@cached(key_prefix="admin_subcategories", ttl=300)
async def get_subcategories(db: Session, parent_id: int) -> List[Category]:
    """
    Lấy danh sách danh mục con của một danh mục.

    Args:
        db: Database session
        parent_id: ID của danh mục cha

    Returns:
        Danh sách danh mục con

    Raises:
        NotFoundException: Nếu không tìm thấy danh mục cha
    """
    try:
        # Kiểm tra danh mục cha tồn tại
        await get_category_by_id(db, parent_id)

        repo = CategoryRepository(db)
        subcategories = await repo.list_subcategories(parent_id)

        return subcategories
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách danh mục con: {str(e)}")
        raise


@cached(key_prefix="admin_category_path", ttl=300)
async def get_category_path(db: Session, category_id: int) -> List[Category]:
    """
    Lấy đường dẫn từ danh mục gốc đến danh mục hiện tại.

    Args:
        db: Database session
        category_id: ID của danh mục

    Returns:
        Danh sách danh mục trong đường dẫn

    Raises:
        NotFoundException: Nếu không tìm thấy danh mục
    """
    try:
        # Kiểm tra danh mục tồn tại
        await get_category_by_id(db, category_id)

        repo = CategoryRepository(db)
        path = await repo.get_category_path(category_id)

        return path
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy đường dẫn danh mục: {str(e)}")
        raise


@cached(key_prefix="admin_category_books", ttl=300)
async def get_category_books(
    db: Session,
    category_id: int,
    skip: int = 0,
    limit: int = 20,
    include_subcategories: bool = False,
) -> List[Any]:
    """
    Lấy danh sách sách thuộc danh mục.

    Args:
        db: Database session
        category_id: ID của danh mục
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về
        include_subcategories: Có bao gồm sách từ danh mục con không

    Returns:
        Danh sách sách

    Raises:
        NotFoundException: Nếu không tìm thấy danh mục
    """
    try:
        # Kiểm tra danh mục tồn tại
        await get_category_by_id(db, category_id)

        repo = CategoryRepository(db)
        books = await repo.list_category_books(
            category_id, skip, limit, include_subcategories
        )

        return books
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách sách thuộc danh mục: {str(e)}")
        raise


async def count_category_books(
    db: Session, category_id: int, include_subcategories: bool = False
) -> int:
    """
    Đếm số lượng sách thuộc danh mục.

    Args:
        db: Database session
        category_id: ID của danh mục
        include_subcategories: Có đếm cả sách từ danh mục con không

    Returns:
        Số lượng sách

    Raises:
        NotFoundException: Nếu không tìm thấy danh mục
    """
    try:
        # Kiểm tra danh mục tồn tại
        await get_category_by_id(db, category_id)

        repo = CategoryRepository(db)
        count = await repo.count_category_books(category_id, include_subcategories)

        return count
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi đếm số sách thuộc danh mục: {str(e)}")
        raise


@cached(key_prefix="admin_category_tree", ttl=600)
async def get_category_tree(db: Session) -> List[Dict[str, Any]]:
    """
    Lấy cây phân cấp danh mục.

    Args:
        db: Database session

    Returns:
        Cây phân cấp danh mục
    """
    try:
        repo = CategoryRepository(db)
        tree = await repo.get_category_tree()

        return tree
    except Exception as e:
        logger.error(f"Lỗi khi lấy cây phân cấp danh mục: {str(e)}")
        raise


async def update_category_order(
    db: Session, category_id: int, new_order: int
) -> Category:
    """
    Cập nhật thứ tự hiển thị của danh mục.

    Args:
        db: Database session
        category_id: ID của danh mục
        new_order: Thứ tự mới

    Returns:
        Thông tin danh mục đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy danh mục
    """
    try:
        # Kiểm tra danh mục tồn tại
        await get_category_by_id(db, category_id)

        repo = CategoryRepository(db)
        updated_category = await repo.update_category(
            category_id, {"display_order": new_order}
        )

        logger.info(
            f"Đã cập nhật thứ tự hiển thị của danh mục {category_id} thành {new_order}"
        )
        return updated_category
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật thứ tự hiển thị: {str(e)}")
        raise


@cached(key_prefix="admin_popular_categories", ttl=3600)
async def get_popular_categories(db: Session, limit: int = 10) -> List[Category]:
    """
    Lấy danh sách danh mục phổ biến nhất.

    Args:
        db: Database session
        limit: Số danh mục tối đa trả về

    Returns:
        Danh sách danh mục phổ biến
    """
    try:
        repo = CategoryRepository(db)
        categories = await repo.get_popular_categories(limit)

        return categories
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách danh mục phổ biến: {str(e)}")
        raise


@cached(key_prefix="admin_category_statistics", ttl=3600)
async def get_category_statistics(
    db: Session, admin_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Lấy thống kê về danh mục.

    Args:
        db: Database session
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thống kê danh mục
    """
    try:
        repo = CategoryRepository(db)

        # Đếm tổng số danh mục
        total_count = await repo.count_categories()

        # Đếm số danh mục gốc
        root_count = await repo.count_root_categories()

        # Thống kê theo trạng thái
        by_status = await repo.count_categories_by_status()

        # Thống kê theo danh mục cha
        by_parent = await repo.count_categories_by_parent()

        # Thống kê theo số lượng sách
        by_books = await repo.count_categories_by_books()

        stats = {
            "total_categories": total_count,
            "root_categories": root_count,
            "by_status": by_status,
            "by_parent": by_parent,
            "by_books": by_books,
        }

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="CATEGORY_STATISTICS",
                        entity_id=0,
                        description="Viewed category statistics",
                        metadata=stats,
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return stats
    except Exception as e:
        logger.error(f"Error retrieving category statistics: {str(e)}")
        raise
