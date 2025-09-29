from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy import select, update, delete, func, or_, and_, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.exc import IntegrityError

from app.user_site.models.category import Category, BookCategory
from app.user_site.models.book import Book
from app.core.exceptions import NotFoundException, ForbiddenException, ConflictException

# Slugify helper (tương tự author_repo)
try:
    from slugify import slugify
except ImportError:
    import re

    def slugify(text):
        text = re.sub(r"[\s\W]+", "-", text)
        return text.lower().strip("-")


class CategoryRepository:
    """Repository cho các thao tác với danh mục (Category) và liên kết sách (BookCategory)."""

    def __init__(self, db: AsyncSession):
        """Khởi tạo repository với AsyncSession."""
        self.db = db

    async def create(self, category_data: Dict[str, Any]) -> Category:
        """Tạo một danh mục mới.

        Args:
            category_data: Dữ liệu danh mục (name, slug, description, parent_id, etc.).

        Returns:
            Đối tượng Category đã tạo.

        Raises:
            ConflictException: Nếu slug đã tồn tại.
            NotFoundException: Nếu parent_id không hợp lệ.
        """
        slug = category_data.get("slug")
        if slug:
            existing = await self.get_by_slug(slug)
            if existing:
                raise ConflictException(detail=f"Slug '{slug}' đã tồn tại.")
        elif "name" in category_data:
            category_data["slug"] = await self._generate_unique_slug(
                category_data["name"]
            )

        # Kiểm tra parent_id nếu có
        parent_id = category_data.get("parent_id")
        if parent_id:
            parent_cat = await self.get_by_id(parent_id)
            if not parent_cat:
                raise NotFoundException(
                    detail=f"Danh mục cha với ID {parent_id} không tồn tại."
                )

        allowed_fields = {
            "name",
            "slug",
            "description",
            "parent_id",
            "icon_url",
            "is_featured",
            "book_count",
        }
        filtered_data = {k: v for k, v in category_data.items() if k in allowed_fields}

        category = Category(**filtered_data)
        self.db.add(category)
        try:
            await self.db.commit()
            await self.db.refresh(category)
            return category
        except IntegrityError as e:
            await self.db.rollback()
            if "uq_categories_slug" in str(e):
                raise ConflictException(
                    detail=f"Slug '{category_data.get('slug')}' đã tồn tại."
                )
            elif (
                "foreign key constraint" in str(e).lower()
                and "parent_id" in str(e).lower()
            ):
                raise NotFoundException(
                    detail=f"Danh mục cha với ID {parent_id} không hợp lệ."
                )
            else:
                raise

    async def get_by_id(
        self, category_id: int, with_relations: Optional[List[str]] = None
    ) -> Optional[Category]:
        """Lấy danh mục theo ID.

        Args:
            category_id: ID của danh mục.
            with_relations: Quan hệ cần load (["parent", "children", "books"]).

        Returns:
            Đối tượng Category hoặc None.
        """
        query = select(Category).where(Category.id == category_id)

        if with_relations:
            options = []
            if "parent" in with_relations:
                options.append(selectinload(Category.parent))
            if "children" in with_relations:
                options.append(selectinload(Category.children))
            if "books" in with_relations:
                options.append(selectinload(Category.books))
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_by_name(self, name: str) -> Optional[Category]:
        """Lấy danh mục theo tên (phân biệt chữ hoa/thường)."""
        query = select(Category).where(Category.name == name)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_by_slug(
        self, slug: str, with_relations: Optional[List[str]] = None
    ) -> Optional[Category]:
        """Lấy danh mục theo slug.

        Args:
            slug: Slug của danh mục.
            with_relations: Quan hệ cần load.

        Returns:
            Đối tượng Category hoặc None.
        """
        query = select(Category).where(Category.slug == slug)
        if with_relations:
            options = []
            if "parent" in with_relations:
                options.append(selectinload(Category.parent))
            if "children" in with_relations:
                options.append(selectinload(Category.children))
            if "books" in with_relations:
                options.append(selectinload(Category.books))
            if options:
                query = query.options(*options)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def update(self, category_id: int, data: Dict[str, Any]) -> Category:
        """Cập nhật thông tin danh mục.

        Args:
            category_id: ID danh mục cần cập nhật.
            data: Dữ liệu cập nhật.

        Returns:
            Đối tượng Category đã cập nhật.

        Raises:
            NotFoundException: Nếu không tìm thấy danh mục hoặc parent_id mới không hợp lệ.
            ConflictException: Nếu slug mới bị trùng.
            ValueError: Nếu cố gắng đặt parent_id là chính nó hoặc con của nó.
        """
        category = await self.get_by_id(
            category_id, with_relations=["children"]
        )  # Load children để kiểm tra vòng lặp
        if not category:
            raise NotFoundException(
                detail=f"Không tìm thấy danh mục với ID {category_id}"
            )

        new_slug = data.get("slug")
        if new_slug and new_slug != category.slug:
            existing = await self.get_by_slug(new_slug)
            if existing:
                raise ConflictException(detail=f"Slug '{new_slug}' đã tồn tại.")

        new_parent_id = data.get("parent_id")
        if new_parent_id is not None and new_parent_id != category.parent_id:
            if new_parent_id == category.id:
                raise ValueError("Không thể đặt danh mục làm cha của chính nó.")
            # Kiểm tra vòng lặp: parent_id mới không được là một trong các con của category hiện tại
            children_ids = {child.id for child in category.children}
            if new_parent_id in children_ids:
                raise ValueError("Không thể đặt danh mục con làm danh mục cha.")
            # Kiểm tra parent mới có tồn tại không
            parent_cat = await self.get_by_id(new_parent_id)
            if not parent_cat:
                raise NotFoundException(
                    detail=f"Danh mục cha mới với ID {new_parent_id} không tồn tại."
                )

        allowed_fields = {
            "name",
            "slug",
            "description",
            "parent_id",
            "icon_url",
            "is_featured",
            "book_count",
        }
        for key, value in data.items():
            if key in allowed_fields:
                setattr(category, key, value)

        try:
            await self.db.commit()
            await self.db.refresh(category)
            return category
        except IntegrityError as e:
            await self.db.rollback()
            if "uq_categories_slug" in str(e):
                raise ConflictException(detail=f"Slug '{data.get('slug')}' đã tồn tại.")
            elif (
                "foreign key constraint" in str(e).lower()
                and "parent_id" in str(e).lower()
            ):
                raise NotFoundException(
                    detail=f"Danh mục cha mới với ID {new_parent_id} không hợp lệ."
                )
            else:
                raise

    async def delete(self, category_id: int) -> bool:
        """Xóa danh mục.

        Args:
            category_id: ID danh mục cần xóa.

        Returns:
            True nếu xóa thành công.

        Raises:
            NotFoundException: Nếu không tìm thấy danh mục.
            ForbiddenException: Nếu danh mục có con hoặc có sách liên kết (nếu không dùng cascade).
        """
        category = await self.get_by_id(category_id)
        if not category:
            raise NotFoundException(
                detail=f"Không tìm thấy danh mục với ID {category_id}"
            )

        # Kiểm tra danh mục con
        children_count = await self.count_categories(parent_id=category_id)
        if children_count > 0:
            raise ForbiddenException(
                detail="Không thể xóa danh mục có chứa danh mục con"
            )

        # Kiểm tra sách liên kết (nếu không có cascade)
        # book_count = await self.get_category_book_count(category_id)
        # if book_count > 0:
        #     raise ForbiddenException(detail="Không thể xóa danh mục có sách liên kết")

        try:
            await self.db.delete(category)
            await self.db.commit()
            return True
        except IntegrityError:
            # Lỗi này có thể xảy ra nếu có sách liên kết và không có cascade
            await self.db.rollback()
            raise ForbiddenException(
                detail="Không thể xóa danh mục do còn sách liên kết."
            )

    async def list_categories(
        self,
        parent_id: Optional[
            int
        ] = -1,  # Dùng -1 để phân biệt None (gốc) và 0 (nếu ID 0 hợp lệ)
        skip: int = 0,
        limit: int = 100,
        sort_by: str = "name",
        sort_desc: bool = False,
        with_relations: Optional[List[str]] = None,
    ) -> List[Category]:
        """Lấy danh sách danh mục, có thể lọc theo parent_id.

        Args:
            parent_id: ID danh mục cha. Nếu None (mặc định), lấy danh mục gốc.
            skip, limit: Phân trang.
            sort_by, sort_desc: Sắp xếp.
            with_relations: Quan hệ cần load.

        Returns:
            Danh sách Category.
        """
        query = select(Category)

        if parent_id == -1:  # Lấy danh mục gốc
            query = query.where(Category.parent_id.is_(None))
        else:  # Lấy con của parent_id cụ thể
            query = query.where(Category.parent_id == parent_id)

        sort_attr = getattr(Category, sort_by, Category.name)
        if sort_desc:
            query = query.order_by(desc(sort_attr))
        else:
            query = query.order_by(asc(sort_attr))

        query = query.offset(skip).limit(limit)

        if with_relations:
            options = []
            if "parent" in with_relations:
                options.append(selectinload(Category.parent))
            if "children" in with_relations:
                options.append(selectinload(Category.children))
            if "books" in with_relations:
                options.append(selectinload(Category.books))
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_root_categories(
        self, with_relations: Optional[List[str]] = None
    ) -> List[Category]:
        """Lấy danh sách danh mục gốc (không có cha)."""
        return await self.list_categories(
            parent_id=-1, limit=1000, with_relations=with_relations
        )  # Lấy hết gốc

    async def get_featured_categories(
        self, limit: int = 10, with_relations: Optional[List[str]] = None
    ) -> List[Category]:
        """Lấy danh sách danh mục nổi bật."""
        query = (
            select(Category)
            .where(Category.is_featured == True)
            .order_by(Category.name)
            .limit(limit)
        )
        if with_relations:
            options = []
            if "parent" in with_relations:
                options.append(selectinload(Category.parent))
            if "children" in with_relations:
                options.append(selectinload(Category.children))
            if options:
                query = query.options(*options)
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_subcategories(
        self, parent_id: int, with_relations: Optional[List[str]] = None
    ) -> List[Category]:
        """Lấy danh sách danh mục con trực tiếp của một danh mục."""
        return await self.list_categories(
            parent_id=parent_id, limit=1000, with_relations=with_relations
        )  # Lấy hết con

    async def count_categories(
        self, parent_id: Optional[int] = -1, search_query: Optional[str] = None
    ) -> int:
        """Đếm số lượng danh mục.

        Args:
            parent_id: Lọc theo ID cha (-1 cho gốc).
            search_query: Tìm kiếm theo name/description.

        Returns:
            Tổng số danh mục khớp điều kiện.
        """
        query = select(func.count(Category.id))

        if parent_id == -1:
            query = query.where(Category.parent_id.is_(None))
        else:
            query = query.where(Category.parent_id == parent_id)

        if search_query:
            search_pattern = f"%{search_query}%"
            query = query.filter(
                or_(
                    Category.name.ilike(search_pattern),
                    Category.description.ilike(search_pattern),
                )
            )

        result = await self.db.execute(query)
        return result.scalar_one() or 0

    async def get_category_book_count(
        self, category_id: int, only_published: bool = True
    ) -> int:
        """Đếm số lượng sách của danh mục, có thể chỉ tính sách đã xuất bản."""
        query = select(func.count(BookCategory.book_id)).where(
            BookCategory.category_id == category_id
        )
        if only_published:
            query = query.join(Book).where(Book.is_published == True)
        result = await self.db.execute(query)
        return result.scalar_one() or 0

    async def get_books_by_category(
        self,
        category_id: int,
        skip: int = 0,
        limit: int = 20,
        only_published: bool = True,
        sort_by: str = "title",
        sort_desc: bool = False,
        recursive: bool = False,  # Thêm tùy chọn lấy sách từ cả danh mục con
        with_relations: Optional[List[str]] = ["authors"],  # Load authors cho sách
    ) -> List[Book]:
        """Lấy danh sách sách của danh mục (và tùy chọn của các danh mục con).

        Args:
            category_id: ID danh mục gốc.
            skip, limit: Phân trang.
            only_published: Chỉ lấy sách đã xuất bản.
            sort_by, sort_desc: Sắp xếp sách.
            recursive: Lấy sách từ cả danh mục con.
            with_relations: Quan hệ cần load cho đối tượng Book.

        Returns:
            Danh sách Book.
        """
        category_ids_to_query = [category_id]
        if recursive:
            # Lấy ID của tất cả danh mục con (cần hàm đệ quy hoặc CTE nếu nhiều cấp)
            # Ví dụ đơn giản cho 1 cấp con:
            sub_cats = await self.get_subcategories(category_id)
            category_ids_to_query.extend([sub.id for sub in sub_cats])
            # Cần giải pháp đệ quy hoàn chỉnh cho cây đa cấp

        query = (
            select(Book)
            .join(BookCategory)
            .where(BookCategory.category_id.in_(category_ids_to_query))
        )

        if only_published:
            query = query.where(Book.is_published == True)

        sort_attr = getattr(Book, sort_by, Book.title)
        if sort_desc:
            query = query.order_by(desc(sort_attr))
        else:
            query = query.order_by(asc(sort_attr))

        query = query.offset(skip).limit(limit)

        if with_relations:
            options = []
            if "authors" in with_relations:
                options.append(selectinload(Book.authors))
            if "categories" in with_relations:
                options.append(selectinload(Book.categories))  # Load lại cat?
            if "tags" in with_relations:
                options.append(selectinload(Book.tags))
            if "publisher" in with_relations:
                options.append(selectinload(Book.publisher))
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return (
            result.scalars().unique().all()
        )  # Dùng unique vì sách có thể thuộc nhiều category con

    async def get_all_categories(
        self, sort_by: str = "name", sort_desc: bool = False
    ) -> List[Category]:
        """Lấy tất cả danh mục, sắp xếp theo tên."""
        query = select(Category)
        sort_attr = getattr(Category, sort_by, Category.name)
        if sort_desc:
            query = query.order_by(desc(sort_attr))
        else:
            query = query.order_by(asc(sort_attr))
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_categories_with_book_count(
        self, only_published: bool = True
    ) -> List[Dict[str, Any]]:
        """Lấy danh sách danh mục kèm số lượng sách (tối ưu hơn).

        Args:
            only_published: Chỉ đếm sách đã xuất bản.

        Returns:
            List of dicts, each with category info and book_count.
        """
        # Subquery để đếm sách
        book_count_query = select(
            BookCategory.category_id,
            func.count(BookCategory.book_id).label("book_count"),
        ).group_by(BookCategory.category_id)

        if only_published:
            book_count_query = book_count_query.join(Book).where(
                Book.is_published == True
            )

        book_count_sq = book_count_query.subquery()

        # Query chính join với subquery
        query = (
            select(
                Category,
                func.coalesce(book_count_sq.c.book_count, 0).label(
                    "calculated_book_count"
                ),
            )
            .outerjoin(book_count_sq, Category.id == book_count_sq.c.category_id)
            .order_by(Category.name)
        )

        result = await self.db.execute(query)

        categories_with_count = []
        for category, count in result:
            # Tạo dict thủ công hoặc dùng Pydantic schema
            category_dict = category.__dict__  # Lấy dict từ object
            # Loại bỏ các thuộc tính không cần thiết của SQLAlchemy
            category_dict.pop("_sa_instance_state", None)
            category_dict["book_count"] = count
            categories_with_count.append(category_dict)

        return categories_with_count

    async def search_categories(self, query: str, limit: int = 10) -> List[Category]:
        """Tìm kiếm danh mục theo từ khóa (name, description)."""
        search_pattern = f"%{query}%"
        sql_query = (
            select(Category)
            .where(
                or_(
                    Category.name.ilike(search_pattern),
                    Category.description.ilike(search_pattern),
                )
            )
            .order_by(Category.name)
            .limit(limit)
        )
        result = await self.db.execute(sql_query)
        return result.scalars().all()

    async def get_or_create(self, name: str, **kwargs) -> Tuple[Category, bool]:
        """Lấy hoặc tạo danh mục mới nếu chưa tồn tại.

        Args:
            name: Tên danh mục.
            **kwargs: Dữ liệu khác (slug, description, parent_id, etc.).

        Returns:
            Tuple (Category, bool) - bool là True nếu tạo mới.
        """
        category = await self.get_by_name(name)
        created = False
        if not category:
            if "slug" not in kwargs or not kwargs["slug"]:
                kwargs["slug"] = await self._generate_unique_slug(name)

            allowed_fields = {
                "slug",
                "description",
                "parent_id",
                "icon_url",
                "is_featured",
            }
            filtered_kwargs = {k: v for k, v in kwargs.items() if k in allowed_fields}
            data = {"name": name, **filtered_kwargs}
            category = await self.create(data)
            created = True
        return category, created

    async def get_category_tree(
        self, with_book_count: bool = False, only_published_books: bool = True
    ) -> List[Dict[str, Any]]:
        """Lấy cây phân cấp danh mục (chỉ hỗ trợ 2 cấp gốc -> con).

        Args:
            with_book_count: Có đính kèm số lượng sách không.
            only_published_books: Chỉ đếm sách đã xuất bản nếu with_book_count=True.

        Returns:
            Danh sách các dict đại diện cho cây danh mục.
        """
        root_categories = await self.get_root_categories()
        result_tree = []

        for root in root_categories:
            subcategories = await self.get_subcategories(root.id)
            root_dict = {
                "id": root.id,
                "name": root.name,
                "slug": root.slug,
                "icon_url": root.icon_url,
                "children": [],
            }
            if with_book_count:
                root_dict["book_count"] = await self.get_category_book_count(
                    root.id, only_published_books
                )

            for sub in subcategories:
                sub_dict = {
                    "id": sub.id,
                    "name": sub.name,
                    "slug": sub.slug,
                    "icon_url": sub.icon_url,
                }
                if with_book_count:
                    sub_dict["book_count"] = await self.get_category_book_count(
                        sub.id, only_published_books
                    )
                root_dict["children"].append(sub_dict)

            result_tree.append(root_dict)

        return result_tree

    async def update_category_book_count(
        self, category_id: int, only_published: bool = True
    ) -> Optional[Category]:
        """Cập nhật số lượng sách thực tế của danh mục và lưu vào DB.

        Args:
            category_id: ID của danh mục.
            only_published: Chỉ đếm sách đã xuất bản.

        Returns:
            Đối tượng Category đã cập nhật hoặc None nếu không tìm thấy.
        """
        category = await self.get_by_id(category_id)
        if not category:
            return None

        book_count = await self.get_category_book_count(category_id, only_published)
        if category.book_count != book_count:
            category.book_count = book_count
            await self.db.commit()
            await self.db.refresh(category)
        return category

    async def _generate_unique_slug(
        self, name: str, initial_slug: Optional[str] = None
    ) -> str:
        """Helper tạo slug duy nhất."""
        slug = initial_slug or slugify(name)
        base_slug = slug
        counter = 1
        while await self.get_by_slug(slug):
            slug = f"{base_slug}-{counter}"
            counter += 1
        return slug
