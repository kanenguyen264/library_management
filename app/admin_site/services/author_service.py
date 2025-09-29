from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timezone

from app.user_site.repositories.author_repo import AuthorRepository
from app.user_site.schemas.author import AuthorCreate, AuthorUpdate
from app.core.exceptions import (
    NotFoundException,
    ConflictException,
    ServerException,
    ValidationException,
)
from app.cache.decorators import cached, invalidate_cache
from app.logging.setup import get_logger
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate

logger = get_logger(__name__)


@cached(ttl=300, namespace="admin:authors", tags=["authors"])
async def get_all_authors(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    is_featured: Optional[bool] = None,
    order_by: str = "name",
    order_desc: bool = False,
    admin_id: Optional[int] = None,
) -> List:
    """
    Lấy danh sách tác giả với các tùy chọn lọc.

    Args:
        db: Database session
        skip: Số lượng bản ghi bỏ qua
        limit: Số lượng bản ghi tối đa
        search: Tìm kiếm theo tên, tiểu sử
        is_featured: Lọc theo trạng thái nổi bật
        order_by: Trường sắp xếp
        order_desc: Sắp xếp giảm dần nếu True
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách tác giả
    """
    try:
        authors = await AuthorRepository.get_all(
            db=db,
            skip=skip,
            limit=limit,
            search=search,
            is_featured=is_featured,
            order_by=order_by,
            order_desc=order_desc,
        )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="AUTHORS",
                        entity_id=0,
                        description="Viewed author list",
                        metadata={
                            "skip": skip,
                            "limit": limit,
                            "search": search,
                            "is_featured": is_featured,
                            "order_by": order_by,
                            "order_desc": order_desc,
                            "results_count": len(authors),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return authors
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách tác giả: {str(e)}")
        raise ServerException(detail=f"Lỗi khi lấy danh sách tác giả: {str(e)}")


def count_authors(
    db: Session, search: Optional[str] = None, is_featured: Optional[bool] = None
) -> int:
    """
    Đếm số lượng tác giả theo điều kiện lọc.

    Args:
        db: Database session
        search: Tìm kiếm theo tên, tiểu sử
        is_featured: Lọc theo trạng thái nổi bật

    Returns:
        Tổng số tác giả thỏa mãn điều kiện
    """
    try:
        return AuthorRepository.count(db=db, search=search, is_featured=is_featured)
    except Exception as e:
        logger.error(f"Lỗi khi đếm tác giả: {str(e)}")
        raise ServerException(detail=f"Lỗi khi đếm tác giả: {str(e)}")


@cached(ttl=3600, namespace="admin:authors", tags=["authors"])
async def get_author_by_id(
    db: Session, author_id: int, admin_id: Optional[int] = None
) -> Any:
    """
    Lấy thông tin tác giả theo ID.

    Args:
        db: Database session
        author_id: ID tác giả
        admin_id: ID của admin thực hiện hành động

    Returns:
        Author object

    Raises:
        NotFoundException: Nếu không tìm thấy tác giả
    """
    author = await AuthorRepository.get_by_id(db, author_id)
    if not author:
        logger.warning(f"Không tìm thấy tác giả với ID={author_id}")
        raise NotFoundException(detail=f"Không tìm thấy tác giả với ID={author_id}")

    # Log admin activity
    if admin_id:
        try:
            await create_admin_activity_log(
                db,
                AdminActivityLogCreate(
                    admin_id=admin_id,
                    activity_type="VIEW",
                    entity_type="AUTHOR",
                    entity_id=author_id,
                    description=f"Viewed author details: {author.name}",
                    metadata={
                        "name": author.name,
                        "bio": author.bio,
                        "is_featured": author.is_featured,
                        "books_count": (
                            author.books_count if hasattr(author, "books_count") else 0
                        ),
                    },
                ),
            )
        except Exception as e:
            logger.error(f"Failed to log admin activity: {str(e)}")

    return author


@cached(ttl=3600, namespace="admin:authors", tags=["authors"])
def get_author_by_slug(db: Session, slug: str) -> Optional[Any]:
    """
    Lấy thông tin tác giả theo slug.

    Args:
        db: Database session
        slug: Slug của tác giả

    Returns:
        Author object hoặc None nếu không tìm thấy
    """
    author = AuthorRepository.get_by_slug(db, slug)
    if not author:
        logger.warning(f"Không tìm thấy tác giả với slug={slug}")
        raise NotFoundException(detail=f"Không tìm thấy tác giả với slug={slug}")
    return author


@invalidate_cache(tags=["authors"])
async def create_author(
    db: Session, author_data: AuthorCreate, admin_id: Optional[int] = None
) -> Any:
    """
    Tạo tác giả mới.

    Args:
        db: Database session
        author_data: Thông tin tác giả mới
        admin_id: ID của admin thực hiện hành động

    Returns:
        Author object đã tạo

    Raises:
        ConflictException: Nếu tên tác giả đã tồn tại
        ServerException: Nếu có lỗi khác xảy ra
    """
    # Kiểm tra tên tác giả đã tồn tại chưa
    existing_author = await AuthorRepository.get_by_name(db, author_data.name)
    if existing_author:
        logger.warning(f"Tên tác giả đã tồn tại: {author_data.name}")
        raise ConflictException(detail="Tên tác giả đã tồn tại", field="name")

    # Chuẩn bị dữ liệu
    author_dict = author_data.model_dump()
    author_dict.update(
        {"created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)}
    )

    # Tạo tác giả mới
    try:
        author = await AuthorRepository.create(db, author_dict)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="CREATE",
                        entity_type="AUTHOR",
                        entity_id=author.id,
                        description=f"Created new author: {author.name}",
                        metadata={
                            "name": author.name,
                            "bio": author.bio,
                            "is_featured": author.is_featured,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return author
    except Exception as e:
        logger.error(f"Lỗi khi tạo tác giả: {str(e)}")
        raise ServerException(detail=f"Không thể tạo tác giả: {str(e)}")


@invalidate_cache(tags=["authors"])
async def update_author(
    db: Session,
    author_id: int,
    author_data: AuthorUpdate,
    admin_id: Optional[int] = None,
) -> Any:
    """
    Cập nhật thông tin tác giả.

    Args:
        db: Database session
        author_id: ID tác giả
        author_data: Dữ liệu cập nhật
        admin_id: ID của admin thực hiện hành động

    Returns:
        Author object đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy tác giả
        ConflictException: Nếu tên mới đã tồn tại
        ServerException: Nếu có lỗi khác xảy ra
    """
    # Kiểm tra tác giả tồn tại
    author = await get_author_by_id(db, author_id)

    # Nếu đổi tên, kiểm tra tên mới đã tồn tại chưa
    if author_data.name and author_data.name != author.name:
        existing = await AuthorRepository.get_by_name(db, author_data.name)
        if existing and existing.id != author_id:
            logger.warning(f"Tên tác giả đã tồn tại: {author_data.name}")
            raise ConflictException(detail="Tên tác giả đã tồn tại", field="name")

    # Chuẩn bị dữ liệu
    update_data = author_data.model_dump(exclude_unset=True)

    # Cập nhật
    try:
        updated_author = await AuthorRepository.update(db, author_id, update_data)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="AUTHOR",
                        entity_id=author_id,
                        description=f"Updated author: {updated_author.name}",
                        metadata={
                            "updated_fields": list(update_data.keys()),
                            "old_values": {
                                k: getattr(author, k) for k in update_data.keys()
                            },
                            "new_values": {
                                k: getattr(updated_author, k)
                                for k in update_data.keys()
                            },
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return updated_author
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật tác giả: {str(e)}")
        raise ServerException(detail=f"Không thể cập nhật tác giả: {str(e)}")


@invalidate_cache(tags=["authors"])
async def delete_author(
    db: Session, author_id: int, admin_id: Optional[int] = None
) -> bool:
    """
    Xóa tác giả.

    Args:
        db: Database session
        author_id: ID tác giả
        admin_id: ID của admin thực hiện hành động

    Returns:
        True nếu xóa thành công

    Raises:
        NotFoundException: Nếu không tìm thấy tác giả
        ServerException: Nếu có lỗi khác xảy ra
    """
    # Kiểm tra tác giả tồn tại
    author = await get_author_by_id(db, author_id)

    # Xóa tác giả
    try:
        result = await AuthorRepository.delete(db, author_id)
        if not result:
            raise NotFoundException(detail=f"Không tìm thấy tác giả với ID={author_id}")

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="DELETE",
                        entity_type="AUTHOR",
                        entity_id=author_id,
                        description=f"Deleted author: {author.name}",
                        metadata={
                            "name": author.name,
                            "bio": author.bio,
                            "is_featured": author.is_featured,
                            "books_count": (
                                author.books_count
                                if hasattr(author, "books_count")
                                else 0
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return result
    except NotFoundException as e:
        raise e
    except Exception as e:
        logger.error(f"Lỗi khi xóa tác giả: {str(e)}")
        raise ServerException(detail=f"Không thể xóa tác giả: {str(e)}")


@cached(ttl=300, namespace="admin:authors", tags=["authors"])
def get_author_books(
    db: Session,
    author_id: int,
    skip: int = 0,
    limit: int = 20,
    only_published: bool = False,
) -> List:
    """
    Lấy danh sách sách của tác giả.

    Args:
        db: Database session
        author_id: ID tác giả
        skip: Số lượng bản ghi bỏ qua
        limit: Số lượng bản ghi tối đa
        only_published: Chỉ lấy sách đã xuất bản

    Returns:
        Danh sách sách

    Raises:
        NotFoundException: Nếu không tìm thấy tác giả
        ServerException: Nếu có lỗi khác xảy ra
    """
    # Kiểm tra tác giả tồn tại
    get_author_by_id(db, author_id)

    try:
        return AuthorRepository.get_books_by_author(
            db=db,
            author_id=author_id,
            skip=skip,
            limit=limit,
            only_published=only_published,
        )
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách sách của tác giả: {str(e)}")
        raise ServerException(
            detail=f"Lỗi khi lấy danh sách sách của tác giả: {str(e)}"
        )


def count_author_books(
    db: Session, author_id: int, only_published: bool = False
) -> int:
    """
    Đếm số lượng sách của tác giả.

    Args:
        db: Database session
        author_id: ID tác giả
        only_published: Chỉ đếm sách đã xuất bản

    Returns:
        Số lượng sách

    Raises:
        NotFoundException: Nếu không tìm thấy tác giả
        ServerException: Nếu có lỗi khác xảy ra
    """
    # Kiểm tra tác giả tồn tại
    get_author_by_id(db, author_id)

    try:
        return AuthorRepository.count_books_by_author(
            db=db, author_id=author_id, only_published=only_published
        )
    except Exception as e:
        logger.error(f"Lỗi khi đếm sách của tác giả: {str(e)}")
        raise ServerException(detail=f"Lỗi khi đếm sách của tác giả: {str(e)}")


@invalidate_cache(tags=["authors"])
async def toggle_featured_status(
    db: Session, author_id: int, admin_id: Optional[int] = None
) -> Any:
    """
    Đảo ngược trạng thái nổi bật của tác giả.

    Args:
        db: Database session
        author_id: ID tác giả
        admin_id: ID của admin thực hiện hành động

    Returns:
        Author object đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy tác giả
        ServerException: Nếu có lỗi khác xảy ra
    """
    author = await get_author_by_id(db, author_id)

    try:
        updated_author = await AuthorRepository.update(
            db=db,
            author_id=author_id,
            author_data={"is_featured": not author.is_featured},
        )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="AUTHOR_FEATURED_STATUS",
                        entity_id=author_id,
                        description=f"Changed featured status for author: {updated_author.name}",
                        metadata={
                            "name": updated_author.name,
                            "old_status": author.is_featured,
                            "new_status": updated_author.is_featured,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return updated_author
    except Exception as e:
        logger.error(f"Lỗi khi thay đổi trạng thái nổi bật của tác giả: {str(e)}")
        raise ServerException(
            detail=f"Lỗi khi thay đổi trạng thái nổi bật của tác giả: {str(e)}"
        )


@invalidate_cache(tags=["authors"])
async def update_book_count(db: Session, author_id: int) -> Any:
    """
    Cập nhật số lượng sách của tác giả.

    Args:
        db: Database session
        author_id: ID tác giả

    Returns:
        Author object đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy tác giả
        ServerException: Nếu có lỗi khác xảy ra
    """
    # Kiểm tra tác giả tồn tại
    get_author_by_id(db, author_id)

    try:
        return AuthorRepository.update_book_count(db, author_id)
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật số lượng sách của tác giả: {str(e)}")
        raise ServerException(
            detail=f"Lỗi khi cập nhật số lượng sách của tác giả: {str(e)}"
        )


@cached(ttl=600, namespace="admin:authors", tags=["authors"])
async def get_featured_authors(
    db: Session, limit: int = 10, admin_id: Optional[int] = None
) -> List:
    """
    Lấy danh sách tác giả nổi bật.

    Args:
        db: Database session
        limit: Số lượng bản ghi tối đa
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách tác giả nổi bật
    """
    try:
        authors = await AuthorRepository.get_featured_authors(db, limit)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="FEATURED_AUTHORS",
                        entity_id=0,
                        description="Viewed featured authors list",
                        metadata={"limit": limit, "results_count": len(authors)},
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return authors
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách tác giả nổi bật: {str(e)}")
        raise ServerException(detail=f"Lỗi khi lấy danh sách tác giả nổi bật: {str(e)}")


@cached(key_prefix="admin_author_statistics", ttl=3600)
async def get_author_statistics(
    db: Session, admin_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Lấy thống kê về tác giả.

    Args:
        db: Database session
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thống kê tác giả
    """
    try:
        repo = AuthorRepository(db)

        # Đếm tổng số tác giả
        total = await repo.count_authors()

        # Thống kê theo trạng thái nổi bật
        by_featured = await repo.count_authors_by_featured()

        # Thống kê theo số lượng sách
        by_books = await repo.count_authors_by_books()

        stats = {"total": total, "by_featured": by_featured, "by_books": by_books}

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="AUTHOR_STATISTICS",
                        entity_id=0,
                        description="Viewed author statistics",
                        metadata=stats,
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return stats
    except Exception as e:
        logger.error(f"Lỗi khi lấy thống kê tác giả: {str(e)}")
        raise
