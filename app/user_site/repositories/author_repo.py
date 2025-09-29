from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy import select, update, delete, func, or_, and_, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.exc import IntegrityError

from app.user_site.models.author import Author, BookAuthor
from app.user_site.models.book import Book
from app.core.exceptions import NotFoundException, ForbiddenException, ConflictException

try:
    from slugify import slugify
except ImportError:
    import re

    def slugify(text):
        text = re.sub(r"[\s\W]+", "-", text)
        return text.lower().strip("-")


class AuthorRepository:
    """Repository cho các thao tác với tác giả (Author) và liên kết sách (BookAuthor)."""

    def __init__(self, db: AsyncSession):
        """Khởi tạo repository với AsyncSession."""
        self.db = db

    async def create(self, data: Dict[str, Any]) -> Author:
        """Tạo một tác giả mới.

        Args:
            data: Dữ liệu tác giả (name, slug, biography, birth_date, death_date, etc.).

        Returns:
            Đối tượng Author đã được tạo.

        Raises:
            ConflictException: Nếu slug đã tồn tại.
        """
        # Kiểm tra slug nếu có
        slug_value = data.get("slug")
        if slug_value:
            existing = await self.get_by_slug(slug_value)
            if existing:
                raise ConflictException(detail=f"Slug '{slug_value}' đã tồn tại.")
        elif "name" in data:
            # Tự động tạo slug từ tên nếu slug không được cung cấp
            data["slug"] = await self._generate_unique_slug(data["name"])

        # Lọc các trường hợp lệ
        allowed_fields = {
            "name",
            "slug",
            "biography",
            "birth_date",
            "death_date",
            "nationality",
            "website",
            "photo_url",
            "is_featured",
            "book_count",  # book_count có thể được tính tự động
        }
        filtered_data = {k: v for k, v in data.items() if k in allowed_fields}

        author = Author(**filtered_data)
        self.db.add(author)
        try:
            await self.db.commit()
            await self.db.refresh(author)
            return author
        except IntegrityError as e:
            await self.db.rollback()
            # Kiểm tra xem lỗi có phải do unique constraint của slug không
            if "uq_authors_slug" in str(e):
                raise ConflictException(detail=f"Slug '{data.get('slug')}' đã tồn tại.")
            else:
                raise  # Ném lại lỗi nếu không phải lỗi unique slug

    async def get_by_id(
        self, author_id: int, with_relations: Optional[List[str]] = None
    ) -> Optional[Author]:
        """Lấy tác giả theo ID.

        Args:
            author_id: ID của tác giả.
            with_relations: Danh sách các mối quan hệ cần load (ví dụ: ["books"]).

        Returns:
            Đối tượng Author hoặc None nếu không tìm thấy.
        """
        query = select(Author).where(Author.id == author_id)

        if with_relations:
            options = []
            if "books" in with_relations:
                options.append(selectinload(Author.books))
            # Thêm các relations khác nếu cần
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_by_slug(
        self, slug: str, with_relations: Optional[List[str]] = None
    ) -> Optional[Author]:
        """Lấy tác giả theo slug.

        Args:
            slug: Slug của tác giả.
            with_relations: Danh sách các mối quan hệ cần load.

        Returns:
            Đối tượng Author hoặc None nếu không tìm thấy.
        """
        query = select(Author).where(Author.slug == slug)
        if with_relations:
            options = []
            if "books" in with_relations:
                options.append(selectinload(Author.books))
            if options:
                query = query.options(*options)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_by_name(self, name: str) -> Optional[Author]:
        """Lấy tác giả theo tên (phân biệt chữ hoa/thường)."""
        query = select(Author).where(Author.name == name)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def update(self, author_id: int, data: Dict[str, Any]) -> Author:
        """Cập nhật thông tin tác giả.

        Args:
            author_id: ID của tác giả cần cập nhật.
            data: Dữ liệu cập nhật.

        Returns:
            Đối tượng Author đã được cập nhật.

        Raises:
            NotFoundException: Nếu không tìm thấy tác giả.
            ConflictException: Nếu slug mới đã tồn tại.
        """
        author = await self.get_by_id(author_id)
        if not author:
            raise NotFoundException(detail=f"Không tìm thấy tác giả với ID {author_id}")

        new_slug = data.get("slug")
        if new_slug and new_slug != author.slug:
            existing = await self.get_by_slug(new_slug)
            if existing:
                raise ConflictException(detail=f"Slug '{new_slug}' đã tồn tại.")

        allowed_fields = {
            "name",
            "slug",
            "biography",
            "birth_date",
            "death_date",
            "nationality",
            "website",
            "photo_url",
            "is_featured",
            "book_count",
        }
        for key, value in data.items():
            if key in allowed_fields:
                setattr(author, key, value)

        try:
            await self.db.commit()
            await self.db.refresh(author)
            return author
        except IntegrityError:
            await self.db.rollback()
            raise ConflictException(
                detail=f"Slug '{data.get('slug')}' đã tồn tại hoặc lỗi ràng buộc khác."
            )

    async def delete(self, author_id: int) -> bool:
        """Xóa tác giả. Sẽ thất bại nếu tác giả còn liên kết với sách (trừ khi có cascade).

        Args:
            author_id: ID của tác giả cần xóa.

        Returns:
            True nếu xóa thành công.

        Raises:
            NotFoundException: Nếu không tìm thấy tác giả.
            ForbiddenException: Nếu tác giả vẫn còn liên kết với sách (nếu không dùng cascade).
        """
        author = await self.get_by_id(author_id)
        if not author:
            raise NotFoundException(detail=f"Không tìm thấy tác giả với ID {author_id}")

        # Cách 1: Kiểm tra sách liên quan trước (cần load books)
        # author_with_books = await self.get_by_id(author_id, with_relations=["books"])
        # if author_with_books.books:
        #     raise ForbiddenException(detail="Không thể xóa tác giả có sách liên quan")
        # await self.db.delete(author)

        # Cách 2: Thử xóa và bắt lỗi IntegrityError (phụ thuộc vào DB constraint)
        try:
            await self.db.delete(author)
            await self.db.commit()
            return True
        except IntegrityError:
            await self.db.rollback()
            raise ForbiddenException(
                detail="Không thể xóa tác giả do còn liên kết với sách."
            )

    async def list_authors(
        self,
        skip: int = 0,
        limit: int = 100,
        search: Optional[str] = None,
        sort_by: str = "name",
        sort_desc: bool = False,
    ) -> List[Author]:
        """Lấy danh sách tác giả với tìm kiếm, sắp xếp và phân trang.

        Args:
            skip: Số lượng bỏ qua.
            limit: Số lượng tối đa.
            search: Từ khóa tìm kiếm (tên, tiểu sử).
            sort_by: Trường sắp xếp (ví dụ: name, book_count).
            sort_desc: Sắp xếp giảm dần.

        Returns:
            Danh sách các đối tượng Author.
        """
        query = select(Author)

        if search:
            search_term = f"%{search}%"
            query = query.filter(
                or_(Author.name.ilike(search_term), Author.biography.ilike(search_term))
            )

        # Sắp xếp
        sort_attr = getattr(Author, sort_by, Author.name)
        if sort_desc:
            query = query.order_by(desc(sort_attr))
        else:
            query = query.order_by(asc(sort_attr))

        # Phân trang
        query = query.offset(skip).limit(limit)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_featured_authors(self, limit: int = 10) -> List[Author]:
        """Lấy danh sách tác giả nổi bật."""
        query = (
            select(Author)
            .where(Author.is_featured == True)
            .order_by(desc(Author.name))
            .limit(limit)
        )
        result = await self.db.execute(query)
        return result.scalars().all()

    async def count_authors(self, search: Optional[str] = None) -> int:
        """Đếm số lượng tác giả với điều kiện tìm kiếm.

        Args:
            search: Từ khóa tìm kiếm.

        Returns:
            Tổng số tác giả khớp điều kiện.
        """
        query = select(func.count(Author.id))

        if search:
            search_term = f"%{search}%"
            query = query.filter(
                or_(Author.name.ilike(search_term), Author.biography.ilike(search_term))
            )

        result = await self.db.execute(query)
        return result.scalar_one() or 0

    async def get_author_book_count(self, author_id: int) -> int:
        """Đếm số lượng sách của tác giả (chỉ tính sách đã được liên kết)."""
        query = select(func.count(BookAuthor.book_id)).where(
            BookAuthor.author_id == author_id
        )
        result = await self.db.execute(query)
        return result.scalar_one() or 0

    async def get_books_by_author(
        self,
        author_id: int,
        skip: int = 0,
        limit: int = 20,
        only_published: bool = True,
        sort_by: str = "title",
        sort_desc: bool = False,
    ) -> List[Book]:
        """Lấy danh sách sách của tác giả với sắp xếp và phân trang.

        Args:
            author_id: ID của tác giả.
            skip: Số lượng bỏ qua.
            limit: Số lượng tối đa.
            only_published: Chỉ lấy sách đã xuất bản.
            sort_by: Trường sắp xếp sách (ví dụ: title, created_at).
            sort_desc: Sắp xếp giảm dần.

        Returns:
            Danh sách các đối tượng Book.
        """
        query = select(Book).join(BookAuthor).where(BookAuthor.author_id == author_id)

        if only_published:
            query = query.where(Book.is_published == True)

        # Sắp xếp sách
        sort_attr = getattr(Book, sort_by, Book.title)
        if sort_desc:
            query = query.order_by(desc(sort_attr))
        else:
            query = query.order_by(asc(sort_attr))

        # Phân trang
        query = query.offset(skip).limit(limit)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_popular_authors(self, limit: int = 10) -> List[Author]:
        """Lấy danh sách tác giả phổ biến dựa trên book_count."""
        query = select(Author).order_by(desc(Author.book_count)).limit(limit)
        result = await self.db.execute(query)
        return result.scalars().all()

    async def search_authors(self, query: str, limit: int = 10) -> List[Author]:
        """Tìm kiếm tác giả theo từ khóa (tên, tiểu sử)."""
        search_pattern = f"%{query}%"
        sql_query = (
            select(Author)
            .where(
                or_(
                    Author.name.ilike(search_pattern),
                    Author.biography.ilike(search_pattern),
                )
            )
            .order_by(Author.name)
            .limit(limit)
        )
        result = await self.db.execute(sql_query)
        return result.scalars().all()

    async def update_author_book_count(self, author_id: int) -> Author:
        """Cập nhật số lượng sách thực tế của tác giả và lưu vào DB.

        Args:
            author_id: ID của tác giả.

        Returns:
            Đối tượng Author đã cập nhật.

        Raises:
            NotFoundException: Nếu không tìm thấy tác giả.
        """
        author = await self.get_by_id(author_id)
        if not author:
            raise NotFoundException(detail=f"Không tìm thấy tác giả với ID {author_id}")

        book_count = await self.get_author_book_count(author_id)
        if author.book_count != book_count:
            author.book_count = book_count
            await self.db.commit()
            await self.db.refresh(author)
        return author

    async def get_or_create(self, name: str, **kwargs) -> Tuple[Author, bool]:
        """Lấy hoặc tạo tác giả mới nếu chưa tồn tại.

        Args:
            name: Tên tác giả.
            **kwargs: Các trường dữ liệu khác (slug, biography, etc.).

        Returns:
            Tuple chứa đối tượng Author và boolean (True nếu tạo mới, False nếu đã tồn tại).
        """
        author = await self.get_by_name(name)
        created = False
        if not author:
            # Tạo slug nếu chưa có
            if "slug" not in kwargs or not kwargs["slug"]:
                kwargs["slug"] = await self._generate_unique_slug(name)

            # Lọc kwargs trước khi tạo
            allowed_fields = {
                "slug",
                "biography",
                "birth_date",
                "death_date",
                "nationality",
                "website",
                "photo_url",
                "is_featured",
                "book_count",
            }
            filtered_kwargs = {k: v for k, v in kwargs.items() if k in allowed_fields}

            data = {"name": name, **filtered_kwargs}
            author = await self.create(data)
            created = True
        return author, created

    async def _generate_unique_slug(
        self, name: str, initial_slug: Optional[str] = None
    ) -> str:
        """Tạo slug duy nhất cho tác giả.

        Args:
            name: Tên tác giả để tạo slug gốc.
            initial_slug: Slug ban đầu (nếu có).

        Returns:
            Slug duy nhất.
        """
        slug = initial_slug or slugify(name)
        base_slug = slug
        counter = 1
        while await self.get_by_slug(slug):
            slug = f"{base_slug}-{counter}"
            counter += 1
        return slug
