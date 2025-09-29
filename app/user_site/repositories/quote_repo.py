from typing import Optional, List, Dict, Any
from sqlalchemy import select, update, delete, func, or_, and_, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timezone, timedelta

from app.user_site.models.quote import Quote, QuoteLike
from app.user_site.models.user import User
from app.user_site.models.book import Book
from app.user_site.models.chapter import Chapter
from app.user_site.models.tag import Tag
from app.core.exceptions import (
    NotFoundException,
    ValidationException,
    ConflictException,
)


class QuoteRepository:
    """Repository cho các thao tác CRUD và liệt kê Trích dẫn (Quote)."""

    def __init__(self, db: AsyncSession):
        """Khởi tạo repository với AsyncSession.

        Args:
            db: Đối tượng AsyncSession để tương tác với cơ sở dữ liệu.
        """
        self.db = db

    async def _validate_dependencies(
        self, user_id: int, book_id: int, chapter_id: Optional[int] = None
    ):
        """(Nội bộ) Kiểm tra sự tồn tại của user, book và chapter (nếu có)."""
        user = await self.db.get(User, user_id)
        if not user:
            raise ValidationException(f"Người dùng với ID {user_id} không tồn tại.")
        book = await self.db.get(Book, book_id)
        if not book:
            raise ValidationException(f"Sách với ID {book_id} không tồn tại.")
        if chapter_id:
            chapter = await self.db.get(Chapter, chapter_id)
            if not chapter:
                raise ValidationException(f"Chương với ID {chapter_id} không tồn tại.")
            if chapter.book_id != book_id:
                raise ValidationException(
                    f"Chương {chapter_id} không thuộc về sách {book_id}."
                )

    async def _process_tags(self, tag_names: Optional[List[str]] = None) -> List[Tag]:
        """(Nội bộ) Xử lý danh sách tên tag, trả về danh sách đối tượng Tag.
        Tạo tag mới nếu chưa tồn tại.
        """
        if not tag_names:
            return []

        existing_tags_query = select(Tag).where(Tag.name.in_(tag_names))
        result = await self.db.execute(existing_tags_query)
        existing_tags = result.scalars().all()
        existing_tag_map = {tag.name: tag for tag in existing_tags}

        tags_to_return = list(existing_tags)
        new_tag_names = set(tag_names) - set(existing_tag_map.keys())

        if new_tag_names:
            new_tags = [Tag(name=name) for name in new_tag_names]
            self.db.add_all(new_tags)
            try:
                await self.db.flush()  # Flush để lấy ID hoặc xử lý lỗi constraint
                tags_to_return.extend(new_tags)
            except IntegrityError:
                await self.db.rollback()  # Rollback nếu có lỗi (vd: tag trùng tên do race condition)
                # Thử lấy lại các tag vừa tạo mà gây lỗi
                retry_query = select(Tag).where(Tag.name.in_(new_tag_names))
                retry_result = await self.db.execute(retry_query)
                tags_to_return.extend(retry_result.scalars().all())
                # Loại bỏ trùng lặp nếu cần (dù không nên xảy ra nhiều)
                tags_to_return = list({tag.id: tag for tag in tags_to_return}.values())

        return tags_to_return

    async def create(self, quote_data: Dict[str, Any]) -> Quote:
        """Tạo trích dẫn mới.

        Args:
            quote_data: Dict chứa dữ liệu cho trích dẫn mới.
                        Bao gồm user_id, book_id, content, và các trường tùy chọn khác
                        như chapter_id, page_number, location_in_book, note, is_public, tags (list[str]).

        Returns:
            Đối tượng Quote đã được tạo.

        Raises:
            ValidationException: Nếu user_id, book_id không tồn tại hoặc dữ liệu không hợp lệ.
            ConflictException: Nếu có lỗi ràng buộc.
        """
        user_id = quote_data.get("user_id")
        book_id = quote_data.get("book_id")
        chapter_id = quote_data.get("chapter_id")
        content = quote_data.get("content")

        if not user_id or not book_id or not content:
            raise ValidationException(
                "Thiếu thông tin bắt buộc: user_id, book_id, content."
            )

        await self._validate_dependencies(user_id, book_id, chapter_id)

        # Lọc các trường hợp lệ của Quote model
        allowed_fields = {
            col.name
            for col in Quote.__table__.columns
            if col.name not in ["id", "created_at", "updated_at", "likes_count"]
        }
        filtered_data = {
            k: v for k, v in quote_data.items() if k in allowed_fields and v is not None
        }

        # Xử lý tags
        tag_names = quote_data.get("tags")
        tags = await self._process_tags(tag_names)

        quote = Quote(**filtered_data)
        quote.tags = tags  # Gán danh sách đối tượng Tag

        self.db.add(quote)
        try:
            await self.db.commit()
            await self.db.refresh(
                quote, attribute_names=["user", "book", "chapter", "tags"]
            )  # Refresh quan hệ
            return quote
        except IntegrityError as e:
            await self.db.rollback()
            raise ConflictException(f"Không thể tạo trích dẫn: {e}")

    async def get_by_id(
        self, quote_id: int, with_relations: List[str] = None
    ) -> Optional[Quote]:
        """Lấy trích dẫn theo ID, tùy chọn tải các quan hệ.

        Args:
            quote_id: ID của trích dẫn.
            with_relations: Danh sách tên các quan hệ cần tải (vd: ['user', 'book', 'tags', 'likes']).

        Returns:
            Đối tượng Quote hoặc None nếu không tìm thấy.
        """
        query = select(Quote).where(Quote.id == quote_id)

        if with_relations:
            options = []
            if "user" in with_relations:
                options.append(selectinload(Quote.user))
            if "book" in with_relations:
                options.append(selectinload(Quote.book))
            if "chapter" in with_relations:
                options.append(selectinload(Quote.chapter))
            if "tags" in with_relations:
                options.append(selectinload(Quote.tags))
            if "likes" in with_relations:  # Lấy danh sách QuoteLike
                options.append(selectinload(Quote.likes).selectinload(QuoteLike.user))
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().first()

    async def list_quotes(
        self,
        user_id: Optional[int] = None,
        book_id: Optional[int] = None,
        tag_name: Optional[str] = None,
        search_term: Optional[str] = None,
        only_public: bool = False,
        skip: int = 0,
        limit: int = 20,
        sort_by: str = "created_at",  # Mặc định: created_at, có thể là 'likes_count', 'updated_at'
        sort_desc: bool = True,
        with_relations: List[str] = None,  # vd: ['user', 'book', 'tags']
    ) -> List[Quote]:
        """Liệt kê trích dẫn với các bộ lọc và tùy chọn sắp xếp, phân trang.

        Args:
            user_id: Lọc theo ID người dùng.
            book_id: Lọc theo ID sách.
            tag_name: Lọc theo tên tag.
            search_term: Tìm kiếm trong nội dung trích dẫn hoặc ghi chú.
            only_public: Chỉ lấy các trích dẫn công khai.
            skip: Số lượng bỏ qua.
            limit: Giới hạn số lượng.
            sort_by: Trường để sắp xếp ('created_at', 'likes_count', 'updated_at').
            sort_desc: Sắp xếp giảm dần (True) hay tăng dần (False).
            with_relations: Danh sách quan hệ cần tải.

        Returns:
            Danh sách các đối tượng Quote.
        """
        query = select(Quote)

        if user_id is not None:
            query = query.where(Quote.user_id == user_id)
        if book_id is not None:
            query = query.where(Quote.book_id == book_id)
        if only_public:
            query = query.where(Quote.is_public == True)

        if tag_name:
            query = query.join(Quote.tags).where(Tag.name == tag_name)

        if search_term:
            search_pattern = f"%{search_term}%"
            query = query.where(
                or_(
                    Quote.content.ilike(search_pattern),
                    Quote.note.ilike(search_pattern),
                )
            )

        # Sắp xếp
        sort_column = Quote.created_at  # Mặc định
        if sort_by == "likes_count":
            # Cần tính toán hoặc join với count subquery nếu không dùng trường denormalized
            # Tạm thời dùng trường likes_count nếu có
            if hasattr(Quote, "likes_count"):
                sort_column = Quote.likes_count
            # Nếu không có trường likes_count, cần cách khác để sắp xếp theo like
            # Ví dụ: subquery đếm like hoặc join và group by (phức tạp hơn)
        elif sort_by == "updated_at":
            sort_column = Quote.updated_at

        order = desc(sort_column) if sort_desc else asc(sort_column)
        query = query.order_by(order)

        # Phân trang
        query = query.offset(skip).limit(limit)

        # Tải quan hệ
        if with_relations:
            options = []
            if "user" in with_relations:
                options.append(selectinload(Quote.user))
            if "book" in with_relations:
                options.append(selectinload(Quote.book))
            if "chapter" in with_relations:
                options.append(selectinload(Quote.chapter))
            if "tags" in with_relations:
                options.append(selectinload(Quote.tags))
            # Không tải 'likes' ở list để tránh quá nhiều dữ liệu
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().unique().all()  # unique() để loại bỏ trùng lặp do join

    async def count_quotes(
        self,
        user_id: Optional[int] = None,
        book_id: Optional[int] = None,
        tag_name: Optional[str] = None,
        search_term: Optional[str] = None,
        only_public: bool = False,
    ) -> int:
        """Đếm số lượng trích dẫn với các bộ lọc.

        Args:
            user_id: Lọc theo ID người dùng.
            book_id: Lọc theo ID sách.
            tag_name: Lọc theo tên tag.
            search_term: Tìm kiếm trong nội dung trích dẫn hoặc ghi chú.
            only_public: Chỉ đếm các trích dẫn công khai.

        Returns:
            Tổng số trích dẫn khớp điều kiện.
        """
        query = select(func.count(Quote.id))

        if user_id is not None:
            query = query.where(Quote.user_id == user_id)
        if book_id is not None:
            query = query.where(Quote.book_id == book_id)
        if only_public:
            query = query.where(Quote.is_public == True)

        if tag_name:
            # Cần join để lọc theo tag
            query = query.join(Quote.tags).where(Tag.name == tag_name)

        if search_term:
            search_pattern = f"%{search_term}%"
            query = query.where(
                or_(
                    Quote.content.ilike(search_pattern),
                    Quote.note.ilike(search_pattern),
                )
            )

        # Nếu có join (vd: tag_name), cần select count(distinct(Quote.id))
        if tag_name:
            query = select(func.count(func.distinct(Quote.id))).select_from(Quote)
            query = query.join(Quote.tags).where(Tag.name == tag_name)
            # Áp dụng lại các bộ lọc khác vào query mới này
            if user_id is not None:
                query = query.where(Quote.user_id == user_id)
            if book_id is not None:
                query = query.where(Quote.book_id == book_id)
            if only_public:
                query = query.where(Quote.is_public == True)
            if search_term:
                query = query.where(
                    or_(
                        Quote.content.ilike(search_pattern),
                        Quote.note.ilike(search_pattern),
                    )
                )
        else:
            # Select from Quote để where hoạt động đúng
            query = query.select_from(Quote)

        result = await self.db.execute(query)
        return result.scalar_one() or 0

    async def update(
        self, quote_id: int, quote_data: Dict[str, Any]
    ) -> Optional[Quote]:
        """Cập nhật thông tin trích dẫn.

        Args:
            quote_id: ID của trích dẫn cần cập nhật.
            quote_data: Dict chứa dữ liệu cập nhật.
                        Có thể chứa content, page_number, location_in_book, note, is_public, tags (list[str]).
                        Không cho phép cập nhật user_id, book_id, chapter_id.

        Returns:
            Đối tượng Quote đã được cập nhật, hoặc None nếu không tìm thấy.

        Raises:
            ValidationException: Nếu dữ liệu không hợp lệ.
            ConflictException: Nếu có lỗi ràng buộc.
        """
        quote = await self.get_by_id(
            quote_id, with_relations=["tags"]
        )  # Load tags để cập nhật
        if not quote:
            return None  # Hoặc raise NotFoundException tùy vào logic gọi

        # Lọc các trường được phép cập nhật
        allowed_fields = {
            "content",
            "page_number",
            "location_in_book",
            "note",
            "is_public",
        }
        updated = False

        for key, value in quote_data.items():
            if key in allowed_fields and value is not None:
                if getattr(quote, key) != value:
                    setattr(quote, key, value)
                    updated = True

        # Xử lý cập nhật tags
        if "tags" in quote_data:
            new_tag_names = quote_data["tags"]
            if isinstance(new_tag_names, list):
                new_tags = await self._process_tags(new_tag_names)
                # Chỉ cập nhật nếu danh sách tag thực sự thay đổi
                if set(t.id for t in quote.tags) != set(t.id for t in new_tags):
                    quote.tags = new_tags
                    updated = True
            else:
                # Có thể log warning hoặc raise lỗi nếu kiểu dữ liệu tags không đúng
                pass

        if updated:
            try:
                await self.db.commit()
                await self.db.refresh(
                    quote, attribute_names=["user", "book", "chapter", "tags"]
                )
            except IntegrityError as e:
                await self.db.rollback()
                raise ConflictException(f"Không thể cập nhật trích dẫn: {e}")

        return quote

    async def delete(self, quote_id: int) -> bool:
        """Xóa trích dẫn.
           Lưu ý: Cần xử lý các QuoteLike liên quan (có thể dùng cascade delete trong model
           hoặc xóa chúng ở đây trước khi xóa quote).
           Hiện tại, giả sử cascade delete được cấu hình hoặc không cần xóa like.

        Args:
            quote_id: ID của trích dẫn cần xóa.

        Returns:
            True nếu xóa thành công, False nếu không tìm thấy.
        """
        # Tùy chọn: Xóa các likes liên quan trước nếu không có cascade
        # like_delete_query = delete(QuoteLike).where(QuoteLike.quote_id == quote_id)
        # await self.db.execute(like_delete_query)

        query = delete(Quote).where(Quote.id == quote_id)
        result = await self.db.execute(query)
        await self.db.commit()
        return result.rowcount > 0

    async def get_likes_count(self, quote_id: int) -> int:
        """Lấy số lượt thích hiện tại của một trích dẫn."""
        query = select(func.count(QuoteLike.id)).where(QuoteLike.quote_id == quote_id)
        result = await self.db.execute(query)
        return result.scalar_one() or 0

    # Các phương thức liên quan đến QuoteLike đã được chuyển sang QuoteLikeRepository
    # Giữ lại các phương thức list tiện ích nếu cần

    async def list_liked_quotes(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 20,
        with_relations: List[str] = None,  # vd: ['book', 'user']
    ) -> List[Quote]:
        """Liệt kê trích dẫn đã thích của người dùng.
        (Sử dụng join với QuoteLike)
        """
        query = select(Quote).join(QuoteLike).where(QuoteLike.user_id == user_id)

        if with_relations:
            options = []
            if "user" in with_relations:  # User tạo quote
                options.append(selectinload(Quote.user))
            if "book" in with_relations:
                options.append(selectinload(Quote.book))
            if "tags" in with_relations:
                options.append(selectinload(Quote.tags))
            if options:
                query = query.options(*options)

        query = query.order_by(desc(QuoteLike.created_at)).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return result.scalars().unique().all()

    async def list_popular_quotes(
        self,
        limit: int = 10,
        book_id: Optional[int] = None,
        time_period_days: Optional[int] = None,  # Lọc theo thời gian nếu cần
        with_relations: List[str] = None,  # vd: ['user', 'book']
    ) -> List[Quote]:
        """Lấy danh sách trích dẫn công khai phổ biến nhất (dựa vào số lượt thích).
        Sử dụng subquery để đếm likes và sắp xếp.
        """
        # Subquery để đếm likes cho mỗi quote công khai
        like_count_subquery = (
            select(QuoteLike.quote_id, func.count(QuoteLike.id).label("like_count"))
            .group_by(QuoteLike.quote_id)
            .subquery()
        )

        query = (
            select(Quote)
            .join(
                like_count_subquery,
                Quote.id == like_count_subquery.c.quote_id,
                isouter=True,  # Left join để giữ quote không có like
            )
            .where(Quote.is_public == True)
        )

        if book_id is not None:
            query = query.where(Quote.book_id == book_id)

        if time_period_days is not None:
            since_date = datetime.now(timezone.utc) - timedelta(days=time_period_days)
            query = query.where(Quote.created_at >= since_date)  # Lọc quote mới
            # Hoặc lọc theo thời gian like nếu cần (phức tạp hơn)

        # Sắp xếp theo like_count (coalesce để quote không có like có count = 0)
        query = query.order_by(desc(func.coalesce(like_count_subquery.c.like_count, 0)))

        query = query.limit(limit)

        # Tải quan hệ
        if with_relations:
            options = []
            if "user" in with_relations:
                options.append(selectinload(Quote.user))
            if "book" in with_relations:
                options.append(selectinload(Quote.book))
            if "tags" in with_relations:
                options.append(selectinload(Quote.tags))
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().unique().all()

    async def get_random_quotes(
        self,
        limit: int = 5,
        book_id: Optional[int] = None,
        tag_name: Optional[str] = None,
        user_id: Optional[int] = None,  # Lấy random từ user cụ thể?
        with_relations: List[str] = None,  # vd: ['user', 'book']
    ) -> List[Quote]:
        """Lấy ngẫu nhiên một số trích dẫn công khai.
        Lưu ý: func.random() hoạt động khác nhau trên các DB.
        """
        query = select(Quote).where(Quote.is_public == True)

        if book_id is not None:
            query = query.where(Quote.book_id == book_id)
        if user_id is not None:
            query = query.where(Quote.user_id == user_id)
        if tag_name:
            query = query.join(Quote.tags).where(Tag.name == tag_name)

        # Sắp xếp ngẫu nhiên
        query = query.order_by(func.random())  # Hoặc text('RANDOM()') tùy DB

        query = query.limit(limit)

        if with_relations:
            options = []
            if "user" in with_relations:
                options.append(selectinload(Quote.user))
            if "book" in with_relations:
                options.append(selectinload(Quote.book))
            if "tags" in with_relations:
                options.append(selectinload(Quote.tags))
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().unique().all()
