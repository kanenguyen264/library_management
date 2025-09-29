from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
import logging

from app.user_site.models.book_series import BookSeries, BookSeriesItem
from app.user_site.repositories.book_series_repo import BookSeriesRepository
from app.user_site.repositories.book_repo import BookRepository
from app.core.exceptions import NotFoundException, ForbiddenException
from app.cache.decorators import cached, invalidate_cache
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate

# Logger cho book series service
logger = logging.getLogger(__name__)


async def get_all_series(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    search_query: Optional[str] = None,
    admin_id: Optional[int] = None,
) -> List[BookSeries]:
    """
    Lấy danh sách series sách với bộ lọc.

    Args:
        db: Database session
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về
        search_query: Chuỗi tìm kiếm
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách series sách
    """
    try:
        repo = BookSeriesRepository(db)
        series_list = await repo.list_series(skip, limit, search_query)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="BOOK_SERIES",
                        entity_id=0,
                        description="Viewed book series list",
                        metadata={
                            "skip": skip,
                            "limit": limit,
                            "search_query": search_query,
                            "results_count": len(series_list),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return series_list
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách series sách: {str(e)}")
        raise


async def count_series(db: Session, search_query: Optional[str] = None) -> int:
    """
    Đếm số lượng series sách.

    Args:
        db: Database session
        search_query: Chuỗi tìm kiếm

    Returns:
        Số lượng series sách
    """
    try:
        repo = BookSeriesRepository(db)
        return await repo.count_series(search_query)
    except Exception as e:
        logger.error(f"Lỗi khi đếm series sách: {str(e)}")
        raise


@cached(key_prefix="admin_book_series", ttl=300)
async def get_series_by_id(
    db: Session,
    series_id: int,
    include_items: bool = False,
    admin_id: Optional[int] = None,
) -> BookSeries:
    """
    Lấy thông tin series sách theo ID.

    Args:
        db: Database session
        series_id: ID của series sách
        include_items: Có load các sách trong series không
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin series sách

    Raises:
        NotFoundException: Nếu không tìm thấy series sách
    """
    try:
        repo = BookSeriesRepository(db)
        series = await repo.get_series_by_id(series_id, include_items)

        if not series:
            logger.warning(f"Không tìm thấy series sách với ID {series_id}")
            raise NotFoundException(
                detail=f"Không tìm thấy series sách với ID {series_id}"
            )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="BOOK_SERIES",
                        entity_id=series_id,
                        description=f"Viewed book series details: {series.name}",
                        metadata={
                            "name": series.name,
                            "description": (
                                series.description
                                if hasattr(series, "description")
                                else None
                            ),
                            "total_books": (
                                series.total_books
                                if hasattr(series, "total_books")
                                else 0
                            ),
                            "include_items": include_items,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return series
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin series sách: {str(e)}")
        raise


@cached(key_prefix="admin_book_series_name", ttl=300)
async def get_series_by_name(db: Session, name: str) -> BookSeries:
    """
    Lấy thông tin series sách theo tên.

    Args:
        db: Database session
        name: Tên của series sách

    Returns:
        Thông tin series sách

    Raises:
        NotFoundException: Nếu không tìm thấy series sách
    """
    try:
        repo = BookSeriesRepository(db)
        series = await repo.get_series_by_name(name)

        if not series:
            logger.warning(f"Không tìm thấy series sách với tên {name}")
            raise NotFoundException(detail=f"Không tìm thấy series sách với tên {name}")

        return series
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin series sách theo tên: {str(e)}")
        raise


async def create_series(
    db: Session, series_data: Dict[str, Any], admin_id: Optional[int] = None
) -> BookSeries:
    """
    Tạo series sách mới.

    Args:
        db: Database session
        series_data: Dữ liệu series sách
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin series sách đã tạo

    Raises:
        ForbiddenException: Nếu series sách với tên này đã tồn tại
    """
    try:
        # Kiểm tra series sách đã tồn tại
        if "name" in series_data:
            repo = BookSeriesRepository(db)
            existing_series = await repo.get_series_by_name(series_data["name"])

            if existing_series:
                logger.warning(f"Series sách với tên {series_data['name']} đã tồn tại")
                raise ForbiddenException(
                    detail=f"Series sách với tên {series_data['name']} đã tồn tại"
                )

        # Tạo series sách mới
        repo = BookSeriesRepository(db)
        series = await repo.create_series(series_data)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="CREATE",
                        entity_type="BOOK_SERIES",
                        entity_id=series.id,
                        description=f"Created new book series: {series.name}",
                        metadata=series_data,
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Đã tạo series sách mới với ID {series.id}")
        return series
    except ForbiddenException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi tạo series sách: {str(e)}")
        raise


async def update_series(
    db: Session,
    series_id: int,
    series_data: Dict[str, Any],
    admin_id: Optional[int] = None,
) -> BookSeries:
    """
    Cập nhật thông tin series sách.

    Args:
        db: Database session
        series_id: ID của series sách
        series_data: Dữ liệu cập nhật
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin series sách đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy series sách
        ForbiddenException: Nếu series sách với tên mới đã tồn tại
    """
    try:
        # Kiểm tra series sách tồn tại
        series = await get_series_by_id(db, series_id)

        # Kiểm tra xung đột tên nếu đổi tên
        if "name" in series_data and series_data["name"] != series.name:
            repo = BookSeriesRepository(db)
            existing_series = await repo.get_series_by_name(series_data["name"])

            if existing_series and existing_series.id != series_id:
                logger.warning(f"Series sách với tên {series_data['name']} đã tồn tại")
                raise ForbiddenException(
                    detail=f"Series sách với tên {series_data['name']} đã tồn tại"
                )

        # Cập nhật series sách
        repo = BookSeriesRepository(db)
        updated_series = await repo.update_series(series_id, series_data)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="BOOK_SERIES",
                        entity_id=series_id,
                        description=f"Updated book series: {updated_series.name}",
                        metadata={"previous_name": series.name, "updates": series_data},
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        # Remove cache
        invalidate_cache(f"admin_book_series:{series_id}")
        invalidate_cache(f"admin_book_series_name:{series.name}")

        logger.info(f"Đã cập nhật series sách với ID {series_id}")
        return updated_series
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật series sách: {str(e)}")
        raise


async def delete_series(
    db: Session, series_id: int, admin_id: Optional[int] = None
) -> None:
    """
    Xóa series sách.

    Args:
        db: Database session
        series_id: ID của series sách
        admin_id: ID của admin thực hiện hành động

    Raises:
        NotFoundException: Nếu không tìm thấy series sách
    """
    try:
        # Kiểm tra series sách tồn tại
        series = await get_series_by_id(db, series_id)

        # Xóa series sách
        repo = BookSeriesRepository(db)
        await repo.delete_series(series_id)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="DELETE",
                        entity_type="BOOK_SERIES",
                        entity_id=series_id,
                        description=f"Deleted book series: {series.name}",
                        metadata={
                            "name": series.name,
                            "description": (
                                series.description
                                if hasattr(series, "description")
                                else None
                            ),
                            "total_books": (
                                series.total_books
                                if hasattr(series, "total_books")
                                else 0
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        # Remove caches
        invalidate_cache(f"admin_book_series:{series_id}")
        invalidate_cache(f"admin_book_series_name:{series.name}")
        invalidate_cache(f"admin_series_items:{series_id}")

        logger.info(f"Đã xóa series sách với ID {series_id}")
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi xóa series sách: {str(e)}")
        raise


@cached(key_prefix="admin_series_items", ttl=300)
async def get_series_items(
    db: Session, series_id: int, skip: int = 0, limit: int = 20
) -> List[BookSeriesItem]:
    """
    Lấy danh sách các sách trong series.

    Args:
        db: Database session
        series_id: ID của series sách
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về

    Returns:
        Danh sách các sách trong series

    Raises:
        NotFoundException: Nếu không tìm thấy series sách
    """
    try:
        # Kiểm tra series sách tồn tại
        await get_series_by_id(db, series_id)

        # Lấy danh sách các sách trong series
        repo = BookSeriesRepository(db)
        items = await repo.list_series_items(series_id, skip, limit)

        return items
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách các sách trong series: {str(e)}")
        raise


async def count_series_items(db: Session, series_id: int) -> int:
    """
    Đếm số lượng sách trong series.

    Args:
        db: Database session
        series_id: ID của series sách

    Returns:
        Số lượng sách trong series

    Raises:
        NotFoundException: Nếu không tìm thấy series sách
    """
    try:
        # Kiểm tra series sách tồn tại
        await get_series_by_id(db, series_id)

        # Đếm số lượng sách trong series
        repo = BookSeriesRepository(db)
        count = await repo.count_series_items(series_id)

        return count
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi đếm số lượng sách trong series: {str(e)}")
        raise


async def add_book_to_series(
    db: Session,
    series_id: int,
    book_id: int,
    position: Optional[int] = None,
    admin_id: Optional[int] = None,
) -> BookSeriesItem:
    """
    Thêm sách vào series.

    Args:
        db: Database session
        series_id: ID của series sách
        book_id: ID của sách
        position: Vị trí trong series
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin mục series đã tạo

    Raises:
        NotFoundException: Nếu không tìm thấy series sách hoặc sách
        ForbiddenException: Nếu sách đã tồn tại trong series
    """
    try:
        # Kiểm tra series sách tồn tại
        series = await get_series_by_id(db, series_id)

        # Kiểm tra sách tồn tại
        book_repo = BookRepository(db)
        book = await book_repo.get_by_id(book_id)

        if not book:
            logger.warning(f"Không tìm thấy sách với ID {book_id}")
            raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

        # Kiểm tra sách đã có trong series chưa
        series_repo = BookSeriesRepository(db)
        existing_item = await series_repo.get_series_item_by_book(series_id, book_id)

        if existing_item:
            logger.warning(f"Sách {book_id} đã tồn tại trong series {series_id}")
            raise ForbiddenException(detail=f"Sách đã tồn tại trong series")

        # Thêm sách vào series
        item_data = {"series_id": series_id, "book_id": book_id}

        if position is not None:
            item_data["position"] = position

        item = await series_repo.create_series_item(item_data)

        # Cập nhật số lượng sách trong series
        await series_repo.update_series_total_books(series_id)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="ADD",
                        entity_type="BOOK_TO_SERIES",
                        entity_id=item.id,
                        description=f"Added book to series: {book.title} to {series.name}",
                        metadata={
                            "series_id": series_id,
                            "series_name": series.name,
                            "book_id": book_id,
                            "book_title": (
                                book.title if hasattr(book, "title") else None
                            ),
                            "position": position,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        # Remove cache
        invalidate_cache(f"admin_series_items:{series_id}")
        invalidate_cache(f"admin_book_series:{series_id}")

        logger.info(f"Đã thêm sách {book_id} vào series {series_id}")
        return item
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi thêm sách vào series: {str(e)}")
        raise


async def update_series_item(
    db: Session, item_id: int, item_data: Dict[str, Any]
) -> BookSeriesItem:
    """
    Cập nhật thông tin mục series.

    Args:
        db: Database session
        item_id: ID của mục series
        item_data: Dữ liệu cập nhật

    Returns:
        Thông tin mục series đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy mục series
    """
    try:
        # Kiểm tra mục series tồn tại
        repo = BookSeriesRepository(db)
        item = await repo.get_series_item_by_id(item_id)

        if not item:
            logger.warning(f"Không tìm thấy mục series với ID {item_id}")
            raise NotFoundException(
                detail=f"Không tìm thấy mục series với ID {item_id}"
            )

        # Cập nhật mục series
        updated_item = await repo.update_series_item(item_id, item_data)

        logger.info(f"Đã cập nhật mục series với ID {item_id}")
        return updated_item
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật mục series: {str(e)}")
        raise


async def remove_book_from_series(
    db: Session, item_id: int, admin_id: Optional[int] = None
) -> None:
    """
    Xóa sách khỏi series.

    Args:
        db: Database session
        item_id: ID của mục series
        admin_id: ID của admin thực hiện hành động

    Raises:
        NotFoundException: Nếu không tìm thấy mục series
    """
    try:
        # Kiểm tra mục series tồn tại
        repo = BookSeriesRepository(db)
        item = await repo.get_series_item_by_id(item_id)

        if not item:
            logger.warning(f"Không tìm thấy mục series với ID {item_id}")
            raise NotFoundException(
                detail=f"Không tìm thấy mục series với ID {item_id}"
            )

        series_id = item.series_id

        # Get book and series details for logging
        book_repo = BookRepository(db)
        book = await book_repo.get_by_id(item.book_id)
        series = await repo.get_series_by_id(series_id)

        # Xóa mục series
        await repo.delete_series_item(item_id)

        # Cập nhật số lượng sách trong series
        await repo.update_series_total_books(series_id)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="REMOVE",
                        entity_type="BOOK_FROM_SERIES",
                        entity_id=item_id,
                        description=f"Removed book from series: {book.title if book else 'Unknown'} from {series.name if series else 'Unknown'}",
                        metadata={
                            "series_id": series_id,
                            "series_name": series.name if series else None,
                            "book_id": item.book_id,
                            "book_title": (
                                book.title if book and hasattr(book, "title") else None
                            ),
                            "position": (
                                item.position if hasattr(item, "position") else None
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        # Remove cache
        invalidate_cache(f"admin_series_items:{series_id}")
        invalidate_cache(f"admin_book_series:{series_id}")

        logger.info(f"Đã xóa mục series với ID {item_id}")
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi xóa mục series: {str(e)}")
        raise


@cached(key_prefix="admin_book_series_statistics", ttl=3600)
async def get_book_series_statistics(
    db: Session, admin_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Lấy thống kê về series sách.

    Args:
        db: Database session
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thống kê series sách
    """
    try:
        repo = BookSeriesRepository(db)

        # Đếm tổng số series sách
        total_series = await repo.count_series()

        # Đây là code demo, cần bổ sung các phương thức hỗ trợ trong repository
        stats = {
            "total_series": total_series,
            "series_with_most_books": [],  # Cần bổ sung phương thức get_series_with_most_books
            "most_popular_series": [],  # Cần bổ sung phương thức get_most_popular_series
            "average_books_per_series": 0,  # Cần bổ sung phương thức calculate_average_books_per_series
        }

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="BOOK_SERIES_STATISTICS",
                        entity_id=0,
                        description="Viewed book series statistics",
                        metadata=stats,
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return stats
    except Exception as e:
        logger.error(f"Lỗi khi lấy thống kê series sách: {str(e)}")
        raise
