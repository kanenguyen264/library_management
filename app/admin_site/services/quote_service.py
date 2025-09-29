from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
import logging

from app.user_site.models.quote import Quote, QuoteLike
from app.user_site.repositories.quote_repo import QuoteRepository
from app.user_site.repositories.user_repo import UserRepository
from app.user_site.repositories.book_repo import BookRepository
from app.core.exceptions import NotFoundException, ForbiddenException, ConflictException
from app.common.utils.cache import cached, remove_cache
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate

# Logger cho quote service
logger = logging.getLogger(__name__)


async def get_all_quotes(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    user_id: Optional[int] = None,
    book_id: Optional[int] = None,
    only_public: bool = None,
    search_query: Optional[str] = None,
    sort_by: str = "created_at",
    sort_desc: bool = True,
    admin_id: Optional[int] = None,
) -> List[Quote]:
    """
    Lấy danh sách trích dẫn với bộ lọc.

    Args:
        db: Database session
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về
        user_id: Lọc theo ID người dùng
        book_id: Lọc theo ID sách
        only_public: Chỉ lấy trích dẫn công khai
        search_query: Chuỗi tìm kiếm
        sort_by: Sắp xếp theo trường
        sort_desc: Sắp xếp giảm dần
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách trích dẫn
    """
    try:
        repo = QuoteRepository(db)

        if user_id:
            quotes = await repo.list_by_user(
                user_id=user_id,
                skip=skip,
                limit=limit,
                only_public=only_public,
                with_relations=True,
            )
        elif book_id:
            quotes = await repo.list_by_book(
                book_id=book_id,
                skip=skip,
                limit=limit,
                only_public=only_public,
                with_relations=True,
            )
        else:
            # Repository hiện tại không có phương thức list_all nên cần phát triển thêm
            # Đây là một giải pháp tạm thời
            logger.warning(
                "Chưa có phương thức để lấy tất cả trích dẫn, bổ sung vào repository"
            )
            quotes = []

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="QUOTES",
                        entity_id=0,
                        description="Viewed quote list",
                        metadata={
                            "skip": skip,
                            "limit": limit,
                            "book_id": book_id,
                            "user_id": user_id,
                            "sort_by": sort_by,
                            "sort_desc": sort_desc,
                            "results_count": len(quotes),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return quotes
    except Exception as e:
        logger.error(f"Error retrieving quotes: {str(e)}")
        raise


async def count_quotes(
    db: Session,
    user_id: Optional[int] = None,
    book_id: Optional[int] = None,
    only_public: bool = None,
) -> int:
    """
    Đếm số lượng trích dẫn.

    Args:
        db: Database session
        user_id: Lọc theo ID người dùng
        book_id: Lọc theo ID sách
        only_public: Chỉ đếm trích dẫn công khai

    Returns:
        Số lượng trích dẫn
    """
    try:
        repo = QuoteRepository(db)

        if user_id:
            return await repo.count_by_user(user_id, only_public)
        elif book_id:
            return await repo.count_by_book(book_id, only_public)
        else:
            # Repository hiện tại không có phương thức count_all
            logger.warning(
                "Chưa có phương thức để đếm tất cả trích dẫn, bổ sung vào repository"
            )
            return 0

    except Exception as e:
        logger.error(f"Lỗi khi đếm trích dẫn: {str(e)}")
        raise


@cached(key_prefix="admin_quote", ttl=300)
async def get_quote_by_id(
    db: Session,
    quote_id: int,
    with_relations: bool = True,
    admin_id: Optional[int] = None,
) -> Quote:
    """
    Lấy thông tin trích dẫn theo ID.

    Args:
        db: Database session
        quote_id: ID của trích dẫn
        with_relations: Có load các mối quan hệ không
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin trích dẫn

    Raises:
        NotFoundException: Nếu không tìm thấy trích dẫn
    """
    try:
        repo = QuoteRepository(db)
        quote = await repo.get_by_id(quote_id, with_relations)

        if not quote:
            logger.warning(f"Không tìm thấy trích dẫn với ID {quote_id}")
            raise NotFoundException(
                detail=f"Không tìm thấy trích dẫn với ID {quote_id}"
            )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="QUOTE",
                        entity_id=quote_id,
                        description=f"Viewed quote details for book {quote.book_id}",
                        metadata={
                            "book_id": quote.book_id,
                            "user_id": quote.user_id,
                            "page_number": quote.page_number,
                            "content_length": len(quote.content),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return quote
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving quote: {str(e)}")
        raise


async def create_quote(
    db: Session, quote_data: Dict[str, Any], admin_id: Optional[int] = None
) -> Quote:
    """
    Tạo trích dẫn mới.

    Args:
        db: Database session
        quote_data: Dữ liệu trích dẫn
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin trích dẫn đã tạo

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng hoặc sách
        ConflictException: Nếu trích dẫn đã tồn tại
    """
    try:
        # Kiểm tra người dùng tồn tại
        if "user_id" in quote_data:
            user_repo = UserRepository(db)
            user = await user_repo.get_by_id(quote_data["user_id"])

            if not user:
                logger.warning(
                    f"Không tìm thấy người dùng với ID {quote_data['user_id']}"
                )
                raise NotFoundException(
                    detail=f"Không tìm thấy người dùng với ID {quote_data['user_id']}"
                )

        # Kiểm tra sách tồn tại
        if "book_id" in quote_data:
            book_repo = BookRepository(db)
            book = await book_repo.get_by_id(quote_data["book_id"])

            if not book:
                logger.warning(f"Không tìm thấy sách với ID {quote_data['book_id']}")
                raise NotFoundException(
                    detail=f"Không tìm thấy sách với ID {quote_data['book_id']}"
                )

        # Kiểm tra xem trích dẫn đã tồn tại chưa
        repo = QuoteRepository(db)
        existing_quote = await repo.get_by_book_and_page(
            book_id=quote_data["book_id"], page_number=quote_data["page_number"]
        )

        if existing_quote:
            logger.warning(
                f"Quote already exists for book {quote_data['book_id']} at page {quote_data['page_number']}"
            )
            raise ConflictException(
                detail=f"Trích dẫn đã tồn tại cho sách này ở trang {quote_data['page_number']}"
            )

        # Tạo trích dẫn mới
        quote = await repo.create(quote_data)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="CREATE",
                        entity_type="QUOTE",
                        entity_id=quote.id,
                        description=f"Created quote for book {quote.book_id}",
                        metadata={
                            "book_id": quote.book_id,
                            "user_id": quote.user_id,
                            "page_number": quote.page_number,
                            "content_length": len(quote.content),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Đã tạo trích dẫn mới với ID {quote.id}")
        return quote
    except NotFoundException:
        raise
    except ConflictException:
        raise
    except Exception as e:
        logger.error(f"Error creating quote: {str(e)}")
        raise


async def update_quote(
    db: Session,
    quote_id: int,
    quote_data: Dict[str, Any],
    admin_id: Optional[int] = None,
) -> Quote:
    """
    Cập nhật thông tin trích dẫn.

    Args:
        db: Database session
        quote_id: ID của trích dẫn
        quote_data: Dữ liệu cập nhật
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin trích dẫn đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy trích dẫn
    """
    try:
        # Kiểm tra trích dẫn tồn tại
        await get_quote_by_id(db, quote_id, False)

        # Cập nhật trích dẫn
        repo = QuoteRepository(db)
        quote = await repo.update(quote_id, quote_data)

        # Xóa cache
        remove_cache(f"admin_quote:{quote_id}")

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="QUOTE",
                        entity_id=quote_id,
                        description=f"Updated quote for book {quote.book_id}",
                        metadata={
                            "book_id": quote.book_id,
                            "user_id": quote.user_id,
                            "updated_fields": list(quote_data.keys()),
                            "old_values": {
                                k: getattr(quote, k) for k in quote_data.keys()
                            },
                            "new_values": {
                                k: getattr(quote, k) for k in quote_data.keys()
                            },
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Đã cập nhật trích dẫn với ID {quote_id}")
        return quote
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error updating quote: {str(e)}")
        raise


async def delete_quote(
    db: Session, quote_id: int, admin_id: Optional[int] = None
) -> None:
    """
    Xóa trích dẫn.

    Args:
        db: Database session
        quote_id: ID của trích dẫn
        admin_id: ID của admin thực hiện hành động

    Raises:
        NotFoundException: Nếu không tìm thấy trích dẫn
    """
    try:
        # Kiểm tra trích dẫn tồn tại và lưu lại để sử dụng trong logging
        current_quote = await get_quote_by_id(db, quote_id)

        repo = QuoteRepository(db)
        await repo.delete(quote_id)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="DELETE",
                        entity_type="QUOTE",
                        entity_id=quote_id,
                        description=f"Deleted quote - ID: {current_quote.id}",
                        metadata={
                            "quote_id": current_quote.id,
                            "content": current_quote.content,
                            "book_id": current_quote.book_id,
                            "user_id": current_quote.user_id,
                            "chapter": current_quote.chapter,
                            "likes_count": current_quote.likes_count,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Deleted quote with ID {quote_id}")
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error deleting quote: {str(e)}")
        raise


async def like_quote(db: Session, user_id: int, quote_id: int) -> QuoteLike:
    """
    Thích trích dẫn.

    Args:
        db: Database session
        user_id: ID của người dùng
        quote_id: ID của trích dẫn

    Returns:
        Thông tin lượt thích

    Raises:
        NotFoundException: Nếu không tìm thấy trích dẫn hoặc người dùng
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

        # Kiểm tra trích dẫn tồn tại
        await get_quote_by_id(db, quote_id, False)

        # Thích trích dẫn
        repo = QuoteRepository(db)
        like = await repo.like_quote(user_id, quote_id)

        logger.info(f"Người dùng {user_id} đã thích trích dẫn {quote_id}")
        return like
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi thích trích dẫn: {str(e)}")
        raise


async def unlike_quote(db: Session, user_id: int, quote_id: int) -> None:
    """
    Bỏ thích trích dẫn.

    Args:
        db: Database session
        user_id: ID của người dùng
        quote_id: ID của trích dẫn

    Raises:
        NotFoundException: Nếu không tìm thấy trích dẫn hoặc người dùng
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

        # Kiểm tra trích dẫn tồn tại
        await get_quote_by_id(db, quote_id, False)

        # Bỏ thích trích dẫn
        repo = QuoteRepository(db)
        await repo.unlike_quote(user_id, quote_id)

        logger.info(f"Người dùng {user_id} đã bỏ thích trích dẫn {quote_id}")
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi bỏ thích trích dẫn: {str(e)}")
        raise


async def check_user_liked_quote(db: Session, user_id: int, quote_id: int) -> bool:
    """
    Kiểm tra người dùng đã thích trích dẫn chưa.

    Args:
        db: Database session
        user_id: ID của người dùng
        quote_id: ID của trích dẫn

    Returns:
        True nếu người dùng đã thích, False nếu chưa

    Raises:
        NotFoundException: Nếu không tìm thấy trích dẫn
    """
    try:
        # Kiểm tra trích dẫn tồn tại
        await get_quote_by_id(db, quote_id, False)

        # Kiểm tra đã thích chưa
        repo = QuoteRepository(db)
        return await repo.has_liked(user_id, quote_id)
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi kiểm tra thích trích dẫn: {str(e)}")
        raise


@cached(key_prefix="admin_user_liked_quotes", ttl=300)
async def get_user_liked_quotes(
    db: Session, user_id: int, skip: int = 0, limit: int = 20
) -> List[Quote]:
    """
    Lấy danh sách trích dẫn đã thích của người dùng.

    Args:
        db: Database session
        user_id: ID của người dùng
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về

    Returns:
        Danh sách trích dẫn đã thích

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

        # Lấy danh sách trích dẫn đã thích
        repo = QuoteRepository(db)
        return await repo.list_liked_quotes(user_id, skip, limit)
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách trích dẫn đã thích: {str(e)}")
        raise


async def count_user_liked_quotes(db: Session, user_id: int) -> int:
    """
    Đếm số lượng trích dẫn đã thích của người dùng.

    Args:
        db: Database session
        user_id: ID của người dùng

    Returns:
        Số lượng trích dẫn đã thích

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

        # Đếm số lượng trích dẫn đã thích
        repo = QuoteRepository(db)
        return await repo.count_liked_quotes(user_id)
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi đếm số lượng trích dẫn đã thích: {str(e)}")
        raise


@cached(key_prefix="admin_popular_quotes", ttl=600)
async def get_popular_quotes(db: Session, limit: int = 10) -> List[Quote]:
    """
    Lấy danh sách trích dẫn phổ biến.

    Args:
        db: Database session
        limit: Số bản ghi tối đa trả về

    Returns:
        Danh sách trích dẫn phổ biến
    """
    try:
        repo = QuoteRepository(db)
        return await repo.list_popular_quotes(limit)
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách trích dẫn phổ biến: {str(e)}")
        raise


@cached(key_prefix="admin_random_quotes", ttl=600)
async def get_random_quotes(db: Session, limit: int = 5) -> List[Quote]:
    """
    Lấy ngẫu nhiên trích dẫn.

    Args:
        db: Database session
        limit: Số bản ghi tối đa trả về

    Returns:
        Danh sách trích dẫn ngẫu nhiên
    """
    try:
        repo = QuoteRepository(db)
        return await repo.get_random_quotes(limit)
    except Exception as e:
        logger.error(f"Lỗi khi lấy trích dẫn ngẫu nhiên: {str(e)}")
        raise


async def toggle_quote_visibility(db: Session, quote_id: int) -> Quote:
    """
    Chuyển đổi trạng thái công khai của trích dẫn.

    Args:
        db: Database session
        quote_id: ID của trích dẫn

    Returns:
        Thông tin trích dẫn đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy trích dẫn
    """
    try:
        # Lấy thông tin trích dẫn
        quote = await get_quote_by_id(db, quote_id, False)

        # Chuyển đổi trạng thái công khai
        new_status = not quote.is_public

        # Cập nhật trạng thái
        repo = QuoteRepository(db)
        updated_quote = await repo.update(quote_id, {"is_public": new_status})

        logger.info(
            f"Đã chuyển đổi trạng thái công khai của trích dẫn {quote_id} thành {new_status}"
        )
        return updated_quote
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi chuyển đổi trạng thái công khai: {str(e)}")
        raise


@cached(key_prefix="admin_quote_statistics", ttl=3600)
async def get_quote_statistics(
    db: Session, admin_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Lấy thống kê về trích dẫn.

    Args:
        db: Database session
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thống kê trích dẫn
    """
    try:
        repo = QuoteRepository(db)

        total = await repo.count_quotes()

        # Thống kê theo sách
        by_book = await repo.count_quotes_by_book()

        # Thống kê theo người dùng
        by_user = await repo.count_quotes_by_user()

        stats = {"total": total, "by_book": by_book, "by_user": by_user}

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="QUOTE_STATISTICS",
                        entity_id=0,
                        description="Viewed quote statistics",
                        metadata=stats,
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return stats
    except Exception as e:
        logger.error(f"Error retrieving quote statistics: {str(e)}")
        raise
