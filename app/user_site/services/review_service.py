from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from app.user_site.repositories.review_repo import ReviewRepository
from app.user_site.repositories.review_like_repo import ReviewLikeRepository
from app.user_site.repositories.book_repo import BookRepository
from app.user_site.repositories.user_repo import UserRepository
from app.core.exceptions import (
    NotFoundException,
    BadRequestException,
    ForbiddenException,
    ConflictException,
    ValidationException,
)
from app.logs_manager.services import create_user_activity_log
from app.logs_manager.schemas.user_activity_log import UserActivityLogCreate
from app.cache.decorators import cached
from app.logging.setup import get_logger
from app.security.audit.audit_trails import log_data_operation
from app.monitoring.metrics.business_metrics import track_book_activity

logger = get_logger(__name__)


class ReviewService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.review_repo = ReviewRepository(db)
        self.review_like_repo = ReviewLikeRepository(db)
        self.book_repo = BookRepository(db)
        self.user_repo = UserRepository(db)

    async def create_review(
        self,
        user_id: int,
        book_id: int,
        rating: int,
        content: Optional[str] = None,
        title: Optional[str] = None,
        tags: Optional[List[str]] = None,
        contains_spoilers: bool = False,
    ) -> Dict[str, Any]:
        """
        Tạo đánh giá sách mới.

        Args:
            user_id: ID của người dùng
            book_id: ID của sách
            rating: Đánh giá (1-5)
            content: Nội dung đánh giá (tùy chọn)
            title: Tiêu đề đánh giá (tùy chọn)
            tags: Danh sách các tag đánh giá (tùy chọn)
            contains_spoilers: Có chứa chi tiết quan trọng không

        Returns:
            Thông tin đánh giá đã tạo

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng hoặc sách
            BadRequestException: Nếu đánh giá không hợp lệ
        """
        # Kiểm tra người dùng tồn tại
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        # Kiểm tra sách tồn tại
        book = await self.book_repo.get_by_id(book_id)
        if not book:
            raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

        # Kiểm tra rating hợp lệ
        if rating < 1 or rating > 5:
            raise BadRequestException(detail="Đánh giá phải từ 1 đến 5")

        # Kiểm tra xem người dùng đã đánh giá sách này chưa
        existing_review = await self.review_repo.get_by_user_and_book(user_id, book_id)
        if existing_review:
            raise BadRequestException(
                detail="Bạn đã đánh giá cuốn sách này. Hãy cập nhật đánh giá thay vì tạo mới."
            )

        # Tạo đánh giá
        review_data = {
            "user_id": user_id,
            "book_id": book_id,
            "rating": rating,
            "content": content,
            "title": title,
            "tags": tags or [],
            "contains_spoilers": contains_spoilers,
            "likes_count": 0,
            "comments_count": 0,
            "is_approved": True,  # Mặc định được phê duyệt
        }

        review = await self.review_repo.create(review_data)

        # Cập nhật đánh giá trung bình cho sách
        await self.book_repo.update_rating(book_id)

        # Log user activity
        await create_user_activity_log(
            self.db,
            UserActivityLogCreate(
                user_id=user_id,
                activity_type="REVIEW_CREATE",
                entity_type="BOOK",
                entity_id=book_id,
                description=f"User submitted a {rating}-star review for book '{book.title}'",
                metadata={
                    "rating": rating,
                    "review_id": review.id,
                    "has_content": content is not None and len(content) > 0,
                },
            ),
        )

        # Lấy thông tin người dùng
        user_info = {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "avatar": user.avatar,
        }

        return {
            "id": review.id,
            "user_id": review.user_id,
            "book_id": review.book_id,
            "rating": review.rating,
            "content": review.content,
            "title": review.title,
            "tags": review.tags,
            "contains_spoilers": review.contains_spoilers,
            "likes_count": review.likes_count,
            "comments_count": review.comments_count,
            "created_at": review.created_at,
            "updated_at": review.updated_at,
            "is_approved": review.is_approved,
            "user": user_info,
            "book_title": book.title,
            "book_cover": book.cover_image,
        }

    async def get_review(self, review_id: int) -> Dict[str, Any]:
        """
        Lấy thông tin đánh giá sách.

        Args:
            review_id: ID của đánh giá

        Returns:
            Thông tin đánh giá

        Raises:
            NotFoundException: Nếu không tìm thấy đánh giá
        """
        review = await self.review_repo.get_by_id(review_id)
        if not review:
            raise NotFoundException(
                detail=f"Không tìm thấy đánh giá với ID {review_id}"
            )

        # Lấy thông tin người dùng
        user = await self.user_repo.get_by_id(review.user_id)
        user_info = {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "avatar": user.avatar,
        }

        # Lấy thông tin sách
        book = await self.book_repo.get_by_id(review.book_id)

        return {
            "id": review.id,
            "user_id": review.user_id,
            "book_id": review.book_id,
            "rating": review.rating,
            "content": review.content,
            "title": review.title,
            "tags": review.tags,
            "contains_spoilers": review.contains_spoilers,
            "likes_count": review.likes_count,
            "comments_count": review.comments_count,
            "created_at": review.created_at,
            "updated_at": review.updated_at,
            "user": user_info,
            "book_title": book.title,
            "book_cover": book.cover_image,
            "book_author": book.author_name,
        }

    async def update_review(
        self, review_id: int, user_id: int, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Cập nhật đánh giá sách.

        Args:
            review_id: ID của đánh giá
            user_id: ID của người dùng (để kiểm tra quyền)
            data: Dữ liệu cập nhật

        Returns:
            Thông tin đánh giá đã cập nhật

        Raises:
            NotFoundException: Nếu không tìm thấy đánh giá
            ForbiddenException: Nếu người dùng không có quyền cập nhật
            BadRequestException: Nếu dữ liệu không hợp lệ
        """
        # Kiểm tra đánh giá tồn tại
        review = await self.review_repo.get_by_id(review_id)
        if not review:
            raise NotFoundException(
                detail=f"Không tìm thấy đánh giá với ID {review_id}"
            )

        # Kiểm tra quyền cập nhật
        if review.user_id != user_id:
            raise ForbiddenException(detail="Bạn không có quyền cập nhật đánh giá này")

        # Kiểm tra dữ liệu cập nhật
        if "rating" in data and (data["rating"] < 1 or data["rating"] > 5):
            raise BadRequestException(detail="Đánh giá phải từ 1 đến 5")

        # Không cho phép thay đổi user_id và book_id
        forbidden_fields = [
            "user_id",
            "book_id",
            "likes_count",
            "comments_count",
            "is_approved",
        ]
        for field in forbidden_fields:
            if field in data:
                del data[field]

        # Cập nhật đánh giá
        updated = await self.review_repo.update(review_id, data)

        # Cập nhật đánh giá trung bình cho sách nếu rating thay đổi
        if "rating" in data:
            await self.book_repo.update_rating(review.book_id)

        # Log user activity
        await create_user_activity_log(
            self.db,
            UserActivityLogCreate(
                user_id=user_id,
                activity_type="REVIEW_UPDATE",
                entity_type="REVIEW",
                entity_id=review_id,
                description=f"User updated review for book ID {review.book_id}",
                metadata={
                    "book_id": review.book_id,
                    "rating": data.get("rating", review.rating),
                    "updated_fields": list(data.keys()),
                },
            ),
        )

        # Lấy thông tin người dùng
        user = await self.user_repo.get_by_id(updated.user_id)
        user_info = {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "avatar": user.avatar,
        }

        # Lấy thông tin sách
        book = await self.book_repo.get_by_id(updated.book_id)

        return {
            "id": updated.id,
            "user_id": updated.user_id,
            "book_id": updated.book_id,
            "rating": updated.rating,
            "content": updated.content,
            "title": updated.title,
            "tags": updated.tags,
            "contains_spoilers": updated.contains_spoilers,
            "likes_count": updated.likes_count,
            "comments_count": updated.comments_count,
            "created_at": updated.created_at,
            "updated_at": updated.updated_at,
            "is_approved": updated.is_approved,
            "user": user_info,
            "book_title": book.title,
            "book_cover": book.cover_image,
        }

    async def delete_review(self, review_id: int, user_id: int) -> Dict[str, Any]:
        """
        Xóa đánh giá sách.

        Args:
            review_id: ID của đánh giá
            user_id: ID của người dùng (để kiểm tra quyền)

        Returns:
            Thông báo kết quả

        Raises:
            NotFoundException: Nếu không tìm thấy đánh giá
            ForbiddenException: Nếu người dùng không có quyền xóa
        """
        # Kiểm tra đánh giá tồn tại
        review = await self.review_repo.get_by_id(review_id)
        if not review:
            raise NotFoundException(
                detail=f"Không tìm thấy đánh giá với ID {review_id}"
            )

        # Kiểm tra quyền xóa
        if review.user_id != user_id:
            raise ForbiddenException(detail="Bạn không có quyền xóa đánh giá này")

        # Lưu book_id để cập nhật rating sau
        book_id = review.book_id

        # Xóa đánh giá
        await self.review_repo.delete(review_id)

        # Xóa tất cả like liên quan
        await self.review_like_repo.delete_by_review(review_id)

        # Cập nhật đánh giá trung bình cho sách
        await self.book_repo.update_rating(book_id)

        # Log user activity
        await create_user_activity_log(
            self.db,
            UserActivityLogCreate(
                user_id=user_id,
                activity_type="REVIEW_DELETE",
                entity_type="BOOK",
                entity_id=book_id,
                description=f"User deleted review for book ID {book_id}",
                metadata={"review_id": review_id},
            ),
        )

        return {"message": "Đã xóa đánh giá thành công"}

    @cached(ttl=3600, namespace="reviews", key_prefix="book", tags=["reviews", "books"])
    async def list_book_reviews(
        self,
        book_id: int,
        rating: Optional[int] = None,
        sort_by: str = "recent",
        skip: int = 0,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        Lấy danh sách đánh giá của một cuốn sách.

        Args:
            book_id: ID của sách
            rating: Lọc theo rating (tùy chọn)
            sort_by: Sắp xếp theo ('recent', 'highest', 'lowest', 'likes')
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa trả về

        Returns:
            Danh sách đánh giá và thông tin phân trang

        Raises:
            NotFoundException: Nếu không tìm thấy sách
            BadRequestException: Nếu tham số không hợp lệ
        """
        # Kiểm tra sách tồn tại
        book = await self.book_repo.get_by_id(book_id)
        if not book:
            raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

        # Kiểm tra tham số
        if rating is not None and (rating < 1 or rating > 5):
            raise BadRequestException(detail="Rating phải từ 1 đến 5")

        valid_sort_options = ["recent", "highest", "lowest", "likes"]
        if sort_by not in valid_sort_options:
            raise BadRequestException(
                detail=f"Tùy chọn sắp xếp không hợp lệ. Cho phép: {', '.join(valid_sort_options)}"
            )

        # Lấy danh sách đánh giá
        reviews = await self.review_repo.list_by_book(
            book_id=book_id, rating=rating, sort_by=sort_by, skip=skip, limit=limit
        )

        total = await self.review_repo.count_by_book(book_id, rating)

        # Lấy thông tin người dùng
        user_ids = [review.user_id for review in reviews]
        users = {user.id: user for user in await self.user_repo.get_by_ids(user_ids)}

        # Xử lý kết quả
        items = []
        for review in reviews:
            user = users.get(review.user_id)
            user_info = None
            if user:
                user_info = {
                    "id": user.id,
                    "username": user.username,
                    "display_name": user.display_name,
                    "avatar": user.avatar,
                }

            items.append(
                {
                    "id": review.id,
                    "rating": review.rating,
                    "content": review.content,
                    "title": review.title,
                    "tags": review.tags,
                    "contains_spoilers": review.contains_spoilers,
                    "likes_count": review.likes_count,
                    "comments_count": review.comments_count,
                    "created_at": review.created_at,
                    "updated_at": review.updated_at,
                    "user": user_info,
                }
            )

        # Lấy thống kê rating
        rating_stats = await self.review_repo.get_rating_stats(book_id)

        return {
            "items": items,
            "total": total,
            "skip": skip,
            "limit": limit,
            "book_id": book_id,
            "book_title": book.title,
            "book_cover": book.cover_image,
            "book_author": book.author_name,
            "average_rating": book.average_rating,
            "total_reviews": rating_stats["total"],
            "rating_counts": rating_stats["counts"],
        }

    @cached(ttl=3600, namespace="reviews", key_prefix="user", tags=["reviews", "users"])
    async def list_user_reviews(
        self, user_id: int, skip: int = 0, limit: int = 20
    ) -> Dict[str, Any]:
        """
        Lấy danh sách đánh giá của một người dùng.

        Args:
            user_id: ID của người dùng
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa trả về

        Returns:
            Danh sách đánh giá và thông tin phân trang

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng
        """
        # Kiểm tra người dùng tồn tại
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        # Lấy danh sách đánh giá
        reviews = await self.review_repo.list_by_user(
            user_id=user_id, skip=skip, limit=limit
        )

        total = await self.review_repo.count_by_user(user_id)

        # Lấy thông tin sách
        book_ids = [review.book_id for review in reviews]
        books = {book.id: book for book in await self.book_repo.get_by_ids(book_ids)}

        # Xử lý kết quả
        items = []
        for review in reviews:
            book = books.get(review.book_id)
            book_info = None
            if book:
                book_info = {
                    "id": book.id,
                    "title": book.title,
                    "cover_image": book.cover_image,
                    "author_name": book.author_name,
                }

            items.append(
                {
                    "id": review.id,
                    "rating": review.rating,
                    "content": review.content,
                    "title": review.title,
                    "tags": review.tags,
                    "contains_spoilers": review.contains_spoilers,
                    "likes_count": review.likes_count,
                    "comments_count": review.comments_count,
                    "created_at": review.created_at,
                    "updated_at": review.updated_at,
                    "book": book_info,
                }
            )

        # Lấy thông tin người dùng
        user_info = {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "avatar": user.avatar,
        }

        return {
            "items": items,
            "total": total,
            "skip": skip,
            "limit": limit,
            "user": user_info,
        }

    async def like_review(self, review_id: int, user_id: int) -> Dict[str, Any]:
        """
        Thích một đánh giá.

        Args:
            review_id: ID của đánh giá
            user_id: ID của người dùng

        Returns:
            Thông tin kết quả

        Raises:
            NotFoundException: Nếu không tìm thấy đánh giá hoặc người dùng
            BadRequestException: Nếu người dùng đã thích đánh giá này
        """
        # Kiểm tra đánh giá tồn tại
        review = await self.review_repo.get_by_id(review_id)
        if not review:
            raise NotFoundException(
                detail=f"Không tìm thấy đánh giá với ID {review_id}"
            )

        # Kiểm tra người dùng tồn tại
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        # Kiểm tra người dùng đã thích đánh giá này chưa
        existing_like = await self.review_like_repo.get_by_user_and_review(
            user_id, review_id
        )
        if existing_like:
            raise BadRequestException(detail="Bạn đã thích đánh giá này rồi")

        # Tạo like
        like_data = {"user_id": user_id, "review_id": review_id}

        await self.review_like_repo.create(like_data)

        # Cập nhật số lượng like cho đánh giá
        likes_count = await self.review_like_repo.count_by_review(review_id)
        await self.review_repo.update(review_id, {"likes_count": likes_count})

        return {
            "message": "Đã thích đánh giá thành công",
            "review_id": review_id,
            "likes_count": likes_count,
        }

    async def unlike_review(self, review_id: int, user_id: int) -> Dict[str, Any]:
        """
        Bỏ thích một đánh giá.

        Args:
            review_id: ID của đánh giá
            user_id: ID của người dùng

        Returns:
            Thông tin kết quả

        Raises:
            NotFoundException: Nếu không tìm thấy đánh giá, người dùng hoặc like
        """
        # Kiểm tra đánh giá tồn tại
        review = await self.review_repo.get_by_id(review_id)
        if not review:
            raise NotFoundException(
                detail=f"Không tìm thấy đánh giá với ID {review_id}"
            )

        # Kiểm tra người dùng tồn tại
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        # Kiểm tra người dùng đã thích đánh giá này chưa
        existing_like = await self.review_like_repo.get_by_user_and_review(
            user_id, review_id
        )
        if not existing_like:
            raise NotFoundException(detail="Bạn chưa thích đánh giá này")

        # Xóa like
        await self.review_like_repo.delete(existing_like.id)

        # Cập nhật số lượng like cho đánh giá
        likes_count = await self.review_like_repo.count_by_review(review_id)
        await self.review_repo.update(review_id, {"likes_count": likes_count})

        return {
            "message": "Đã bỏ thích đánh giá thành công",
            "review_id": review_id,
            "likes_count": likes_count,
        }

    async def check_user_liked(self, review_id: int, user_id: int) -> Dict[str, Any]:
        """
        Kiểm tra người dùng đã thích đánh giá chưa.

        Args:
            review_id: ID của đánh giá
            user_id: ID của người dùng

        Returns:
            Kết quả kiểm tra

        Raises:
            NotFoundException: Nếu không tìm thấy đánh giá hoặc người dùng
        """
        # Kiểm tra đánh giá tồn tại
        review = await self.review_repo.get_by_id(review_id)
        if not review:
            raise NotFoundException(
                detail=f"Không tìm thấy đánh giá với ID {review_id}"
            )

        # Kiểm tra người dùng tồn tại
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        # Kiểm tra người dùng đã thích đánh giá này chưa
        existing_like = await self.review_like_repo.get_by_user_and_review(
            user_id, review_id
        )

        return {
            "review_id": review_id,
            "user_id": user_id,
            "has_liked": existing_like is not None,
        }

    @cached(
        ttl=7200,
        namespace="reviews",
        key_prefix="rating_stats",
        tags=["reviews", "statistics"],
    )
    async def get_rating_stats(self, book_id: int) -> Dict[str, Any]:
        """
        Lấy thống kê đánh giá của một cuốn sách.

        Args:
            book_id: ID của sách

        Returns:
            Thống kê đánh giá

        Raises:
            NotFoundException: Nếu không tìm thấy sách
        """
        # Kiểm tra sách tồn tại
        book = await self.book_repo.get_by_id(book_id)
        if not book:
            raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

        # Lấy thống kê rating
        stats = await self.review_repo.get_rating_stats(book_id)

        return {
            "book_id": book_id,
            "book_title": book.title,
            "average_rating": book.average_rating,
            "total_reviews": stats["total"],
            "rating_counts": stats["counts"],
        }

    async def get_user_review_for_book(
        self, user_id: int, book_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Lấy đánh giá của người dùng cho một cuốn sách.

        Args:
            user_id: ID của người dùng
            book_id: ID của sách

        Returns:
            Thông tin đánh giá hoặc None nếu chưa đánh giá

        Raises:
            NotFoundException: Nếu không tìm thấy người dùng hoặc sách
        """
        # Kiểm tra người dùng tồn tại
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        # Kiểm tra sách tồn tại
        book = await self.book_repo.get_by_id(book_id)
        if not book:
            raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

        # Lấy đánh giá
        review = await self.review_repo.get_by_user_and_book(user_id, book_id)
        if not review:
            return None

        # Lấy thông tin người dùng
        user_info = {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "avatar": user.avatar,
        }

        return {
            "id": review.id,
            "user_id": review.user_id,
            "book_id": review.book_id,
            "rating": review.rating,
            "content": review.content,
            "title": review.title,
            "tags": review.tags,
            "contains_spoilers": review.contains_spoilers,
            "likes_count": review.likes_count,
            "comments_count": review.comments_count,
            "created_at": review.created_at,
            "updated_at": review.updated_at,
            "user": user_info,
            "book_title": book.title,
        }

    @cached(ttl=1800, namespace="reviews", key_prefix="recent", tags=["reviews"])
    async def get_recent_reviews(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Lấy danh sách đánh giá gần đây.

        Args:
            limit: Số lượng đánh giá tối đa trả về

        Returns:
            Danh sách đánh giá gần đây
        """
        # Lấy danh sách đánh giá gần đây
        reviews = await self.review_repo.get_recent(limit)

        # Lấy thông tin người dùng và sách
        user_ids = [review.user_id for review in reviews]
        book_ids = [review.book_id for review in reviews]

        users = {user.id: user for user in await self.user_repo.get_by_ids(user_ids)}
        books = {book.id: book for book in await self.book_repo.get_by_ids(book_ids)}

        # Xử lý kết quả
        result = []
        for review in reviews:
            user = users.get(review.user_id)
            book = books.get(review.book_id)

            user_info = None
            if user:
                user_info = {
                    "id": user.id,
                    "username": user.username,
                    "display_name": user.display_name,
                    "avatar": user.avatar,
                }

            book_info = None
            if book:
                book_info = {
                    "id": book.id,
                    "title": book.title,
                    "cover_image": book.cover_image,
                    "author_name": book.author_name,
                }

            result.append(
                {
                    "id": review.id,
                    "rating": review.rating,
                    "content": review.content,
                    "title": review.title,
                    "created_at": review.created_at,
                    "likes_count": review.likes_count,
                    "user": user_info,
                    "book": book_info,
                }
            )

        return result

    async def report_review(
        self,
        review_id: int,
        user_id: int,
        reason: str,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Báo cáo một đánh giá không phù hợp

        Args:
            review_id: ID đánh giá
            user_id: ID người dùng báo cáo
            reason: Lý do báo cáo
            description: Mô tả chi tiết (tùy chọn)

        Returns:
            Thông tin kết quả báo cáo

        Raises:
            NotFoundException: Nếu không tìm thấy đánh giá
            ValidationException: Nếu lý do không hợp lệ
            ConflictException: Nếu người dùng đã báo cáo đánh giá này
        """
        # Kiểm tra đánh giá tồn tại
        review = await self.review_repo.get_by_id(review_id)
        if not review:
            raise NotFoundException(f"Không tìm thấy đánh giá có ID {review_id}")

        # Kiểm tra người dùng tồn tại
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng có ID {user_id}")

        # Kiểm tra lý do hợp lệ
        if not reason or len(reason.strip()) < 5:
            raise ValidationException("Lý do báo cáo phải có ít nhất 5 ký tự")

        # Kiểm tra người dùng đã báo cáo đánh giá này chưa
        existing_report = await self.review_repo.get_report(user_id, review_id)
        if existing_report:
            raise ConflictException("Bạn đã báo cáo đánh giá này rồi")

        # Tạo báo cáo
        report_data = {
            "reporter_id": user_id,
            "review_id": review_id,
            "reason": reason,
            "description": description,
        }

        report = await self.review_repo.report_review(report_data)

        # Ghi log và theo dõi chỉ số
        await log_data_operation(
            "create", "review_report", str(report.id), str(user_id), "user", "success"
        )

        return {
            "success": True,
            "message": "Báo cáo đã được gửi thành công",
            "report_id": report.id,
        }

    # --- Helper methods --- #

    async def _invalidate_related_caches(self, book_id: int, user_id: int) -> None:
        """
        Xóa các cache liên quan khi có thay đổi về đánh giá

        Args:
            book_id: ID sách
            user_id: ID người dùng
        """
        # Giả sử đã thiết lập cache_manager từ app/cache/manager.py
        from app.cache.manager import cache_manager

        # Xóa cache đánh giá sách
        await cache_manager.invalidate_by_tags([f"book:{book_id}", "reviews"])

        # Xóa cache liên quan đến user
        await cache_manager.invalidate_by_tags([f"user:{user_id}", "reviews"])

        # Xóa cache thống kê đánh giá
        await cache_manager.invalidate_by_tags([f"book:{book_id}:stats"])
