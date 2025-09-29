from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.user_site.repositories.category_repo import CategoryRepository
from app.user_site.repositories.book_repo import BookRepository
from app.core.exceptions import (
    NotFoundException,
    BadRequestException,
    ConflictException,
    ForbiddenException,
)
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate
from app.cache.decorators import cached, invalidate_cache
from app.performance.profiling.code_profiler import CodeProfiler
from app.monitoring.metrics import Metrics
from app.cache import get_cache


class CategoryService:
    """Service để quản lý danh mục sách."""

    def __init__(self, db: AsyncSession):
        """Khởi tạo service với AsyncSession."""
        self.db = db
        self.category_repo = CategoryRepository(db)
        self.book_repo = BookRepository(db)
        self.cache = get_cache()
        self.metrics = Metrics()
        self.profiler = CodeProfiler(enabled=True)

    async def create_category(
        self,
        name: str,
        description: Optional[str] = None,
        parent_id: Optional[int] = None,
        icon: Optional[str] = None,
        slug: Optional[str] = None,
        admin_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Tạo danh mục mới.

        Args:
            name: Tên danh mục
            description: Mô tả danh mục (tùy chọn)
            parent_id: ID của danh mục cha (tùy chọn)
            icon: Icon của danh mục (tùy chọn)
            slug: Slug định danh danh mục (tùy chọn)
            admin_id: ID của admin thực hiện hành động (tùy chọn)

        Returns:
            Thông tin danh mục đã tạo

        Raises:
            NotFoundException: Nếu danh mục cha không tồn tại
            ConflictException: Nếu tên hoặc slug đã tồn tại
        """
        # Kiểm tra parent_id nếu có
        if parent_id:
            parent = await self.category_repo.get_by_id(parent_id)
            if not parent:
                raise NotFoundException(
                    detail=f"Không tìm thấy danh mục cha với ID {parent_id}"
                )

        # Kiểm tra trùng lặp tên danh mục
        existing_by_name = await self.category_repo.get_by_name(name)
        if existing_by_name:
            raise ConflictException(detail=f"Đã tồn tại danh mục với tên '{name}'")

        # Kiểm tra trùng lặp slug nếu có
        if slug:
            existing_by_slug = await self.category_repo.get_by_slug(slug)
            if existing_by_slug:
                raise ConflictException(detail=f"Đã tồn tại danh mục với slug '{slug}'")

        # Tạo danh mục mới
        category = await self.category_repo.create(
            name=name,
            description=description,
            parent_id=parent_id,
            icon=icon,
            slug=slug,
        )

        # Log the creation activity if admin_id is provided
        if admin_id:
            try:
                await create_admin_activity_log(
                    self.db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="CREATE",
                        entity_type="CATEGORY",
                        entity_id=category.id,
                        description=f"Created category: {category.name}",
                        metadata={
                            "category_name": category.name,
                            "parent_id": parent_id,
                            "slug": category.slug,
                        },
                    ),
                )
            except Exception:
                # Log but don't fail if logging fails
                pass

        return {
            "id": category.id,
            "name": category.name,
            "description": category.description,
            "parent_id": category.parent_id,
            "icon": category.icon,
            "slug": category.slug,
            "created_at": category.created_at,
            "updated_at": category.updated_at,
        }

    @cached(
        ttl=3600,
        namespace="categories",
        tags=["category_detail"],
        key_builder=lambda *args, **kwargs: f"category:{kwargs.get('category_id')}",
    )
    async def get_category(self, category_id: int) -> Dict[str, Any]:
        """
        Lấy thông tin chi tiết của danh mục sách.

        Args:
            category_id: ID của danh mục

        Returns:
            Thông tin chi tiết danh mục

        Raises:
            NotFoundException: Nếu không tìm thấy danh mục
        """
        with self.profiler.profile("get_category"):
            category = await self.category_repo.get_by_id(
                category_id, with_relations=["parent", "children"]
            )

            if not category:
                raise NotFoundException(
                    detail=f"Không tìm thấy danh mục với ID {category_id}"
                )

            # Track metric
            self.metrics.track_user_activity("category_viewed")

            # Đếm số sách trong danh mục
            book_count = await self.category_repo.count_books_in_category(category_id)

            result = self._format_category_response(category)
            result["book_count"] = book_count

            return result

    async def get_category_by_slug(self, slug: str) -> Dict[str, Any]:
        """
        Lấy thông tin danh mục theo slug.

        Args:
            slug: Slug của danh mục

        Returns:
            Thông tin danh mục

        Raises:
            NotFoundException: Nếu danh mục không tồn tại
        """
        category = await self.category_repo.get_by_slug(slug, with_relations=True)
        if not category:
            raise NotFoundException(detail=f"Không tìm thấy danh mục với slug '{slug}'")

        result = {
            "id": category.id,
            "name": category.name,
            "description": category.description,
            "parent_id": category.parent_id,
            "icon": category.icon,
            "slug": category.slug,
            "created_at": category.created_at,
            "updated_at": category.updated_at,
        }

        # Thêm thông tin danh mục cha nếu có
        if hasattr(category, "parent") and category.parent:
            result["parent"] = {
                "id": category.parent.id,
                "name": category.parent.name,
                "slug": category.parent.slug,
            }

        # Thêm danh sách danh mục con nếu có
        if hasattr(category, "children") and category.children:
            result["children"] = [
                {
                    "id": child.id,
                    "name": child.name,
                    "slug": child.slug,
                    "icon": child.icon,
                }
                for child in category.children
            ]

        return result

    @cached(
        ttl=1800,
        namespace="categories",
        tags=["categories_list"],
        key_builder=lambda *args, **kwargs: (
            f"categories:{kwargs.get('parent_id', 'None')}:"
            f"{kwargs.get('skip')}:{kwargs.get('limit')}:"
            f"{kwargs.get('search_query', '')}"
        ),
    )
    async def list_categories(
        self,
        skip: int = 0,
        limit: int = 20,
        parent_id: Optional[int] = None,
        search_query: Optional[str] = None,
        include_tree: bool = False,
    ) -> Dict[str, Any]:
        """
        Liệt kê danh mục sách, có thể lọc theo danh mục cha.

        Args:
            skip: Số mục bỏ qua (phân trang)
            limit: Số mục tối đa trả về
            parent_id: ID danh mục cha (nếu None, lấy danh mục gốc)
            search_query: Từ khóa tìm kiếm (tùy chọn)
            include_tree: Có bao gồm cây danh mục con không

        Returns:
            Danh sách danh mục và tổng số
        """
        with self.profiler.profile("list_categories"):
            # Lấy danh sách danh mục
            categories = await self.category_repo.list_categories(
                skip, limit, parent_id, search_query, with_relations=["parent"]
            )

            # Đếm tổng số danh mục
            total = await self.category_repo.count_categories(parent_id, search_query)

            # Track metric
            self.metrics.track_user_activity("categories_listed")

            result = {
                "items": [self._format_category_response(cat) for cat in categories],
                "total": total,
            }

            # Nếu yêu cầu lấy cây danh mục
            if include_tree and not search_query:
                # Chỉ lấy cây khi không tìm kiếm để tránh kết quả không nhất quán
                tree = await self.get_category_tree(parent_id)
                result["tree"] = tree

            return result

    @cached(
        ttl=3600,
        namespace="categories",
        tags=["category_tree"],
        key_builder=lambda *args, **kwargs: f"category_tree:{kwargs.get('parent_id', 'None')}",
    )
    async def get_category_tree(
        self, parent_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Lấy cây danh mục, bắt đầu từ một danh mục cha hoặc từ gốc.

        Args:
            parent_id: ID danh mục cha (nếu None, lấy từ gốc)

        Returns:
            Cây danh mục dạng nested dictionary
        """
        with self.profiler.profile("get_category_tree"):
            # Lấy tất cả danh mục bắt đầu từ root hoặc parent_id
            categories = await self.category_repo.get_category_tree(parent_id)

            # Track metric
            self.metrics.track_user_activity("category_tree_viewed")

            # Xử lý thành cấu trúc cây
            root_categories = []
            category_map = {}

            # Tạo map các danh mục
            for cat in categories:
                cat_dict = self._format_category_response(cat)
                cat_dict["children"] = []
                category_map[cat.id] = cat_dict

            # Xây dựng cây
            for cat in categories:
                cat_dict = category_map[cat.id]

                if cat.parent_id is None or (
                    parent_id is not None and cat.id == parent_id
                ):
                    # Đây là root hoặc là parent được chỉ định
                    if parent_id is None or cat.id == parent_id:
                        root_categories.append(cat_dict)
                elif cat.parent_id in category_map:
                    # Thêm vào danh mục cha
                    category_map[cat.parent_id]["children"].append(cat_dict)

            return (
                root_categories
                if parent_id is None
                else category_map.get(parent_id, [])
            )

    @cached(
        ttl=1800,
        namespace="categories",
        tags=["category_books"],
        key_builder=lambda *args, **kwargs: (
            f"category_books:{kwargs.get('category_id')}:"
            f"{kwargs.get('skip')}:{kwargs.get('limit')}:"
            f"{kwargs.get('sort_by', 'popularity')}:"
            f"{kwargs.get('search_query', '')}"
        ),
    )
    async def list_books_by_category(
        self,
        category_id: int,
        skip: int = 0,
        limit: int = 20,
        sort_by: str = "popularity",
        search_query: Optional[str] = None,
        include_subcategories: bool = True,
    ) -> Dict[str, Any]:
        """
        Liệt kê sách thuộc danh mục.

        Args:
            category_id: ID danh mục
            skip: Số mục bỏ qua (phân trang)
            limit: Số mục tối đa trả về
            sort_by: Tiêu chí sắp xếp (popularity, latest, title, rating)
            search_query: Từ khóa tìm kiếm (tùy chọn)
            include_subcategories: Có lấy sách từ danh mục con không

        Returns:
            Danh sách sách thuộc danh mục và tổng số

        Raises:
            NotFoundException: Nếu không tìm thấy danh mục
        """
        # Kiểm tra danh mục tồn tại
        category = await self.category_repo.get_by_id(category_id)
        if not category:
            raise NotFoundException(
                detail=f"Không tìm thấy danh mục với ID {category_id}"
            )

        # Lấy danh sách ID danh mục con nếu bao gồm
        category_ids = [category_id]
        if include_subcategories:
            subcategory_ids = await self.category_repo.get_all_subcategory_ids(
                category_id
            )
            category_ids.extend(subcategory_ids)

        # Lấy danh sách sách
        books = await self.book_repo.list_books_by_categories(
            category_ids,
            skip,
            limit,
            sort_by,
            search_query,
            with_relations=["authors", "categories"],
        )

        # Đếm tổng số sách
        total = await self.book_repo.count_books_by_categories(
            category_ids, search_query
        )

        # Track metric
        self.metrics.track_user_activity("category_books_listed")

        # Format kết quả
        return {
            "items": [
                {
                    "id": book.id,
                    "title": book.title,
                    "cover_image": book.cover_image,
                    "cover_thumbnail_url": book.cover_thumbnail_url,
                    "author_names": (
                        [author.name for author in book.authors]
                        if hasattr(book, "authors") and book.authors
                        else []
                    ),
                    "rating": book.average_rating,
                    "description": book.description,
                    "categories": (
                        [{"id": cat.id, "name": cat.name} for cat in book.categories]
                        if hasattr(book, "categories") and book.categories
                        else []
                    ),
                    "published_date": book.published_date,
                    "created_at": book.created_at,
                    "updated_at": book.updated_at,
                }
                for book in books
            ],
            "total": total,
            "category": self._format_category_response(category),
        }

    @cached(
        ttl=1800,
        namespace="categories",
        tags=["popular_categories"],
        key_builder=lambda *args, **kwargs: f"popular_categories:{kwargs.get('limit')}",
    )
    async def get_popular_categories(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Lấy danh sách danh mục phổ biến, dựa trên số lượng sách và lượt đọc.

        Args:
            limit: Số lượng danh mục trả về

        Returns:
            Danh sách danh mục phổ biến
        """
        with self.profiler.profile("get_popular_categories"):
            # Lấy danh mục phổ biến
            categories = await self.category_repo.get_popular_categories(limit)

            # Track metric
            self.metrics.track_user_activity("popular_categories_viewed")

            # Format kết quả với số lượng sách
            result = []
            for cat in categories:
                category_data = self._format_category_response(cat)
                category_data["book_count"] = (
                    await self.category_repo.count_books_in_category(cat.id)
                )
                result.append(category_data)

            return result

    @cached(
        ttl=7200,
        namespace="categories",
        tags=["featured_categories"],
        key_builder=lambda *args, **kwargs: f"featured_categories:{kwargs.get('limit')}",
    )
    async def get_featured_categories(self, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Lấy danh sách danh mục nổi bật (được quản trị viên đánh dấu).

        Args:
            limit: Số lượng danh mục trả về

        Returns:
            Danh sách danh mục nổi bật
        """
        with self.profiler.profile("get_featured_categories"):
            # Lấy danh mục nổi bật
            categories = await self.category_repo.get_featured_categories(limit)

            # Track metric
            self.metrics.track_user_activity("featured_categories_viewed")

            # Format kết quả với số lượng sách
            result = []
            for cat in categories:
                category_data = self._format_category_response(cat)
                category_data["book_count"] = (
                    await self.category_repo.count_books_in_category(cat.id)
                )
                result.append(category_data)

            return result

    @cached(
        ttl=1800,
        namespace="categories",
        tags=["book_categories"],
        key_builder=lambda *args, **kwargs: f"book_categories:{kwargs.get('book_id')}",
    )
    async def get_book_categories(self, book_id: int) -> List[Dict[str, Any]]:
        """
        Lấy danh sách danh mục của một cuốn sách.

        Args:
            book_id: ID sách

        Returns:
            Danh sách danh mục của sách

        Raises:
            NotFoundException: Nếu không tìm thấy sách
        """
        # Kiểm tra sách tồn tại
        book = await self.book_repo.get_by_id(book_id)
        if not book:
            raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

        # Lấy danh mục của sách
        categories = await self.category_repo.get_book_categories(book_id)

        # Track metric
        self.metrics.track_user_activity("book_categories_viewed")

        return [self._format_category_response(cat) for cat in categories]

    def _format_category_response(self, category) -> Dict[str, Any]:
        """
        Chuyển đổi đối tượng category thành response dict.

        Args:
            category: Đối tượng Category từ database

        Returns:
            Dict thông tin category đã được format
        """
        result = {
            "id": category.id,
            "name": category.name,
            "slug": category.slug,
            "description": category.description,
            "parent_id": category.parent_id,
            "is_featured": category.is_featured,
            "icon": category.icon,
            "image_url": category.image_url,
            "created_at": category.created_at,
            "updated_at": category.updated_at,
        }

        # Thêm thông tin danh mục cha nếu đã load
        if hasattr(category, "parent") and category.parent:
            result["parent"] = {
                "id": category.parent.id,
                "name": category.parent.name,
                "slug": category.parent.slug,
            }

        # Thêm thông tin danh mục con nếu đã load
        if hasattr(category, "children") and category.children:
            result["children"] = [
                {
                    "id": child.id,
                    "name": child.name,
                    "slug": child.slug,
                    "parent_id": child.parent_id,
                }
                for child in category.children
            ]

        return result

    async def update_category(
        self, category_id: int, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Cập nhật thông tin danh mục.

        Args:
            category_id: ID của danh mục
            data: Dữ liệu cập nhật

        Returns:
            Thông tin danh mục đã cập nhật

        Raises:
            NotFoundException: Nếu danh mục không tồn tại
            ConflictException: Nếu tên hoặc slug mới đã tồn tại
            BadRequestException: Nếu danh mục cha không hợp lệ
        """
        # Kiểm tra danh mục tồn tại
        category = await self.category_repo.get_by_id(category_id)
        if not category:
            raise NotFoundException(
                detail=f"Không tìm thấy danh mục với ID {category_id}"
            )

        # Kiểm tra trùng lặp tên danh mục nếu có
        if "name" in data and data["name"] != category.name:
            existing_by_name = await self.category_repo.get_by_name(data["name"])
            if existing_by_name and existing_by_name.id != category_id:
                raise ConflictException(
                    detail=f"Đã tồn tại danh mục với tên '{data['name']}'"
                )

        # Kiểm tra trùng lặp slug nếu có
        if "slug" in data and data["slug"] and data["slug"] != category.slug:
            existing_by_slug = await self.category_repo.get_by_slug(data["slug"])
            if existing_by_slug and existing_by_slug.id != category_id:
                raise ConflictException(
                    detail=f"Đã tồn tại danh mục với slug '{data['slug']}'"
                )

        # Kiểm tra parent_id hợp lệ nếu có
        if "parent_id" in data and data["parent_id"]:
            # Không thể đặt chính nó làm danh mục cha
            if data["parent_id"] == category_id:
                raise BadRequestException(
                    detail="Không thể đặt danh mục làm danh mục cha của chính nó"
                )

            # Kiểm tra danh mục cha tồn tại
            parent = await self.category_repo.get_by_id(data["parent_id"])
            if not parent:
                raise NotFoundException(
                    detail=f"Không tìm thấy danh mục cha với ID {data['parent_id']}"
                )

            # Kiểm tra vòng lặp trong cây danh mục
            is_descendant = await self.category_repo.is_descendant(
                category_id, data["parent_id"]
            )
            if is_descendant:
                raise BadRequestException(
                    detail="Không thể tạo vòng lặp trong cây danh mục"
                )

        # Cập nhật
        updated = await self.category_repo.update(category_id, data)

        # Log the update activity if admin_id is provided
        if "admin_id" in data:
            try:
                # Track which fields were updated
                updated_fields = list(data.keys())
                updated_fields.remove("admin_id")

                await create_admin_activity_log(
                    self.db,
                    AdminActivityLogCreate(
                        admin_id=data["admin_id"],
                        activity_type="UPDATE",
                        entity_type="CATEGORY",
                        entity_id=category_id,
                        description=f"Updated category: {updated.name}",
                        metadata={
                            "category_name": updated.name,
                            "parent_id": updated.parent_id,
                            "slug": updated.slug,
                            "updated_fields": updated_fields,
                        },
                    ),
                )
            except Exception:
                # Log but don't fail if logging fails
                pass

        return {
            "id": updated.id,
            "name": updated.name,
            "description": updated.description,
            "parent_id": updated.parent_id,
            "icon": updated.icon,
            "slug": updated.slug,
            "created_at": updated.created_at,
            "updated_at": updated.updated_at,
        }

    async def delete_category(
        self, category_id: int, admin_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Xóa danh mục.

        Args:
            category_id: ID của danh mục
            admin_id: ID của admin thực hiện hành động (tùy chọn)

        Returns:
            Thông báo kết quả

        Raises:
            NotFoundException: Nếu danh mục không tồn tại
            BadRequestException: Nếu danh mục có danh mục con hoặc sách thuộc danh mục
        """
        # Kiểm tra danh mục tồn tại
        category = await self.category_repo.get_by_id(category_id)
        if not category:
            raise NotFoundException(
                detail=f"Không tìm thấy danh mục với ID {category_id}"
            )

        # Kiểm tra danh mục có danh mục con
        has_children = await self.category_repo.has_children(category_id)
        if has_children:
            raise BadRequestException(
                detail="Không thể xóa danh mục có chứa danh mục con"
            )

        # Kiểm tra danh mục có sách
        has_books = await self.book_repo.has_category(category_id)
        if has_books:
            raise BadRequestException(detail="Không thể xóa danh mục có chứa sách")

        # Xóa danh mục
        await self.category_repo.delete(category_id)

        # Log the deletion activity if admin_id is provided
        if admin_id:
            try:
                await create_admin_activity_log(
                    self.db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="DELETE",
                        entity_type="CATEGORY",
                        entity_id=category_id,
                        description=f"Deleted category: {category.name}",
                        metadata={
                            "category_name": category.name,
                            "had_parent": category.parent_id is not None,
                        },
                    ),
                )
            except Exception:
                # Log but don't fail if logging fails
                pass

        return {"message": "Đã xóa danh mục thành công"}
