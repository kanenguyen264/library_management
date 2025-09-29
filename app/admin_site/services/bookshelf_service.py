from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
import logging

from app.user_site.models.bookshelf import Bookshelf, BookshelfItem
from app.user_site.repositories.bookshelf_repo import BookshelfRepository
from app.user_site.repositories.user_repo import UserRepository
from app.user_site.repositories.book_repo import BookRepository
from app.core.exceptions import NotFoundException, ForbiddenException
from app.cache.decorators import cached, invalidate_cache
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate

# Logger cho bookshelf service
logger = logging.getLogger(__name__)


async def get_all_bookshelves(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    user_id: Optional[int] = None,
    only_public: bool = False,
    search_query: Optional[str] = None,
    admin_id: Optional[int] = None,
) -> List[Bookshelf]:
    """
    Lấy danh sách kệ sách với bộ lọc.

    Args:
        db: Database session
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về
        user_id: Lọc theo ID người dùng
        only_public: Chỉ lấy kệ sách công khai
        search_query: Chuỗi tìm kiếm
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách kệ sách
    """
    try:
        repo = BookshelfRepository(db)

        bookshelves = []
        if user_id:
            bookshelves = await repo.list_user_bookshelves(user_id, skip, limit)
        elif only_public:
            bookshelves = await repo.list_public_bookshelves(skip, limit, search_query)
        else:
            logger.warning("Yêu cầu lấy tất cả kệ sách không được hỗ trợ")

        # Log admin activity
        if admin_id:
            try:
                activity_description = "Viewed bookshelves"
                if user_id:
                    activity_description = f"Viewed bookshelves for user {user_id}"
                elif only_public:
                    activity_description = "Viewed public bookshelves"

                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="BOOKSHELVES",
                        entity_id=0,
                        description=activity_description,
                        metadata={
                            "skip": skip,
                            "limit": limit,
                            "user_id": user_id,
                            "only_public": only_public,
                            "search_query": search_query,
                            "results_count": len(bookshelves),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return bookshelves
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách kệ sách: {str(e)}")
        raise


async def count_bookshelves(
    db: Session,
    user_id: Optional[int] = None,
    only_public: bool = False,
    search_query: Optional[str] = None,
) -> int:
    """
    Đếm số lượng kệ sách.

    Args:
        db: Database session
        user_id: Lọc theo ID người dùng
        only_public: Chỉ đếm kệ sách công khai
        search_query: Chuỗi tìm kiếm

    Returns:
        Số lượng kệ sách
    """
    try:
        repo = BookshelfRepository(db)

        if user_id:
            return await repo.count_user_bookshelves(user_id)
        elif only_public:
            return await repo.count_public_bookshelves(search_query)
        else:
            logger.warning("Yêu cầu đếm tất cả kệ sách không được hỗ trợ")
            return 0
    except Exception as e:
        logger.error(f"Lỗi khi đếm kệ sách: {str(e)}")
        raise


@cached(key_prefix="admin_bookshelf", ttl=300)
async def get_bookshelf_by_id(
    db: Session,
    bookshelf_id: int,
    include_items: bool = False,
    admin_id: Optional[int] = None,
) -> Bookshelf:
    """
    Lấy thông tin kệ sách theo ID.

    Args:
        db: Database session
        bookshelf_id: ID của kệ sách
        include_items: Có load các sách trong kệ không
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin kệ sách

    Raises:
        NotFoundException: Nếu không tìm thấy kệ sách
    """
    try:
        repo = BookshelfRepository(db)
        bookshelf = await repo.get_bookshelf_by_id(bookshelf_id, include_items)

        if not bookshelf:
            logger.warning(f"Không tìm thấy kệ sách với ID {bookshelf_id}")
            raise NotFoundException(
                detail=f"Không tìm thấy kệ sách với ID {bookshelf_id}"
            )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="BOOKSHELF",
                        entity_id=bookshelf_id,
                        description=f"Viewed bookshelf details: {bookshelf.name}",
                        metadata={
                            "name": (
                                bookshelf.name if hasattr(bookshelf, "name") else None
                            ),
                            "user_id": (
                                bookshelf.user_id
                                if hasattr(bookshelf, "user_id")
                                else None
                            ),
                            "is_public": (
                                bookshelf.is_public
                                if hasattr(bookshelf, "is_public")
                                else None
                            ),
                            "include_items": include_items,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return bookshelf
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin kệ sách: {str(e)}")
        raise


async def create_bookshelf(
    db: Session, bookshelf_data: Dict[str, Any], admin_id: Optional[int] = None
) -> Bookshelf:
    """
    Tạo kệ sách mới.

    Args:
        db: Database session
        bookshelf_data: Dữ liệu kệ sách
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin kệ sách đã tạo

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng
        ForbiddenException: Nếu người dùng đã có kệ sách cùng tên
    """
    try:
        # Kiểm tra người dùng tồn tại
        user = None
        if "user_id" in bookshelf_data:
            user_repo = UserRepository(db)
            user = await user_repo.get_by_id(bookshelf_data["user_id"])

            if not user:
                logger.warning(
                    f"Không tìm thấy người dùng với ID {bookshelf_data['user_id']}"
                )
                raise NotFoundException(
                    detail=f"Không tìm thấy người dùng với ID {bookshelf_data['user_id']}"
                )

        # Kiểm tra kệ sách đã tồn tại
        repo = BookshelfRepository(db)
        if "name" in bookshelf_data and "user_id" in bookshelf_data:
            existing_bookshelf = await repo.get_bookshelf_by_name_and_user(
                bookshelf_data["name"], bookshelf_data["user_id"]
            )

            if existing_bookshelf:
                logger.warning(
                    f"Người dùng {bookshelf_data['user_id']} đã có kệ sách với tên {bookshelf_data['name']}"
                )
                raise ForbiddenException(
                    detail=f"Bạn đã có kệ sách với tên {bookshelf_data['name']}"
                )

        # Tạo kệ sách mới
        bookshelf = await repo.create_bookshelf(bookshelf_data)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="CREATE",
                        entity_type="BOOKSHELF",
                        entity_id=bookshelf.id,
                        description=f"Created new bookshelf: {bookshelf.name}",
                        metadata={
                            "name": (
                                bookshelf.name if hasattr(bookshelf, "name") else None
                            ),
                            "user_id": (
                                bookshelf.user_id
                                if hasattr(bookshelf, "user_id")
                                else None
                            ),
                            "username": (
                                user.username
                                if user and hasattr(user, "username")
                                else None
                            ),
                            "is_public": (
                                bookshelf.is_public
                                if hasattr(bookshelf, "is_public")
                                else None
                            ),
                            "description": (
                                bookshelf.description
                                if hasattr(bookshelf, "description")
                                else None
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        # Remove cache if user_id is present
        if "user_id" in bookshelf_data:
            invalidate_cache(f"admin_user_bookshelves:{bookshelf_data['user_id']}")

        logger.info(f"Đã tạo kệ sách mới với ID {bookshelf.id}")
        return bookshelf
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi tạo kệ sách: {str(e)}")
        raise


async def update_bookshelf(
    db: Session,
    bookshelf_id: int,
    bookshelf_data: Dict[str, Any],
    admin_id: Optional[int] = None,
) -> Bookshelf:
    """
    Cập nhật thông tin kệ sách.

    Args:
        db: Database session
        bookshelf_id: ID của kệ sách
        bookshelf_data: Dữ liệu cập nhật
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin kệ sách đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy kệ sách
        ForbiddenException: Nếu người dùng đã có kệ sách khác cùng tên
    """
    try:
        # Kiểm tra kệ sách tồn tại
        bookshelf = await get_bookshelf_by_id(db, bookshelf_id)

        # Kiểm tra xung đột tên nếu đổi tên
        if "name" in bookshelf_data and bookshelf_data["name"] != bookshelf.name:
            repo = BookshelfRepository(db)
            existing_bookshelf = await repo.get_bookshelf_by_name_and_user(
                bookshelf_data["name"], bookshelf.user_id
            )

            if existing_bookshelf and existing_bookshelf.id != bookshelf_id:
                logger.warning(
                    f"Người dùng {bookshelf.user_id} đã có kệ sách khác với tên {bookshelf_data['name']}"
                )
                raise ForbiddenException(
                    detail=f"Bạn đã có kệ sách khác với tên {bookshelf_data['name']}"
                )

        # Cập nhật kệ sách
        repo = BookshelfRepository(db)
        updated_bookshelf = await repo.update_bookshelf(bookshelf_id, bookshelf_data)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="BOOKSHELF",
                        entity_id=bookshelf_id,
                        description=f"Updated bookshelf: {updated_bookshelf.name}",
                        metadata={
                            "previous_name": bookshelf.name,
                            "user_id": bookshelf.user_id,
                            "updates": bookshelf_data,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        # Remove cache
        invalidate_cache(f"admin_bookshelf:{bookshelf_id}")
        if hasattr(bookshelf, "user_id") and bookshelf.user_id:
            invalidate_cache(f"admin_user_bookshelves:{bookshelf.user_id}")
        if hasattr(bookshelf, "is_public") and bookshelf.is_public:
            invalidate_cache("admin_public_bookshelves")

        logger.info(f"Đã cập nhật kệ sách với ID {bookshelf_id}")
        return updated_bookshelf
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật kệ sách: {str(e)}")
        raise


async def delete_bookshelf(
    db: Session, bookshelf_id: int, admin_id: Optional[int] = None
) -> None:
    """
    Xóa kệ sách.

    Args:
        db: Database session
        bookshelf_id: ID của kệ sách
        admin_id: ID của admin thực hiện hành động

    Raises:
        NotFoundException: Nếu không tìm thấy kệ sách
    """
    try:
        # Kiểm tra kệ sách tồn tại
        bookshelf = await get_bookshelf_by_id(db, bookshelf_id)

        # Log admin activity before deletion
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="DELETE",
                        entity_type="BOOKSHELF",
                        entity_id=bookshelf_id,
                        description=f"Deleted bookshelf: {bookshelf.name}",
                        metadata={
                            "name": bookshelf.name,
                            "user_id": bookshelf.user_id,
                            "is_public": (
                                bookshelf.is_public
                                if hasattr(bookshelf, "is_public")
                                else None
                            ),
                            "description": (
                                bookshelf.description
                                if hasattr(bookshelf, "description")
                                else None
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        # Xóa kệ sách
        repo = BookshelfRepository(db)
        await repo.delete_bookshelf(bookshelf_id)

        # Remove cache
        invalidate_cache(f"admin_bookshelf:{bookshelf_id}")
        invalidate_cache(f"admin_bookshelf_items:{bookshelf_id}")
        if hasattr(bookshelf, "user_id") and bookshelf.user_id:
            invalidate_cache(f"admin_user_bookshelves:{bookshelf.user_id}")
        if hasattr(bookshelf, "is_public") and bookshelf.is_public:
            invalidate_cache("admin_public_bookshelves")

        logger.info(f"Đã xóa kệ sách với ID {bookshelf_id}")
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi xóa kệ sách: {str(e)}")
        raise


@cached(key_prefix="admin_bookshelf_items", ttl=300)
async def get_bookshelf_items(
    db: Session, bookshelf_id: int, skip: int = 0, limit: int = 20
) -> List[BookshelfItem]:
    """
    Lấy danh sách các sách trong kệ sách.

    Args:
        db: Database session
        bookshelf_id: ID của kệ sách
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về

    Returns:
        Danh sách các sách trong kệ sách

    Raises:
        NotFoundException: Nếu không tìm thấy kệ sách
    """
    try:
        # Kiểm tra kệ sách tồn tại
        await get_bookshelf_by_id(db, bookshelf_id)

        # Lấy danh sách các sách
        repo = BookshelfRepository(db)
        items = await repo.list_bookshelf_items(bookshelf_id, skip, limit)

        return items
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách sách trong kệ sách: {str(e)}")
        raise


async def count_bookshelf_items(db: Session, bookshelf_id: int) -> int:
    """
    Đếm số lượng sách trong kệ sách.

    Args:
        db: Database session
        bookshelf_id: ID của kệ sách

    Returns:
        Số lượng sách trong kệ sách

    Raises:
        NotFoundException: Nếu không tìm thấy kệ sách
    """
    try:
        # Kiểm tra kệ sách tồn tại
        await get_bookshelf_by_id(db, bookshelf_id)

        # Đếm số lượng sách
        repo = BookshelfRepository(db)
        count = await repo.count_bookshelf_items(bookshelf_id)

        return count
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi đếm số lượng sách trong kệ sách: {str(e)}")
        raise


async def add_book_to_bookshelf(
    db: Session,
    bookshelf_id: int,
    book_id: int,
    note: Optional[str] = None,
    admin_id: Optional[int] = None,
) -> BookshelfItem:
    """
    Thêm sách vào kệ sách.

    Args:
        db: Database session
        bookshelf_id: ID của kệ sách
        book_id: ID của sách
        note: Ghi chú
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin mục kệ sách đã tạo

    Raises:
        NotFoundException: Nếu không tìm thấy kệ sách hoặc sách
    """
    try:
        # Kiểm tra kệ sách tồn tại
        bookshelf = await get_bookshelf_by_id(db, bookshelf_id)

        # Kiểm tra sách tồn tại
        book_repo = BookRepository(db)
        book = await book_repo.get_by_id(book_id)

        if not book:
            logger.warning(f"Không tìm thấy sách với ID {book_id}")
            raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

        # Thêm sách vào kệ sách (repository đã xử lý trường hợp sách đã tồn tại trong kệ)
        bookshelf_repo = BookshelfRepository(db)
        item = await bookshelf_repo.add_book_to_bookshelf(bookshelf_id, book_id, note)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="ADD",
                        entity_type="BOOK_TO_BOOKSHELF",
                        entity_id=item.id,
                        description=f"Added book to bookshelf: {book.title if hasattr(book, 'title') else f'ID:{book_id}'} to {bookshelf.name}",
                        metadata={
                            "bookshelf_id": bookshelf_id,
                            "bookshelf_name": bookshelf.name,
                            "book_id": book_id,
                            "book_title": (
                                book.title if hasattr(book, "title") else None
                            ),
                            "user_id": bookshelf.user_id,
                            "note": note,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        # Remove cache
        invalidate_cache(f"admin_bookshelf_items:{bookshelf_id}")

        logger.info(f"Đã thêm sách {book_id} vào kệ sách {bookshelf_id}")
        return item
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi thêm sách vào kệ sách: {str(e)}")
        raise


async def update_bookshelf_item(
    db: Session, item_id: int, item_data: Dict[str, Any]
) -> BookshelfItem:
    """
    Cập nhật thông tin mục kệ sách.

    Args:
        db: Database session
        item_id: ID của mục kệ sách
        item_data: Dữ liệu cập nhật

    Returns:
        Thông tin mục kệ sách đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy mục kệ sách
    """
    try:
        # Kiểm tra mục kệ sách tồn tại
        repo = BookshelfRepository(db)
        item = await repo.get_bookshelf_item_by_id(item_id)

        if not item:
            logger.warning(f"Không tìm thấy mục kệ sách với ID {item_id}")
            raise NotFoundException(
                detail=f"Không tìm thấy mục kệ sách với ID {item_id}"
            )

        # Cập nhật mục kệ sách
        updated_item = await repo.update_bookshelf_item(item_id, item_data)

        logger.info(f"Đã cập nhật mục kệ sách với ID {item_id}")
        return updated_item
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật mục kệ sách: {str(e)}")
        raise


async def remove_book_from_bookshelf(
    db: Session, item_id: int, admin_id: Optional[int] = None
) -> None:
    """
    Xóa sách khỏi kệ sách.

    Args:
        db: Database session
        item_id: ID của mục kệ sách
        admin_id: ID của admin thực hiện hành động

    Raises:
        NotFoundException: Nếu không tìm thấy mục kệ sách
    """
    try:
        # Kiểm tra mục kệ sách tồn tại
        repo = BookshelfRepository(db)
        item = await repo.get_bookshelf_item_by_id(item_id)

        if not item:
            logger.warning(f"Không tìm thấy mục kệ sách với ID {item_id}")
            raise NotFoundException(
                detail=f"Không tìm thấy mục kệ sách với ID {item_id}"
            )

        bookshelf_id = item.bookshelf_id

        # Get additional info for logging
        bookshelf = await repo.get_bookshelf_by_id(bookshelf_id)
        book_repo = BookRepository(db)
        book = await book_repo.get_by_id(item.book_id)

        # Log admin activity before deletion
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="REMOVE",
                        entity_type="BOOK_FROM_BOOKSHELF",
                        entity_id=item_id,
                        description=f"Removed book from bookshelf: {book.title if book and hasattr(book, 'title') else f'ID:{item.book_id}'} from {bookshelf.name if bookshelf else f'ID:{bookshelf_id}'}",
                        metadata={
                            "bookshelf_id": bookshelf_id,
                            "bookshelf_name": bookshelf.name if bookshelf else None,
                            "book_id": item.book_id,
                            "book_title": (
                                book.title if book and hasattr(book, "title") else None
                            ),
                            "user_id": bookshelf.user_id if bookshelf else None,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        # Xóa mục kệ sách
        await repo.delete_bookshelf_item(item_id)

        # Remove cache
        invalidate_cache(f"admin_bookshelf_items:{bookshelf_id}")

        logger.info(f"Đã xóa mục kệ sách với ID {item_id}")
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi xóa mục kệ sách: {str(e)}")
        raise


@cached(key_prefix="admin_user_bookshelves", ttl=300)
async def get_user_bookshelves(
    db: Session, user_id: int, skip: int = 0, limit: int = 20
) -> List[Bookshelf]:
    """
    Lấy danh sách kệ sách của người dùng.

    Args:
        db: Database session
        user_id: ID của người dùng
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về

    Returns:
        Danh sách kệ sách của người dùng

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng
    """
    try:
        # Kiểm tra người dùng tồn tại
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)

        if not user:
            logger.warning(f"Không tìm thấy người dùng với ID {user_id}")
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        # Lấy danh sách kệ sách
        repo = BookshelfRepository(db)
        bookshelves = await repo.list_user_bookshelves(user_id, skip, limit)

        return bookshelves
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách kệ sách của người dùng: {str(e)}")
        raise


@cached(key_prefix="admin_public_bookshelves", ttl=300)
async def get_public_bookshelves(
    db: Session, skip: int = 0, limit: int = 20, search_query: Optional[str] = None
) -> List[Bookshelf]:
    """
    Lấy danh sách kệ sách công khai.

    Args:
        db: Database session
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về
        search_query: Chuỗi tìm kiếm

    Returns:
        Danh sách kệ sách công khai
    """
    try:
        repo = BookshelfRepository(db)
        bookshelves = await repo.list_public_bookshelves(skip, limit, search_query)

        return bookshelves
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách kệ sách công khai: {str(e)}")
        raise


async def get_default_bookshelf(db: Session, user_id: int) -> Bookshelf:
    """
    Lấy kệ sách mặc định của người dùng, tạo mới nếu chưa có.

    Args:
        db: Database session
        user_id: ID của người dùng

    Returns:
        Kệ sách mặc định

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng
    """
    try:
        # Kiểm tra người dùng tồn tại
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)

        if not user:
            logger.warning(f"Không tìm thấy người dùng với ID {user_id}")
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        # Lấy kệ sách mặc định
        repo = BookshelfRepository(db)
        bookshelf = await repo.get_default_bookshelf(user_id)

        return bookshelf
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy kệ sách mặc định: {str(e)}")
        raise


async def toggle_bookshelf_visibility(db: Session, bookshelf_id: int) -> Bookshelf:
    """
    Chuyển đổi trạng thái công khai của kệ sách.

    Args:
        db: Database session
        bookshelf_id: ID của kệ sách

    Returns:
        Thông tin kệ sách đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy kệ sách
    """
    try:
        # Lấy thông tin kệ sách
        bookshelf = await get_bookshelf_by_id(db, bookshelf_id)

        # Chuyển đổi trạng thái công khai
        new_status = not bookshelf.is_public

        # Cập nhật trạng thái
        repo = BookshelfRepository(db)
        updated_bookshelf = await repo.update_bookshelf(
            bookshelf_id, {"is_public": new_status}
        )

        logger.info(
            f"Đã chuyển đổi trạng thái công khai của kệ sách {bookshelf_id} thành {new_status}"
        )
        return updated_bookshelf
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi chuyển đổi trạng thái công khai: {str(e)}")
        raise


async def get_user_book_bookshelves(
    db: Session, user_id: int, book_id: int
) -> List[Bookshelf]:
    """
    Lấy danh sách kệ sách của người dùng có chứa một cuốn sách cụ thể.

    Args:
        db: Database session
        user_id: ID của người dùng
        book_id: ID của sách

    Returns:
        Danh sách kệ sách

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng hoặc sách
    """
    try:
        # Kiểm tra người dùng tồn tại
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)

        if not user:
            logger.warning(f"Không tìm thấy người dùng với ID {user_id}")
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        # Kiểm tra sách tồn tại
        book_repo = BookRepository(db)
        book = await book_repo.get_by_id(book_id)

        if not book:
            logger.warning(f"Không tìm thấy sách với ID {book_id}")
            raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

        # Lấy danh sách kệ sách có chứa sách
        repo = BookshelfRepository(db)
        bookshelves = await repo.get_user_book_bookshelves(user_id, book_id)

        return bookshelves
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách kệ sách chứa sách: {str(e)}")
        raise


async def remove_book_from_all_bookshelves(
    db: Session, user_id: int, book_id: int
) -> None:
    """
    Xóa sách khỏi tất cả kệ sách của người dùng.

    Args:
        db: Database session
        user_id: ID của người dùng
        book_id: ID của sách

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng hoặc sách
    """
    try:
        # Kiểm tra người dùng tồn tại
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)

        if not user:
            logger.warning(f"Không tìm thấy người dùng với ID {user_id}")
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        # Kiểm tra sách tồn tại
        book_repo = BookRepository(db)
        book = await book_repo.get_by_id(book_id)

        if not book:
            logger.warning(f"Không tìm thấy sách với ID {book_id}")
            raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

        # Xóa sách khỏi tất cả kệ sách
        repo = BookshelfRepository(db)
        await repo.remove_book_from_all_bookshelves(user_id, book_id)

        logger.info(
            f"Đã xóa sách {book_id} khỏi tất cả kệ sách của người dùng {user_id}"
        )
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi xóa sách khỏi tất cả kệ sách: {str(e)}")
        raise


@cached(key_prefix="admin_bookshelf_statistics", ttl=3600)
async def get_bookshelf_statistics(
    db: Session, admin_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Lấy thống kê về kệ sách.

    Args:
        db: Database session
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thống kê kệ sách
    """
    try:
        repo = BookshelfRepository(db)

        # Đếm tổng số kệ sách công khai
        public_count = await repo.count_public_bookshelves()

        # Đây là code demo, cần bổ sung các phương thức hỗ trợ trong repository
        stats = {
            "total_public_bookshelves": public_count,
            "users_with_most_bookshelves": [],  # Cần bổ sung phương thức get_users_with_most_bookshelves
            "most_popular_bookshelves": [],  # Cần bổ sung phương thức get_most_popular_bookshelves
            "most_added_books": [],  # Cần bổ sung phương thức get_most_added_books
        }

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="BOOKSHELF_STATISTICS",
                        entity_id=0,
                        description="Viewed bookshelf statistics",
                        metadata=stats,
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return stats
    except Exception as e:
        logger.error(f"Lỗi khi lấy thống kê kệ sách: {str(e)}")
        raise
