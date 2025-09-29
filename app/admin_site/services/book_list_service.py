from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
import logging

from app.user_site.models.book_list import UserBookList, UserBookListItem
from app.user_site.repositories.book_list_repo import BookListRepository
from app.user_site.repositories.user_repo import UserRepository
from app.user_site.repositories.book_repo import BookRepository
from app.core.exceptions import NotFoundException, ForbiddenException
from app.common.utils.cache import cached
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate

# Logger cho book list service
logger = logging.getLogger(__name__)


async def get_all_book_lists(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    user_id: Optional[int] = None,
    only_public: bool = False,
    search_query: Optional[str] = None,
) -> List[UserBookList]:
    """
    Lấy danh sách các danh sách sách với bộ lọc.

    Args:
        db: Database session
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về
        user_id: Lọc theo ID người dùng
        only_public: Chỉ lấy danh sách công khai
        search_query: Chuỗi tìm kiếm

    Returns:
        Danh sách các danh sách sách
    """
    try:
        repo = BookListRepository(db)

        if user_id:
            return await repo.list_user_book_lists(user_id, skip, limit)
        elif only_public:
            return await repo.list_public_book_lists(skip, limit, search_query)
        else:
            logger.warning("Yêu cầu lấy tất cả danh sách sách không được hỗ trợ")
            return []
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách sách: {str(e)}")
        raise


async def count_book_lists(
    db: Session,
    user_id: Optional[int] = None,
    only_public: bool = False,
    search_query: Optional[str] = None,
) -> int:
    """
    Đếm số lượng danh sách sách.

    Args:
        db: Database session
        user_id: Lọc theo ID người dùng
        only_public: Chỉ đếm danh sách công khai
        search_query: Chuỗi tìm kiếm

    Returns:
        Số lượng danh sách sách
    """
    try:
        repo = BookListRepository(db)

        if user_id:
            return await repo.count_user_book_lists(user_id)
        elif only_public:
            return await repo.count_public_book_lists(search_query)
        else:
            logger.warning("Yêu cầu đếm tất cả danh sách sách không được hỗ trợ")
            return 0
    except Exception as e:
        logger.error(f"Lỗi khi đếm danh sách sách: {str(e)}")
        raise


@cached(key_prefix="admin_book_list", ttl=300)
async def get_book_list_by_id(
    db: Session, list_id: int, include_items: bool = False
) -> UserBookList:
    """
    Lấy thông tin danh sách sách theo ID.

    Args:
        db: Database session
        list_id: ID của danh sách sách
        include_items: Có load các sách trong danh sách không

    Returns:
        Thông tin danh sách sách

    Raises:
        NotFoundException: Nếu không tìm thấy danh sách sách
    """
    try:
        repo = BookListRepository(db)
        book_list = await repo.get_list_by_id(list_id, include_items)

        if not book_list:
            logger.warning(f"Không tìm thấy danh sách sách với ID {list_id}")
            raise NotFoundException(
                detail=f"Không tìm thấy danh sách sách với ID {list_id}"
            )

        return book_list
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin danh sách sách: {str(e)}")
        raise


async def create_book_list(db: Session, list_data: Dict[str, Any]) -> UserBookList:
    """
    Tạo danh sách sách mới.

    Args:
        db: Database session
        list_data: Dữ liệu danh sách sách

    Returns:
        Thông tin danh sách sách đã tạo

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng
        ForbiddenException: Nếu người dùng đã có danh sách cùng tên
    """
    try:
        # Kiểm tra người dùng tồn tại
        if "user_id" in list_data:
            user_repo = UserRepository(db)
            user = await user_repo.get_by_id(list_data["user_id"])

            if not user:
                logger.warning(
                    f"Không tìm thấy người dùng với ID {list_data['user_id']}"
                )
                raise NotFoundException(
                    detail=f"Không tìm thấy người dùng với ID {list_data['user_id']}"
                )

        # Kiểm tra danh sách sách đã tồn tại
        repo = BookListRepository(db)
        if "title" in list_data and "user_id" in list_data:
            existing_list = await repo.get_list_by_title_and_user(
                list_data["title"], list_data["user_id"]
            )

            if existing_list:
                logger.warning(
                    f"Người dùng {list_data['user_id']} đã có danh sách sách với tên {list_data['title']}"
                )
                raise ForbiddenException(
                    detail=f"Bạn đã có danh sách sách với tên {list_data['title']}"
                )

        # Tạo danh sách sách mới
        book_list = await repo.create_list(list_data)

        logger.info(f"Đã tạo danh sách sách mới với ID {book_list.id}")
        return book_list
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi tạo danh sách sách: {str(e)}")
        raise


