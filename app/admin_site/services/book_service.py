from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from datetime import datetime
import logging

from app.user_site.repositories.book_repo import BookRepository
from app.user_site.repositories.chapter_repo import ChapterRepository
from app.user_site.repositories.author_repo import AuthorRepository
from app.user_site.repositories.category_repo import CategoryRepository
from app.user_site.repositories.tag_repo import TagRepository
from app.user_site.repositories.publisher_repo import PublisherRepository
from app.user_site.models.book import Book
from app.user_site.models.author import Author
from app.user_site.models.category import Category
from app.user_site.models.tag import Tag
from app.user_site.models.chapter import Chapter
from app.common.exceptions import (
    NotFoundException,
    BadRequestException,
    ResourceConflictException,
)
from app.logging.setup import get_logger
from app.cache.decorators import cached
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate
from app.core.exceptions import ConflictException

logger = get_logger(__name__)


async def get_all_books(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    only_published: bool = True,
    sort_by: str = "created_at",
    sort_desc: bool = True,
    include_relationships: bool = False,
    category_id: Optional[int] = None,
    author_id: Optional[int] = None,
    tag_id: Optional[int] = None,
    search_query: Optional[str] = None,
    admin_id: Optional[int] = None,
) -> List[Book]:
    """
    Lấy danh sách sách với bộ lọc.

    Args:
        db: Database session
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về
        only_published: Chỉ lấy sách đã xuất bản
        sort_by: Sắp xếp theo trường
        sort_desc: Sắp xếp giảm dần
        include_relationships: Có load các mối quan hệ không
        category_id: Lọc theo danh mục
        author_id: Lọc theo tác giả
        tag_id: Lọc theo tag
        search_query: Chuỗi tìm kiếm
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách sách
    """
    try:
        repo = BookRepository(db)
        books = await repo.list_books(
            skip=skip,
            limit=limit,
            only_published=only_published,
            sort_by=sort_by,
            sort_desc=sort_desc,
            include_relationships=include_relationships,
            category_id=category_id,
            author_id=author_id,
            tag_id=tag_id,
            search_query=search_query,
        )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="BOOKS",
                        entity_id=0,
                        description="Viewed book list",
                        metadata={
                            "skip": skip,
                            "limit": limit,
                            "search_query": search_query,
                            "author_id": author_id,
                            "category_id": category_id,
                            "tag_id": tag_id,
                            "results_count": len(books),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return books
    except Exception as e:
        logger.error(f"Error retrieving books: {str(e)}")
        raise


async def count_books(
    db: Session,
    only_published: bool = True,
    category_id: Optional[int] = None,
    author_id: Optional[int] = None,
    tag_id: Optional[int] = None,
    search_query: Optional[str] = None,
) -> int:
    """
    Đếm số lượng sách.

    Args:
        db: Database session
        only_published: Chỉ đếm sách đã xuất bản
        category_id: Lọc theo danh mục
        author_id: Lọc theo tác giả
        tag_id: Lọc theo tag
        search_query: Chuỗi tìm kiếm

    Returns:
        Số lượng sách
    """
    try:
        repo = BookRepository(db)
        return await repo.count_books(
            only_published=only_published,
            category_id=category_id,
            author_id=author_id,
            tag_id=tag_id,
            search_query=search_query,
        )
    except Exception as e:
        logger.error(f"Lỗi khi đếm sách: {str(e)}")
        raise


@cached(key_prefix="admin_book", ttl=300)
async def get_book_by_id(
    db: Session,
    book_id: int,
    with_relations: bool = False,
    admin_id: Optional[int] = None,
) -> Book:
    """
    Lấy thông tin sách theo ID.

    Args:
        db: Database session
        book_id: ID của sách
        with_relations: Có load các mối quan hệ không
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin sách

    Raises:
        NotFoundException: Nếu không tìm thấy sách
    """
    try:
        repo = BookRepository(db)
        book = await repo.get_by_id(book_id, with_relations)

        if not book:
            logger.warning(f"Không tìm thấy sách với ID {book_id}")
            raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="BOOK",
                        entity_id=book_id,
                        description=f"Viewed book details: {book.title}",
                        metadata={
                            "title": book.title,
                            "isbn": book.isbn,
                            "author_id": book.author_id,
                            "publisher_id": book.publisher_id,
                            "category_id": book.category_id,
                            "is_published": book.is_published,
                            "publication_date": (
                                book.publication_date.isoformat()
                                if book.publication_date
                                else None
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return book
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving book: {str(e)}")
        raise


@cached(key_prefix="admin_book_isbn", ttl=300)
async def get_book_by_isbn(db: Session, isbn: str) -> Book:
    """
    Lấy thông tin sách theo ISBN.

    Args:
        db: Database session
        isbn: ISBN của sách

    Returns:
        Thông tin sách

    Raises:
        NotFoundException: Nếu không tìm thấy sách
    """
    try:
        repo = BookRepository(db)
        book = await repo.get_by_isbn(isbn)

        if not book:
            logger.warning(f"Không tìm thấy sách với ISBN {isbn}")
            raise NotFoundException(detail=f"Không tìm thấy sách với ISBN {isbn}")

        return book
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin sách theo ISBN: {str(e)}")
        raise


async def create_book(
    db: Session, book_data: Dict[str, Any], admin_id: Optional[int] = None
) -> Book:
    """
    Tạo sách mới.

    Args:
        db: Database session
        book_data: Dữ liệu sách
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin sách đã tạo
    """
    try:
        # Kiểm tra tác giả tồn tại
        if "author_id" in book_data:
            author_repo = AuthorRepository(db)
            author = await author_repo.get_by_id(book_data["author_id"])

            if not author:
                logger.warning(f"Author with ID {book_data['author_id']} not found")
                raise NotFoundException(
                    detail=f"Không tìm thấy tác giả với ID {book_data['author_id']}"
                )

        # Kiểm tra nhà xuất bản tồn tại
        if "publisher_id" in book_data:
            publisher_repo = PublisherRepository(db)
            publisher = await publisher_repo.get_by_id(book_data["publisher_id"])

            if not publisher:
                logger.warning(
                    f"Publisher with ID {book_data['publisher_id']} not found"
                )
                raise NotFoundException(
                    detail=f"Không tìm thấy nhà xuất bản với ID {book_data['publisher_id']}"
                )

        # Kiểm tra danh mục tồn tại
        if "category_id" in book_data:
            category_repo = CategoryRepository(db)
            category = await category_repo.get_by_id(book_data["category_id"])

            if not category:
                logger.warning(f"Category with ID {book_data['category_id']} not found")
                raise NotFoundException(
                    detail=f"Không tìm thấy danh mục với ID {book_data['category_id']}"
                )

        # Kiểm tra ISBN đã tồn tại chưa
        if "isbn" in book_data:
            repo = BookRepository(db)
            existing_book = await repo.get_by_isbn(book_data["isbn"])

            if existing_book:
                logger.warning(f"Book with ISBN {book_data['isbn']} already exists")
                raise ConflictException(
                    detail=f"Sách với ISBN {book_data['isbn']} đã tồn tại"
                )

        # Tạo sách mới
        repo = BookRepository(db)
        book = await repo.create(book_data)

        # Thêm tác giả nếu có
        if "author_ids" in book_data and book_data["author_ids"]:
            await repo._add_authors(book.id, book_data["author_ids"])

        # Thêm danh mục nếu có
        if "category_ids" in book_data and book_data["category_ids"]:
            await repo._add_categories(book.id, book_data["category_ids"])

        # Thêm tag nếu có
        if "tag_ids" in book_data and book_data["tag_ids"]:
            await repo._add_tags(book.id, book_data["tag_ids"])

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="CREATE",
                        entity_type="BOOK",
                        entity_id=book.id,
                        description=f"Created new book: {book.title}",
                        metadata={
                            "title": book.title,
                            "isbn": book.isbn,
                            "author_id": book.author_id,
                            "publisher_id": book.publisher_id,
                            "category_id": book.category_id,
                            "is_published": book.is_published,
                            "publication_date": (
                                book.publication_date.isoformat()
                                if book.publication_date
                                else None
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Created new book with ID {book.id}")
        return book
    except NotFoundException:
        raise
    except ConflictException:
        raise
    except Exception as e:
        logger.error(f"Error creating book: {str(e)}")
        raise


async def update_book(
    db: Session, book_id: int, book_data: Dict[str, Any], admin_id: Optional[int] = None
) -> Book:
    """
    Cập nhật thông tin sách.

    Args:
        db: Database session
        book_id: ID của sách
        book_data: Dữ liệu cập nhật
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin sách đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy sách
        ConflictException: Nếu ISBN đã tồn tại
    """
    try:
        # Kiểm tra sách tồn tại
        await get_book_by_id(db, book_id)

        repo = BookRepository(db)

        # Kiểm tra ISBN mới có trùng không
        if "isbn" in book_data and book_data["isbn"] != await get_book_by_isbn(
            db, book_data["isbn"]
        ):
            logger.warning(f"Book with ISBN {book_data['isbn']} already exists")
            raise ConflictException(
                detail=f"Sách với ISBN {book_data['isbn']} đã tồn tại"
            )

        # Sao lưu danh sách tác giả, danh mục, tag nếu cần cập nhật
        author_ids = book_data.pop("author_ids", None)
        category_ids = book_data.pop("category_ids", None)
        tag_ids = book_data.pop("tag_ids", None)

        # Cập nhật thông tin sách
        book = await repo.update(book_id, book_data)

        # Cập nhật tác giả nếu có
        if author_ids is not None:
            await repo._update_authors(book.id, author_ids)

        # Cập nhật danh mục nếu có
        if category_ids is not None:
            await repo._update_categories(book.id, category_ids)

        # Cập nhật tag nếu có
        if tag_ids is not None:
            await repo._update_tags(book.id, tag_ids)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="BOOK",
                        entity_id=book_id,
                        description=f"Updated book: {book.title}",
                        metadata={
                            "updated_fields": list(book_data.keys()),
                            "old_values": {
                                k: getattr(await get_book_by_id(db, book_id), k)
                                for k in book_data.keys()
                            },
                            "new_values": {
                                k: getattr(book, k) for k in book_data.keys()
                            },
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Updated book with ID {book_id}")
        return book
    except NotFoundException:
        raise
    except ConflictException:
        raise
    except Exception as e:
        logger.error(f"Error updating book: {str(e)}")
        raise


async def delete_book(
    db: Session, book_id: int, admin_id: Optional[int] = None
) -> bool:
    """
    Xóa sách.

    Args:
        db: Database session
        book_id: ID của sách
        admin_id: ID của admin thực hiện hành động

    Returns:
        True nếu xóa thành công

    Raises:
        NotFoundException: Nếu không tìm thấy sách
    """
    try:
        # Kiểm tra sách tồn tại
        await get_book_by_id(db, book_id)

        # Xóa sách
        repo = BookRepository(db)
        result = await repo.delete(book_id)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="DELETE",
                        entity_type="BOOK",
                        entity_id=book_id,
                        description=f"Deleted book: {await get_book_by_id(db, book_id).title}",
                        metadata={
                            "title": await get_book_by_id(db, book_id).title,
                            "isbn": await get_book_by_isbn(
                                db, await get_book_by_id(db, book_id).isbn
                            ),
                            "author_id": await get_book_by_id(db, book_id).author_id,
                            "publisher_id": await get_book_by_id(
                                db, book_id
                            ).publisher_id,
                            "category_id": await get_book_by_id(
                                db, book_id
                            ).category_id,
                            "is_published": await get_book_by_id(
                                db, book_id
                            ).is_published,
                            "publication_date": (
                                await get_book_by_id(
                                    db, book_id
                                ).publication_date.isoformat()
                                if await get_book_by_id(db, book_id).publication_date
                                else None
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Deleted book with ID {book_id}")
        return result
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error deleting book: {str(e)}")
        raise


@cached(key_prefix="admin_featured_books", ttl=600)
async def get_featured_books(db: Session, limit: int = 10) -> List[Book]:
    """
    Lấy danh sách sách nổi bật.

    Args:
        db: Database session
        limit: Số lượng sách tối đa

    Returns:
        Danh sách sách nổi bật
    """
    try:
        repo = BookRepository(db)
        return await repo.get_featured_books(limit)
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách sách nổi bật: {str(e)}")
        raise


@cached(key_prefix="admin_trending_books", ttl=600)
async def get_trending_books(db: Session, limit: int = 10) -> List[Book]:
    """
    Lấy danh sách sách xu hướng.

    Args:
        db: Database session
        limit: Số lượng sách tối đa

    Returns:
        Danh sách sách xu hướng
    """
    try:
        repo = BookRepository(db)
        return await repo.get_trending_books(limit)
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách sách xu hướng: {str(e)}")
        raise


@cached(key_prefix="admin_similar_books", ttl=600)
async def get_similar_books(db: Session, book_id: int, limit: int = 5) -> List[Book]:
    """
    Lấy danh sách sách tương tự.

    Args:
        db: Database session
        book_id: ID của sách
        limit: Số lượng sách tối đa

    Returns:
        Danh sách sách tương tự

    Raises:
        NotFoundException: Nếu không tìm thấy sách
    """
    try:
        # Kiểm tra sách tồn tại
        await get_book_by_id(db, book_id)

        # Lấy danh sách sách tương tự
        repo = BookRepository(db)
        return await repo.get_similar_books(book_id, limit)
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách sách tương tự: {str(e)}")
        raise


async def update_rating(
    db: Session, book_id: int, avg_rating: float, review_count: int
) -> Book:
    """
    Cập nhật đánh giá cho sách.

    Args:
        db: Database session
        book_id: ID của sách
        avg_rating: Đánh giá trung bình
        review_count: Số lượng đánh giá

    Returns:
        Thông tin sách đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy sách
    """
    try:
        # Kiểm tra sách tồn tại
        await get_book_by_id(db, book_id)

        # Cập nhật đánh giá
        repo = BookRepository(db)
        return await repo.update_rating(book_id, avg_rating, review_count)
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật đánh giá sách: {str(e)}")
        raise


async def add_categories(db: Session, book_id: int, category_ids: List[int]) -> Book:
    """
    Thêm danh mục cho sách.

    Args:
        db: Database session
        book_id: ID của sách
        category_ids: Danh sách ID danh mục

    Returns:
        Thông tin sách đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy sách hoặc danh mục
    """
    try:
        # Kiểm tra sách tồn tại
        await get_book_by_id(db, book_id)

        # Kiểm tra danh mục tồn tại
        category_repo = CategoryRepository(db)
        for category_id in category_ids:
            category = await category_repo.get_by_id(category_id)

            if not category:
                logger.warning(f"Không tìm thấy danh mục với ID {category_id}")
                raise NotFoundException(
                    detail=f"Không tìm thấy danh mục với ID {category_id}"
                )

        # Thêm danh mục cho sách
        book_repo = BookRepository(db)
        return await book_repo.add_categories(book_id, category_ids)
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi thêm danh mục cho sách: {str(e)}")
        raise


async def remove_categories(db: Session, book_id: int, category_ids: List[int]) -> Book:
    """
    Xóa danh mục của sách.

    Args:
        db: Database session
        book_id: ID của sách
        category_ids: Danh sách ID danh mục

    Returns:
        Thông tin sách đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy sách
    """
    try:
        # Kiểm tra sách tồn tại
        await get_book_by_id(db, book_id)

        # Xóa danh mục của sách
        book_repo = BookRepository(db)
        return await book_repo.remove_categories(book_id, category_ids)
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi xóa danh mục của sách: {str(e)}")
        raise


async def add_tags(db: Session, book_id: int, tag_ids: List[int]) -> Book:
    """
    Thêm tag cho sách.

    Args:
        db: Database session
        book_id: ID của sách
        tag_ids: Danh sách ID tag

    Returns:
        Thông tin sách đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy sách hoặc tag
    """
    try:
        # Kiểm tra sách tồn tại
        await get_book_by_id(db, book_id)

        # Kiểm tra tag tồn tại
        tag_repo = TagRepository(db)
        for tag_id in tag_ids:
            tag = await tag_repo.get_by_id(tag_id)

            if not tag:
                logger.warning(f"Không tìm thấy tag với ID {tag_id}")
                raise NotFoundException(detail=f"Không tìm thấy tag với ID {tag_id}")

        # Thêm tag cho sách
        book_repo = BookRepository(db)
        return await book_repo.add_tags(book_id, tag_ids)
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi thêm tag cho sách: {str(e)}")
        raise


async def remove_tags(db: Session, book_id: int, tag_ids: List[int]) -> Book:
    """
    Xóa tag của sách.

    Args:
        db: Database session
        book_id: ID của sách
        tag_ids: Danh sách ID tag

    Returns:
        Thông tin sách đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy sách
    """
    try:
        # Kiểm tra sách tồn tại
        await get_book_by_id(db, book_id)

        # Xóa tag của sách
        book_repo = BookRepository(db)
        return await book_repo.remove_tags(book_id, tag_ids)
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi xóa tag của sách: {str(e)}")
        raise


async def add_authors(db: Session, book_id: int, author_ids: List[int]) -> Book:
    """
    Thêm tác giả cho sách.

    Args:
        db: Database session
        book_id: ID của sách
        author_ids: Danh sách ID tác giả

    Returns:
        Thông tin sách đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy sách hoặc tác giả
    """
    try:
        # Kiểm tra sách tồn tại
        await get_book_by_id(db, book_id)

        # Kiểm tra tác giả tồn tại
        author_repo = AuthorRepository(db)
        for author_id in author_ids:
            author = await author_repo.get_by_id(author_id)

            if not author:
                logger.warning(f"Không tìm thấy tác giả với ID {author_id}")
                raise NotFoundException(
                    detail=f"Không tìm thấy tác giả với ID {author_id}"
                )

        # Thêm tác giả cho sách
        book_repo = BookRepository(db)
        return await book_repo.add_authors(book_id, author_ids)
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi thêm tác giả cho sách: {str(e)}")
        raise


async def remove_authors(db: Session, book_id: int, author_ids: List[int]) -> Book:
    """
    Xóa tác giả của sách.

    Args:
        db: Database session
        book_id: ID của sách
        author_ids: Danh sách ID tác giả

    Returns:
        Thông tin sách đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy sách
    """
    try:
        # Kiểm tra sách tồn tại
        await get_book_by_id(db, book_id)

        # Xóa tác giả của sách
        book_repo = BookRepository(db)
        return await book_repo.remove_authors(book_id, author_ids)
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi xóa tác giả của sách: {str(e)}")
        raise


async def publish_book(
    db: Session, book_id: int, admin_id: Optional[int] = None
) -> Book:
    """
    Xuất bản sách.

    Args:
        db: Database session
        book_id: ID của sách
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin sách đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy sách
    """
    try:
        # Kiểm tra sách tồn tại
        await get_book_by_id(db, book_id)

        # Xuất bản sách
        repo = BookRepository(db)
        updated_book = await repo.update(
            book_id, {"is_published": True, "status": "published"}
        )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="PUBLISH",
                        entity_type="BOOK",
                        entity_id=book_id,
                        description=f"Published book: {updated_book.title}",
                        metadata={
                            "title": updated_book.title,
                            "isbn": updated_book.isbn,
                            "old_status": await get_book_by_id(
                                db, book_id
                            ).is_published,
                            "new_status": updated_book.is_published,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Published book with ID {book_id}")
        return updated_book
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error publishing book: {str(e)}")
        raise


async def unpublish_book(
    db: Session, book_id: int, admin_id: Optional[int] = None
) -> Book:
    """
    Hủy xuất bản sách.

    Args:
        db: Database session
        book_id: ID của sách
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin sách đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy sách
    """
    try:
        # Kiểm tra sách tồn tại
        await get_book_by_id(db, book_id)

        # Hủy xuất bản sách
        repo = BookRepository(db)
        updated_book = await repo.update(
            book_id, {"is_published": False, "status": "draft"}
        )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UNPUBLISH",
                        entity_type="BOOK",
                        entity_id=book_id,
                        description=f"Unpublished book: {updated_book.title}",
                        metadata={
                            "title": updated_book.title,
                            "isbn": updated_book.isbn,
                            "old_status": await get_book_by_id(
                                db, book_id
                            ).is_published,
                            "new_status": updated_book.is_published,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Unpublished book with ID {book_id}")
        return updated_book
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error unpublishing book: {str(e)}")
        raise


@cached(key_prefix="admin_book_statistics", ttl=3600)
async def get_book_statistics(
    db: Session, admin_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Lấy thống kê về sách.

    Args:
        db: Database session
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thống kê sách
    """
    try:
        repo = BookRepository(db)

        # Tính toán các thống kê
        total_books = await repo.count_books(only_published=False)
        published_books = await repo.count_books(only_published=True)
        trending_books = await repo.get_trending_books(5)
        featured_books = await repo.get_featured_books(5)

        # Thống kê sách theo danh mục
        # Chú ý: Cần bổ sung các phương thức hỗ trợ trong repository

        stats = {
            "total_books": total_books,
            "published_books": published_books,
            "unpublished_books": total_books - published_books,
            "trending_books": [
                {
                    "id": book.id,
                    "title": book.title,
                    "author": book.authors[0].name if book.authors else "N/A",
                    "view_count": book.view_count,
                    "avg_rating": book.avg_rating,
                }
                for book in trending_books
            ],
            "featured_books": [
                {
                    "id": book.id,
                    "title": book.title,
                    "author": book.authors[0].name if book.authors else "N/A",
                    "is_featured": book.is_featured,
                }
                for book in featured_books
            ],
            "books_by_category": [],  # Cần bổ sung phương thức count_books_by_category
            "books_by_author": [],  # Cần bổ sung phương thức count_books_by_author
            "books_by_status": {
                "published": published_books,
                "draft": total_books - published_books,
            },
        }

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="BOOK_STATISTICS",
                        entity_id=0,
                        description="Viewed book statistics",
                        metadata=stats,
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return stats
    except Exception as e:
        logger.error(f"Error retrieving book statistics: {str(e)}")
        raise
