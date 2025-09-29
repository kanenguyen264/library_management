from typing import Optional, List, Dict, Any, Union, Tuple
from sqlalchemy import select, update, delete, desc, func, or_, and_, asc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.exc import IntegrityError

from app.user_site.models.book import Book
from app.user_site.models.author import Author, BookAuthor
from app.user_site.models.category import Category, BookCategory
from app.user_site.models.tag import Tag, BookTag
from app.core.exceptions import NotFoundException, ConflictException


class BookRepository:
    """Repository cho các thao tác liên quan đến sách (Book) và các mối quan hệ của nó."""

    def __init__(self, db: AsyncSession):
        """Khởi tạo repository với AsyncSession."""
        self.db = db

    async def create(
        self,
        book_data: Dict[str, Any],
        author_ids: List[int] = [],
        category_ids: List[int] = [],
        tag_ids: List[int] = [],
    ) -> Book:
        """Tạo một sách mới.

        Args:
            book_data: Dữ liệu cơ bản của sách (title, slug, description, isbn, etc.).
            author_ids: Danh sách ID các tác giả.
            category_ids: Danh sách ID các danh mục.
            tag_ids: Danh sách ID các tag.

        Returns:
            Đối tượng Book đã được tạo.

        Raises:
            ConflictException: Nếu slug hoặc ISBN đã tồn tại.
        """
        # Kiểm tra slug/isbn nếu có
        slug = book_data.get("slug")
        isbn = book_data.get("isbn")
        if slug:
            existing_slug = await self.get_by_slug(slug)
            if existing_slug:
                raise ConflictException(detail=f"Slug '{slug}' đã tồn tại.")
        if isbn:
            existing_isbn = await self.get_by_isbn(isbn)
            if existing_isbn:
                raise ConflictException(detail=f"ISBN '{isbn}' đã tồn tại.")

        # Lọc dữ liệu sách cơ bản
        allowed_book_fields = {
            "title",
            "slug",
            "description",
            "isbn",
            "publisher_id",
            "publication_date",
            "language",
            "page_count",
            "cover_image_url",
            "average_rating",
            "reviews_count",
            "status",
            "is_featured",
            "is_published",
            "content_rating",
            # Thêm các trường khác nếu cần
        }
        filtered_book_data = {
            k: v for k, v in book_data.items() if k in allowed_book_fields
        }
        book = Book(**filtered_book_data)
        self.db.add(book)

        try:
            # Commit để lấy book.id
            await self.db.commit()
            await self.db.refresh(book)

            # Thêm các mối quan hệ many-to-many sau khi có book.id
            await self._add_authors(book.id, author_ids)
            await self._add_categories(book.id, category_ids)
            await self._add_tags(book.id, tag_ids)

            # Commit lần cuối sau khi thêm relations
            await self.db.commit()
            await self.db.refresh(book)  # Refresh lại để load relations nếu cần
            return book
        except IntegrityError as e:
            await self.db.rollback()
            if "uq_books_slug" in str(e):
                raise ConflictException(detail=f"Slug '{slug}' đã tồn tại.")
            elif "uq_books_isbn" in str(e):
                raise ConflictException(detail=f"ISBN '{isbn}' đã tồn tại.")
            # Handle foreign key constraint failures (e.g., publisher_id not found)
            elif "foreign key constraint" in str(e).lower():
                raise NotFoundException(
                    detail="Publisher hoặc ID liên quan khác không hợp lệ."
                )
            else:
                raise  # Re-raise unexpected errors

    async def get_by_id(
        self, book_id: int, with_relations: Optional[List[str]] = None
    ) -> Optional[Book]:
        """Lấy sách theo ID.

        Args:
            book_id: ID của sách.
            with_relations: Danh sách các mối quan hệ cần load (ví dụ: ["authors", "categories", "tags", "publisher", "chapters"]).

        Returns:
            Đối tượng Book hoặc None nếu không tìm thấy.
        """
        query = select(Book).where(Book.id == book_id)

        if with_relations:
            options = []
            if "authors" in with_relations:
                options.append(selectinload(Book.authors))
            if "categories" in with_relations:
                options.append(selectinload(Book.categories))
            if "tags" in with_relations:
                options.append(selectinload(Book.tags))
            if "publisher" in with_relations:
                options.append(selectinload(Book.publisher))
            if "chapters" in with_relations:
                options.append(selectinload(Book.chapters))
            # Thêm các relations khác nếu cần (reviews, etc.)
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_by_slug(
        self, slug: str, with_relations: Optional[List[str]] = None
    ) -> Optional[Book]:
        """Lấy sách theo slug.

        Args:
            slug: Slug của sách.
            with_relations: Danh sách quan hệ cần load.

        Returns:
            Đối tượng Book hoặc None.
        """
        query = select(Book).where(Book.slug == slug)
        if with_relations:
            # Tương tự get_by_id, thêm các options load relations
            options = []
            if "authors" in with_relations:
                options.append(selectinload(Book.authors))
            if "categories" in with_relations:
                options.append(selectinload(Book.categories))
            if "tags" in with_relations:
                options.append(selectinload(Book.tags))
            if "publisher" in with_relations:
                options.append(selectinload(Book.publisher))
            if "chapters" in with_relations:
                options.append(selectinload(Book.chapters))
            if options:
                query = query.options(*options)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_by_isbn(self, isbn: str) -> Optional[Book]:
        """Lấy sách theo ISBN."""
        query = select(Book).where(Book.isbn == isbn)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def update(self, book_id: int, data: Dict[str, Any]) -> Book:
        """Cập nhật thông tin sách cơ bản (không bao gồm relations many-to-many).
           Sử dụng các phương thức add/remove/update riêng cho relations.
        Args:
            book_id: ID của sách cần cập nhật.
            data: Dữ liệu cập nhật.

        Returns:
            Đối tượng Book đã được cập nhật.

        Raises:
            NotFoundException: Nếu không tìm thấy sách.
            ConflictException: Nếu slug hoặc ISBN mới bị trùng.
        """
        book = await self.get_by_id(book_id)
        if not book:
            raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

        new_slug = data.get("slug")
        new_isbn = data.get("isbn")

        if new_slug and new_slug != book.slug:
            existing_slug = await self.get_by_slug(new_slug)
            if existing_slug:
                raise ConflictException(detail=f"Slug '{new_slug}' đã tồn tại.")
        if new_isbn and new_isbn != book.isbn:
            existing_isbn = await self.get_by_isbn(new_isbn)
            if existing_isbn:
                raise ConflictException(detail=f"ISBN '{new_isbn}' đã tồn tại.")

        allowed_book_fields = {
            "title",
            "slug",
            "description",
            "isbn",
            "publisher_id",
            "publication_date",
            "language",
            "page_count",
            "cover_image_url",
            "average_rating",
            "reviews_count",
            "status",
            "is_featured",
            "is_published",
            "content_rating",
        }
        for key, value in data.items():
            if key in allowed_book_fields:
                setattr(book, key, value)

        try:
            await self.db.commit()
            await self.db.refresh(book)
            return book
        except IntegrityError as e:
            await self.db.rollback()
            # Handle potential integrity errors (e.g., duplicate slug/isbn again, invalid foreign keys)
            raise ConflictException(detail="Lỗi ràng buộc dữ liệu khi cập nhật sách.")

    async def delete(self, book_id: int) -> bool:
        """Xóa sách. Cảnh báo: Cần xử lý các dependencies hoặc dùng cascade.

        Args:
            book_id: ID sách cần xóa.

        Returns:
            True nếu xóa thành công.

        Raises:
            NotFoundException: Nếu không tìm thấy sách.
            IntegrityError: Nếu có lỗi ràng buộc khóa ngoại (nếu không dùng cascade).
        """
        book = await self.get_by_id(book_id)
        if not book:
            raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

        try:
            # Xóa các liên kết many-to-many trước nếu không có cascade
            await self.db.execute(
                delete(BookAuthor).where(BookAuthor.book_id == book_id)
            )
            await self.db.execute(
                delete(BookCategory).where(BookCategory.book_id == book_id)
            )
            await self.db.execute(delete(BookTag).where(BookTag.book_id == book_id))
            # Xem xét xóa các liên kết khác: chapters, reviews, bookmarks, etc.

            await self.db.delete(book)
            await self.db.commit()
            return True
        except IntegrityError as e:
            await self.db.rollback()
            # Log the error for debugging
            print(f"IntegrityError deleting book {book_id}: {e}")
            raise IntegrityError(
                "Không thể xóa sách do còn dữ liệu liên quan.", orig=e, params=None
            )

    async def list_books(
        self,
        skip: int = 0,
        limit: int = 20,  # Giảm limit mặc định
        only_published: bool = True,
        sort_by: str = "created_at",
        sort_desc: bool = True,
        with_relations: Optional[List[str]] = None,
        category_id: Optional[int] = None,
        author_id: Optional[int] = None,
        tag_id: Optional[int] = None,
        search_query: Optional[str] = None,
    ) -> List[Book]:
        """Liệt kê sách với nhiều bộ lọc, sắp xếp và phân trang.

        Args:
            skip, limit: Phân trang.
            only_published: Chỉ lấy sách đã xuất bản.
            sort_by: Trường sắp xếp (title, created_at, average_rating, etc.).
            sort_desc: Sắp xếp giảm dần.
            with_relations: Danh sách quan hệ cần load (authors, categories, tags, publisher).
            category_id: Lọc theo ID danh mục.
            author_id: Lọc theo ID tác giả.
            tag_id: Lọc theo ID tag.
            search_query: Từ khóa tìm kiếm (title, description, isbn).

        Returns:
            Danh sách các đối tượng Book.
        """
        query = select(Book)

        # Áp dụng bộ lọc
        if only_published:
            query = query.filter(Book.is_published == True)
        if category_id:
            query = query.join(BookCategory).filter(
                BookCategory.category_id == category_id
            )
        if author_id:
            query = query.join(BookAuthor).filter(BookAuthor.author_id == author_id)
        if tag_id:
            query = query.join(BookTag).filter(BookTag.tag_id == tag_id)
        if search_query:
            search_pattern = f"%{search_query}%"
            query = query.filter(
                or_(
                    Book.title.ilike(search_pattern),
                    Book.description.ilike(search_pattern),
                    Book.isbn.ilike(search_pattern),
                    # Có thể join với Author để tìm theo tên tác giả
                )
            )

        # Sắp xếp
        sort_attr = getattr(Book, sort_by, Book.created_at)
        if sort_desc:
            query = query.order_by(desc(sort_attr))
        else:
            query = query.order_by(asc(sort_attr))

        # Load relations
        if with_relations:
            options = []
            if "authors" in with_relations:
                options.append(selectinload(Book.authors))
            if "categories" in with_relations:
                options.append(selectinload(Book.categories))
            if "tags" in with_relations:
                options.append(selectinload(Book.tags))
            if "publisher" in with_relations:
                options.append(selectinload(Book.publisher))
            if options:
                query = query.options(*options)

        # Phân trang
        query = query.offset(skip).limit(limit)

        result = await self.db.execute(query)
        # Dùng unique() để tránh trùng lặp sách khi join nhiều lần
        return result.scalars().unique().all()

    async def get_featured_books(
        self, limit: int = 10, with_relations: Optional[List[str]] = None
    ) -> List[Book]:
        """Lấy danh sách sách nổi bật."""
        query = (
            select(Book)
            .where(Book.is_featured == True)
            .order_by(desc(Book.created_at))
            .limit(limit)
        )
        if with_relations:
            options = []
            if "authors" in with_relations:
                options.append(selectinload(Book.authors))
            if "publisher" in with_relations:
                options.append(selectinload(Book.publisher))
            if options:
                query = query.options(*options)
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_trending_books(
        self, limit: int = 10, days: int = 7, with_relations: Optional[List[str]] = None
    ) -> List[Book]:
        """Lấy danh sách sách thịnh hành (ví dụ: dựa trên lượt xem/đọc gần đây). Cần có bảng tracking riêng."""
        # Placeholder: Logic này cần dựa trên dữ liệu thực tế (ví dụ: bảng view counts)
        # Ví dụ: Sắp xếp theo số lượt xem trong `days` ngày qua
        # Giả sử có BookView model: BookView(book_id, user_id, viewed_at)
        # subquery = select(BookView.book_id, func.count(BookView.id).label('view_count'))\
        #     .where(BookView.viewed_at >= datetime.now() - timedelta(days=days))\
        #     .group_by(BookView.book_id).subquery()
        # query = select(Book).join(subquery, Book.id == subquery.c.book_id)\
        #     .order_by(desc(subquery.c.view_count)).limit(limit)

        # Tạm thời trả về sách mới nhất
        query = (
            select(Book)
            .where(Book.is_published == True)
            .order_by(desc(Book.created_at))
            .limit(limit)
        )
        if with_relations:
            options = []
            if "authors" in with_relations:
                options.append(selectinload(Book.authors))
            if "publisher" in with_relations:
                options.append(selectinload(Book.publisher))
            if options:
                query = query.options(*options)
        result = await self.db.execute(query)
        return result.scalars().all()

    async def update_rating(
        self, book_id: int, avg_rating: float, reviews_count: int
    ) -> Book:
        """Cập nhật điểm đánh giá trung bình và số lượng đánh giá cho sách.
        Thường được gọi sau khi tạo/xóa/cập nhật review.
        """
        book = await self.get_by_id(book_id)
        if not book:
            raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

        book.average_rating = avg_rating
        book.reviews_count = reviews_count

        await self.db.commit()
        await self.db.refresh(book)
        return book

    async def count_books(
        self,
        only_published: bool = True,
        category_id: Optional[int] = None,
        author_id: Optional[int] = None,
        tag_id: Optional[int] = None,
        search_query: Optional[str] = None,
    ) -> int:
        """Đếm số lượng sách với các bộ lọc tương tự list_books."""
        query = select(func.count(Book.id))

        # Áp dụng join và filter giống list_books để đảm bảo count chính xác
        if category_id:
            query = query.join(BookCategory).filter(
                BookCategory.category_id == category_id
            )
        if author_id:
            query = query.join(BookAuthor).filter(BookAuthor.author_id == author_id)
        if tag_id:
            query = query.join(BookTag).filter(BookTag.tag_id == tag_id)

        # Filter cơ bản
        if only_published:
            query = query.filter(Book.is_published == True)
        if search_query:
            search_pattern = f"%{search_query}%"
            query = query.filter(
                or_(
                    Book.title.ilike(search_pattern),
                    Book.description.ilike(search_pattern),
                    Book.isbn.ilike(search_pattern),
                )
            )

        result = await self.db.execute(query)
        return result.scalar_one() or 0

    # --- Many-to-Many Helper Methods (Internal) --- #

    async def _add_items(
        self,
        book_id: int,
        item_ids: List[int],
        association_table: Any,
        book_column: str,
        item_column: str,
    ):
        """Helper chung để thêm items vào bảng liên kết many-to-many."""
        if not item_ids:
            return
        # Lấy các liên kết đã tồn tại
        existing_query = select(getattr(association_table.c, item_column)).where(
            getattr(association_table.c, book_column) == book_id
        )
        existing_result = await self.db.execute(existing_query)
        existing_ids = set(existing_result.scalars().all())

        items_to_add = []
        for item_id in item_ids:
            if item_id not in existing_ids:
                items_to_add.append({book_column: book_id, item_column: item_id})

        if items_to_add:
            await self.db.execute(association_table.insert(), items_to_add)

    async def _remove_items(
        self,
        book_id: int,
        item_ids: List[int],
        association_table: Any,
        book_column: str,
        item_column: str,
    ):
        """Helper chung để xóa items khỏi bảng liên kết many-to-many."""
        if not item_ids:
            return
        query = delete(association_table).where(
            getattr(association_table.c, book_column) == book_id,
            getattr(association_table.c, item_column).in_(item_ids),
        )
        await self.db.execute(query)

    async def _update_items(
        self,
        book_id: int,
        item_ids: List[int],
        association_table: Any,
        book_column: str,
        item_column: str,
    ):
        """Helper chung để cập nhật (xóa cũ, thêm mới) items trong bảng liên kết."""
        # Xóa tất cả liên kết cũ
        delete_query = delete(association_table).where(
            getattr(association_table.c, book_column) == book_id
        )
        await self.db.execute(delete_query)
        # Thêm liên kết mới
        await self._add_items(
            book_id, item_ids, association_table, book_column, item_column
        )

    # --- Many-to-Many Public Methods --- #

    async def add_authors(self, book_id: int, author_ids: List[int]) -> Book:
        """Thêm tác giả vào sách."""
        await self._add_items(
            book_id, author_ids, BookAuthor.__table__, "book_id", "author_id"
        )
        await self.db.commit()  # Commit sau mỗi thao tác add/remove/update relations
        book = await self.get_by_id(book_id, with_relations=["authors"])
        if not book:
            raise NotFoundException(
                f"Sách {book_id} không tồn tại sau khi thêm tác giả?"
            )
        return book

    async def remove_authors(self, book_id: int, author_ids: List[int]) -> Book:
        """Xóa tác giả khỏi sách."""
        await self._remove_items(
            book_id, author_ids, BookAuthor.__table__, "book_id", "author_id"
        )
        await self.db.commit()
        book = await self.get_by_id(book_id, with_relations=["authors"])
        if not book:
            raise NotFoundException(
                f"Sách {book_id} không tồn tại sau khi xóa tác giả?"
            )
        return book

    async def update_authors(self, book_id: int, author_ids: List[int]) -> Book:
        """Cập nhật danh sách tác giả cho sách (xóa cũ, thêm mới)."""
        await self._update_items(
            book_id, author_ids, BookAuthor.__table__, "book_id", "author_id"
        )
        await self.db.commit()
        book = await self.get_by_id(book_id, with_relations=["authors"])
        if not book:
            raise NotFoundException(
                f"Sách {book_id} không tồn tại sau khi cập nhật tác giả?"
            )
        return book

    async def add_categories(self, book_id: int, category_ids: List[int]) -> Book:
        """Thêm danh mục vào sách."""
        await self._add_items(
            book_id, category_ids, BookCategory.__table__, "book_id", "category_id"
        )
        await self.db.commit()
        book = await self.get_by_id(book_id, with_relations=["categories"])
        if not book:
            raise NotFoundException(
                f"Sách {book_id} không tồn tại sau khi thêm danh mục?"
            )
        return book

    async def remove_categories(self, book_id: int, category_ids: List[int]) -> Book:
        """Xóa danh mục khỏi sách."""
        await self._remove_items(
            book_id, category_ids, BookCategory.__table__, "book_id", "category_id"
        )
        await self.db.commit()
        book = await self.get_by_id(book_id, with_relations=["categories"])
        if not book:
            raise NotFoundException(
                f"Sách {book_id} không tồn tại sau khi xóa danh mục?"
            )
        return book

    async def update_categories(self, book_id: int, category_ids: List[int]) -> Book:
        """Cập nhật danh sách danh mục cho sách."""
        await self._update_items(
            book_id, category_ids, BookCategory.__table__, "book_id", "category_id"
        )
        await self.db.commit()
        book = await self.get_by_id(book_id, with_relations=["categories"])
        if not book:
            raise NotFoundException(
                f"Sách {book_id} không tồn tại sau khi cập nhật danh mục?"
            )
        return book

    async def add_tags(self, book_id: int, tag_ids: List[int]) -> Book:
        """Thêm tag vào sách."""
        await self._add_items(book_id, tag_ids, BookTag.__table__, "book_id", "tag_id")
        await self.db.commit()
        book = await self.get_by_id(book_id, with_relations=["tags"])
        if not book:
            raise NotFoundException(f"Sách {book_id} không tồn tại sau khi thêm tag?")
        return book

    async def remove_tags(self, book_id: int, tag_ids: List[int]) -> Book:
        """Xóa tag khỏi sách."""
        await self._remove_items(
            book_id, tag_ids, BookTag.__table__, "book_id", "tag_id"
        )
        await self.db.commit()
        book = await self.get_by_id(book_id, with_relations=["tags"])
        if not book:
            raise NotFoundException(f"Sách {book_id} không tồn tại sau khi xóa tag?")
        return book

    async def update_tags(self, book_id: int, tag_ids: List[int]) -> Book:
        """Cập nhật tags (thay thế hoàn toàn danh sách cũ)."""
        await self._update_items(
            book_id=book_id,
            item_ids=tag_ids,
            association_table=BookTag,
            book_column="book_id",
            item_column="tag_id",
        )
        return await self.get_by_id(book_id, with_relations=["tags"])

    # --- Publisher related methods ---

    async def count_by_publisher(self, publisher_id: int) -> int:
        """Đếm số lượng sách của một nhà xuất bản.

        Args:
            publisher_id: ID của nhà xuất bản

        Returns:
            Số lượng sách
        """
        query = select(func.count(Book.id)).where(Book.publisher_id == publisher_id)
        result = await self.db.execute(query)
        return result.scalar_one() or 0

    async def get_latest_by_publisher(
        self,
        publisher_id: int,
        limit: int = 5,
        with_relations: Optional[List[str]] = None,
    ) -> List[Book]:
        """Lấy danh sách sách mới nhất của một nhà xuất bản.

        Args:
            publisher_id: ID của nhà xuất bản
            limit: Số lượng sách trả về
            with_relations: Danh sách các mối quan hệ cần load

        Returns:
            Danh sách sách
        """
        query = (
            select(Book)
            .where(Book.publisher_id == publisher_id)
            .where(Book.is_published == True)
            .order_by(desc(Book.publication_date))
            .limit(limit)
        )

        if with_relations:
            options = []
            if "authors" in with_relations:
                options.append(selectinload(Book.authors))
            if "categories" in with_relations:
                options.append(selectinload(Book.categories))
            if "tags" in with_relations:
                options.append(selectinload(Book.tags))
            if "publisher" in with_relations:
                options.append(selectinload(Book.publisher))
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def count_authors_by_publisher(self, publisher_id: int) -> int:
        """Đếm số lượng tác giả đã xuất bản sách với nhà xuất bản này.

        Args:
            publisher_id: ID của nhà xuất bản

        Returns:
            Số lượng tác giả
        """
        # Lấy tất cả sách của nhà xuất bản
        books_query = select(Book.id).where(Book.publisher_id == publisher_id)
        books_result = await self.db.execute(books_query)
        book_ids = [book_id for book_id, in books_result.all()]

        if not book_ids:
            return 0

        # Đếm số lượng tác giả duy nhất đã viết các sách này
        authors_query = select(func.count(func.distinct(BookAuthor.author_id))).where(
            BookAuthor.book_id.in_(book_ids)
        )
        authors_result = await self.db.execute(authors_query)
        return authors_result.scalar_one() or 0

    async def get_top_genres_by_publisher(
        self, publisher_id: int, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Lấy các thể loại phổ biến nhất của nhà xuất bản.

        Args:
            publisher_id: ID của nhà xuất bản
            limit: Số lượng thể loại trả về

        Returns:
            Danh sách thể loại phổ biến và số lượng sách tương ứng
        """
        # Lấy tất cả sách của nhà xuất bản
        books_query = select(Book.id).where(Book.publisher_id == publisher_id)
        books_result = await self.db.execute(books_query)
        book_ids = [book_id for book_id, in books_result.all()]

        if not book_ids:
            return []

        # Lấy các thể loại phổ biến nhất
        genres_query = (
            select(
                Category.id,
                Category.name,
                Category.slug,
                func.count(BookCategory.book_id).label("book_count"),
            )
            .join(BookCategory, Category.id == BookCategory.category_id)
            .where(BookCategory.book_id.in_(book_ids))
            .group_by(Category.id)
            .order_by(desc("book_count"))
            .limit(limit)
        )
        genres_result = await self.db.execute(genres_query)

        return [
            {
                "id": id,
                "name": name,
                "slug": slug,
                "book_count": book_count,
            }
            for id, name, slug, book_count in genres_result.all()
        ]

    async def get_average_rating_by_publisher(
        self, publisher_id: int
    ) -> Optional[float]:
        """Lấy điểm đánh giá trung bình của tất cả sách từ nhà xuất bản.

        Args:
            publisher_id: ID của nhà xuất bản

        Returns:
            Điểm đánh giá trung bình hoặc None nếu không có đánh giá
        """
        query = (
            select(func.avg(Book.average_rating))
            .where(Book.publisher_id == publisher_id)
            .where(Book.average_rating.is_not(None))
            .where(Book.is_published == True)
        )
        result = await self.db.execute(query)
        avg_rating = result.scalar_one_or_none()

        # Làm tròn đến 1 chữ số thập phân nếu có giá trị
        return round(float(avg_rating), 1) if avg_rating is not None else None

    async def get_similar_books(
        self,
        book_id: int,
        limit: int = 5,
        with_relations: Optional[List[str]] = ["authors"],
    ) -> List[Book]:
        """Lấy danh sách sách tương tự dựa trên danh mục và tag chung.
        Cần cải thiện logic này để có kết quả tốt hơn.
        """
        target_book = await self.get_by_id(
            book_id, with_relations=["categories", "tags"]
        )
        if not target_book:
            return []

        category_ids = [c.id for c in target_book.categories]
        tag_ids = [t.id for t in target_book.tags]

        if not category_ids and not tag_ids:
            return []  # Không có cơ sở để tìm sách tương tự

        # Tìm các sách khác có chung category hoặc tag
        query = select(Book).where(Book.id != book_id, Book.is_published == True)

        similar_books_filter = []
        if category_ids:
            similar_books_filter.append(
                Book.categories.any(Category.id.in_(category_ids))
            )
        if tag_ids:
            similar_books_filter.append(Book.tags.any(Tag.id.in_(tag_ids)))

        if similar_books_filter:
            query = query.filter(or_(*similar_books_filter))

        # Ưu tiên sách có nhiều điểm chung hơn (cần logic phức tạp hơn để tính điểm)
        # Tạm thời sắp xếp theo rating hoặc ngày tạo
        query = query.order_by(desc(Book.average_rating), desc(Book.created_at))

        # Load relations cần thiết
        if with_relations:
            options = []
            if "authors" in with_relations:
                options.append(selectinload(Book.authors))
            if "categories" in with_relations:
                options.append(selectinload(Book.categories))
            if "tags" in with_relations:
                options.append(selectinload(Book.tags))
            if options:
                query = query.options(*options)

        query = query.limit(limit)

        result = await self.db.execute(query)
        return result.scalars().unique().all()