async def update_book_list(
    db: Session, list_id: int, list_data: Dict[str, Any]
) -> UserBookList:
    """
    Cập nhật thông tin danh sách sách.

    Args:
        db: Database session
        list_id: ID của danh sách sách
        list_data: Dữ liệu cập nhật

    Returns:
        Thông tin danh sách sách đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy danh sách sách
        ForbiddenException: Nếu người dùng đã có danh sách khác cùng tên
    """
    try:
        # Kiểm tra danh sách sách tồn tại
        book_list = await get_book_list_by_id(db, list_id)

        # Kiểm tra xung đột tên nếu đổi tên
        if "title" in list_data and list_data["title"] != book_list.title:
            repo = BookListRepository(db)
            existing_list = await repo.get_list_by_title_and_user(
                list_data["title"], book_list.user_id
            )

            if existing_list and existing_list.id != list_id:
                logger.warning(
                    f"Người dùng {book_list.user_id} đã có danh sách sách khác với tên {list_data['title']}"
                )
                raise ForbiddenException(
                    detail=f"Bạn đã có danh sách sách khác với tên {list_data['title']}"
                )

        # Cập nhật danh sách sách
        repo = BookListRepository(db)
        updated_list = await repo.update_list(list_id, list_data)

        logger.info(f"Đã cập nhật danh sách sách với ID {list_id}")
        return updated_list
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật danh sách sách: {str(e)}")
        raise


async def delete_book_list(db: Session, list_id: int) -> None:
    """
    Xóa danh sách sách.

    Args:
        db: Database session
        list_id: ID của danh sách sách

    Raises:
        NotFoundException: Nếu không tìm thấy danh sách sách
    """
    try:
        # Kiểm tra danh sách sách tồn tại
        await get_book_list_by_id(db, list_id)

        # Xóa danh sách sách
        repo = BookListRepository(db)
        await repo.delete_list(list_id)

        logger.info(f"Đã xóa danh sách sách với ID {list_id}")
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi xóa danh sách sách: {str(e)}")
        raise


@cached(key_prefix="admin_book_list_items", ttl=300)
async def get_book_list_items(
    db: Session, list_id: int, skip: int = 0, limit: int = 20
) -> List[UserBookListItem]:
    """
    Lấy danh sách các sách trong danh sách sách.

    Args:
        db: Database session
        list_id: ID của danh sách sách
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về

    Returns:
        Danh sách các sách trong danh sách sách

    Raises:
        NotFoundException: Nếu không tìm thấy danh sách sách
    """
    try:
        # Kiểm tra danh sách sách tồn tại
        await get_book_list_by_id(db, list_id)

        # Lấy danh sách các sách
        repo = BookListRepository(db)
        items = await repo.list_list_items(list_id, skip, limit)

        return items
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách sách trong danh sách sách: {str(e)}")
        raise


async def count_book_list_items(db: Session, list_id: int) -> int:
    """
    Đếm số lượng sách trong danh sách sách.

    Args:
        db: Database session
        list_id: ID của danh sách sách

    Returns:
        Số lượng sách trong danh sách sách

    Raises:
        NotFoundException: Nếu không tìm thấy danh sách sách
    """
    try:
        # Kiểm tra danh sách sách tồn tại
        await get_book_list_by_id(db, list_id)

        # Đếm số lượng sách
        repo = BookListRepository(db)
        count = await repo.count_list_items(list_id)

        return count
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi đếm số lượng sách trong danh sách sách: {str(e)}")
        raise


async def add_book_to_list(
    db: Session,
    list_id: int,
    book_id: int,
    note: Optional[str] = None,
    position: Optional[int] = None,
) -> UserBookListItem:
    """
    Thêm sách vào danh sách sách.

    Args:
        db: Database session
        list_id: ID của danh sách sách
        book_id: ID của sách
        note: Ghi chú
        position: Vị trí trong danh sách

    Returns:
        Thông tin mục danh sách sách đã tạo

    Raises:
        NotFoundException: Nếu không tìm thấy danh sách sách hoặc sách
        ForbiddenException: Nếu sách đã tồn tại trong danh sách
    """
    try:
        # Kiểm tra danh sách sách tồn tại
        await get_book_list_by_id(db, list_id)

        # Kiểm tra sách tồn tại
        book_repo = BookRepository(db)
        book = await book_repo.get_by_id(book_id)

        if not book:
            logger.warning(f"Không tìm thấy sách với ID {book_id}")
            raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

        # Kiểm tra sách đã có trong danh sách chưa
        list_repo = BookListRepository(db)
        existing_item = await list_repo.get_list_item_by_book(list_id, book_id)

        if existing_item:
            logger.warning(f"Sách {book_id} đã tồn tại trong danh sách sách {list_id}")
            raise ForbiddenException(detail=f"Sách đã tồn tại trong danh sách")

        # Thêm sách vào danh sách
        item_data = {"list_id": list_id, "book_id": book_id}

        if note:
            item_data["note"] = note

        if position is not None:
            item_data["position"] = position

        item = await list_repo.create_list_item(item_data)

        logger.info(f"Đã thêm sách {book_id} vào danh sách sách {list_id}")
        return item
    except (NotFoundException, ForbiddenException):
        raise
    except Exception as e:
        logger.error(f"Lỗi khi thêm sách vào danh sách sách: {str(e)}")
        raise


async def update_book_list_item(
    db: Session, item_id: int, item_data: Dict[str, Any]
) -> UserBookListItem:
    """
    Cập nhật thông tin mục danh sách sách.

    Args:
        db: Database session
        item_id: ID của mục danh sách sách
        item_data: Dữ liệu cập nhật

    Returns:
        Thông tin mục danh sách sách đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy mục danh sách sách
    """
    try:
        # Kiểm tra mục danh sách sách tồn tại
        repo = BookListRepository(db)
        item = await repo.get_list_item_by_id(item_id)

        if not item:
            logger.warning(f"Không tìm thấy mục danh sách sách với ID {item_id}")
            raise NotFoundException(
                detail=f"Không tìm thấy mục danh sách sách với ID {item_id}"
            )

        # Cập nhật mục danh sách sách
        updated_item = await repo.update_list_item(item_id, item_data)

        logger.info(f"Đã cập nhật mục danh sách sách với ID {item_id}")
        return updated_item
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật mục danh sách sách: {str(e)}")
        raise


async def remove_book_from_list(db: Session, item_id: int) -> None:
    """
    Xóa sách khỏi danh sách sách.

    Args:
        db: Database session
        item_id: ID của mục danh sách sách

    Raises:
        NotFoundException: Nếu không tìm thấy mục danh sách sách
    """
    try:
        # Kiểm tra mục danh sách sách tồn tại
        repo = BookListRepository(db)
        item = await repo.get_list_item_by_id(item_id)

        if not item:
            logger.warning(f"Không tìm thấy mục danh sách sách với ID {item_id}")
            raise NotFoundException(
                detail=f"Không tìm thấy mục danh sách sách với ID {item_id}"
            )

        # Xóa mục danh sách sách
        await repo.delete_list_item(item_id)

        logger.info(f"Đã xóa mục danh sách sách với ID {item_id}")
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi xóa mục danh sách sách: {str(e)}")
        raise


@cached(key_prefix="admin_user_book_lists", ttl=300)
async def get_user_book_lists(
    db: Session, user_id: int, skip: int = 0, limit: int = 20
) -> List[UserBookList]:
    """
    Lấy danh sách các danh sách sách của người dùng.

    Args:
        db: Database session
        user_id: ID của người dùng
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về

    Returns:
        Danh sách các danh sách sách của người dùng

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

        # Lấy danh sách các danh sách sách
        repo = BookListRepository(db)
        lists = await repo.list_user_book_lists(user_id, skip, limit)

        return lists
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy danh sách các danh sách sách của người dùng: {str(e)}"
        )
        raise


@cached(key_prefix="admin_public_book_lists", ttl=300)
async def get_public_book_lists(
    db: Session, skip: int = 0, limit: int = 20, search_query: Optional[str] = None
) -> List[UserBookList]:
    """
    Lấy danh sách các danh sách sách công khai.

    Args:
        db: Database session
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về
        search_query: Chuỗi tìm kiếm

    Returns:
        Danh sách các danh sách sách công khai
    """
    try:
        repo = BookListRepository(db)
        lists = await repo.list_public_book_lists(skip, limit, search_query)

        return lists
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách các danh sách sách công khai: {str(e)}")
        raise


async def toggle_book_list_visibility(db: Session, list_id: int) -> UserBookList:
    """
    Chuyển đổi trạng thái công khai của danh sách sách.

    Args:
        db: Database session
        list_id: ID của danh sách sách

    Returns:
        Thông tin danh sách sách đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy danh sách sách
    """
    try:
        # Lấy thông tin danh sách sách
        book_list = await get_book_list_by_id(db, list_id)

        # Chuyển đổi trạng thái công khai
        new_status = not book_list.is_public

        # Cập nhật trạng thái
        repo = BookListRepository(db)
        updated_list = await repo.update_list(list_id, {"is_public": new_status})

        logger.info(
            f"Đã chuyển đổi trạng thái công khai của danh sách sách {list_id} thành {new_status}"
        )
        return updated_list
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi chuyển đổi trạng thái công khai: {str(e)}")
        raise


@cached(key_prefix="admin_book_list_statistics", ttl=3600)
async def get_book_list_statistics(db: Session) -> Dict[str, Any]:
    """
    Lấy thống kê về danh sách sách.

    Args:
        db: Database session

    Returns:
        Thống kê danh sách sách
    """
    try:
        repo = BookListRepository(db)

        # Đếm tổng số danh sách sách công khai
        public_count = await repo.count_public_book_lists()

        # Đây là code demo, cần bổ sung các phương thức hỗ trợ trong repository
        stats = {
            "total_public_lists": public_count,
            "most_popular_lists": [],  # Cần bổ sung phương thức get_most_popular_lists
            "users_with_most_lists": [],  # Cần bổ sung phương thức get_users_with_most_lists
            "most_included_books": [],  # Cần bổ sung phương thức get_most_included_books
        }

        return stats
    except Exception as e:
        logger.error(f"Lỗi khi lấy thống kê danh sách sách: {str(e)}")
        raise
