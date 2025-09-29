from typing import Optional, List, Dict, Any, Union, Tuple
from datetime import datetime, timezone
from sqlalchemy import select, update, delete, desc, func, or_, and_, asc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError

from app.user_site.models.review import Review, ReviewLike, ReviewReport
from app.user_site.models.user import User
from app.user_site.models.book import Book
from app.core.exceptions import (
    NotFoundException,
    ConflictException,
    ValidationException,
)

# Định nghĩa các trạng thái báo cáo hợp lệ
VALID_REPORT_STATUSES = ["pending", "approved", "rejected", "resolved"]


class ReviewRepository:
    """Repository cho các thao tác với Đánh giá (Review), bao gồm quản lý Báo cáo (ReviewReport)."""

    def __init__(self, db: AsyncSession):
        """Khởi tạo repository với AsyncSession."""
        self.db = db

    # --- Review Methods --- #

    async def _validate_dependencies(self, user_id: int, book_id: int):
        """(Nội bộ) Kiểm tra sự tồn tại của user và book."""
        user = await self.db.get(User, user_id)
        if not user:
            raise ValidationException(f"Người dùng với ID {user_id} không tồn tại.")
        book = await self.db.get(Book, book_id)
        if not book:
            raise ValidationException(f"Sách với ID {book_id} không tồn tại.")

    async def create(self, review_data: Dict[str, Any]) -> Review:
        """Tạo đánh giá mới.

        Args:
            review_data: Dict chứa dữ liệu (user_id, book_id, rating, content, title?, is_approved?).

        Returns:
            Đối tượng Review đã tạo.

        Raises:
            ValidationException: Nếu thiếu trường, rating không hợp lệ, dependencies không tồn tại.
            ConflictException: Nếu người dùng đã đánh giá sách này hoặc lỗi ràng buộc khác.
        """
        user_id = review_data.get("user_id")
        book_id = review_data.get("book_id")
        rating = review_data.get("rating")
        content = review_data.get("content")

        if not all([user_id, book_id, rating, content]):
            raise ValidationException(
                "Thiếu thông tin bắt buộc: user_id, book_id, rating, content."
            )

        await self._validate_dependencies(user_id, book_id)

        if not isinstance(rating, int) or not (1 <= rating <= 5):
            raise ValidationException(
                f"Điểm đánh giá không hợp lệ: {rating}. Phải từ 1 đến 5."
            )

        # Kiểm tra người dùng đã đánh giá sách này chưa
        existing_review = await self.get_by_user_and_book(user_id, book_id)
        if existing_review:
            raise ConflictException(
                f"Người dùng {user_id} đã đánh giá sách {book_id} rồi (ID: {existing_review.id})."
            )

        # Lọc dữ liệu
        allowed_fields = {
            col.name
            for col in Review.__table__.columns
            if col.name not in ["id", "created_at", "updated_at", "likes_count"]
        }
        filtered_data = {
            k: v
            for k, v in review_data.items()
            if k in allowed_fields and v is not None
        }
        # Mặc định is_approved là False hoặc True tùy vào cài đặt hệ thống
        filtered_data["is_approved"] = filtered_data.get("is_approved", False)

        review = Review(**filtered_data)
        self.db.add(review)
        try:
            await self.db.commit()
            await self.db.refresh(
                review, attribute_names=["user", "book"]
            )  # Load quan hệ
            return review
        except IntegrityError as e:
            await self.db.rollback()
            raise ConflictException(f"Không thể tạo đánh giá: {e}")

    async def get_by_id(
        self, review_id: int, with_relations: List[str] = None
    ) -> Optional[Review]:
        """Lấy đánh giá theo ID.

        Args:
            review_id: ID đánh giá.
            with_relations: Danh sách quan hệ cần tải (['user', 'book', 'likes', 'reports']).

        Returns:
            Đối tượng Review hoặc None.
        """
        query = select(Review).where(Review.id == review_id)

        if with_relations:
            options = []
            if "user" in with_relations:
                options.append(selectinload(Review.user))
            if "book" in with_relations:
                options.append(selectinload(Review.book))
            # Load likes kèm user nếu cần
            if "likes" in with_relations:
                like_load = selectinload(Review.likes)
                if "likes.user" in with_relations:  # Ví dụ load lồng
                    like_load = like_load.selectinload(ReviewLike.user)
                options.append(like_load)
            # Load reports kèm reporter nếu cần
            if "reports" in with_relations:
                report_load = selectinload(Review.reports)
                if "reports.reporter" in with_relations:
                    report_load = report_load.selectinload(ReviewReport.reporter)
                options.append(report_load)
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_by_user_and_book(
        self, user_id: int, book_id: int, with_relations: List[str] = None
    ) -> Optional[Review]:
        """Lấy đánh giá của người dùng cho một sách cụ thể."""
        query = select(Review).where(
            Review.user_id == user_id, Review.book_id == book_id
        )
        if with_relations:
            options = []
            if "user" in with_relations:
                options.append(selectinload(Review.user))
            if "book" in with_relations:
                options.append(selectinload(Review.book))
            if "likes" in with_relations:
                options.append(selectinload(Review.likes))
            if "reports" in with_relations:
                options.append(selectinload(Review.reports))
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().first()

    async def update(
        self, review_id: int, review_data: Dict[str, Any]
    ) -> Optional[Review]:
        """Cập nhật đánh giá (rating, title, content).

        Args:
            review_id: ID đánh giá.
            review_data: Dict chứa dữ liệu cập nhật.

        Returns:
            Đối tượng Review đã cập nhật hoặc None nếu không tìm thấy.
        """
        review = await self.get_by_id(review_id)
        if not review:
            return None  # Hoặc raise NotFoundException

        allowed_fields = {
            "rating",
            "title",
            "content",
            "is_approved",
        }  # is_approved có thể cập nhật qua approve/reject
        updated = False

        for key, value in review_data.items():
            if key in allowed_fields and value is not None:
                if key == "rating":
                    if not isinstance(value, int) or not (1 <= value <= 5):
                        raise ValidationException(
                            f"Điểm đánh giá không hợp lệ: {value}. Phải từ 1 đến 5."
                        )
                if getattr(review, key) != value:
                    setattr(review, key, value)
                    updated = True

        if updated:
            review.updated_at = datetime.now(timezone.utc)  # Cập nhật thời gian sửa đổi
            try:
                await self.db.commit()
                await self.db.refresh(review, attribute_names=["user", "book"])
            except IntegrityError as e:
                await self.db.rollback()
                raise ConflictException(f"Không thể cập nhật đánh giá: {e}")

        return review

    async def delete(self, review_id: int) -> bool:
        """Xóa đánh giá.
           Cần đảm bảo các ReviewLike và ReviewReport liên quan được xử lý (cascade delete hoặc xóa thủ công).

        Args:
            review_id: ID đánh giá cần xóa.

        Returns:
            True nếu xóa thành công, False nếu không tìm thấy.
        """
        # Tùy chọn: Xóa likes và reports trước nếu không có cascade
        # await self.db.execute(delete(ReviewLike).where(ReviewLike.review_id == review_id))
        # await self.db.execute(delete(ReviewReport).where(ReviewReport.review_id == review_id))

        query = delete(Review).where(Review.id == review_id)
        result = await self.db.execute(query)
        await self.db.commit()
        return result.rowcount > 0

    async def list_reviews(
        self,
        book_id: Optional[int] = None,
        user_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 20,
        sort_by: str = "created_at",  # 'created_at', 'rating', 'likes_count'
        sort_desc: bool = True,
        is_approved: Optional[bool] = True,  # Mặc định chỉ lấy đã duyệt
        with_relations: List[str] = ["user"],  # Mặc định tải user
    ) -> List[Review]:
        """Liệt kê đánh giá với bộ lọc và sắp xếp.

        Args:
            book_id: Lọc theo sách.
            user_id: Lọc theo người dùng.
            skip, limit: Phân trang.
            sort_by: Trường sắp xếp.
            sort_desc: Sắp xếp giảm dần.
            is_approved: Lọc theo trạng thái phê duyệt (True, False, None để lấy tất cả).
            with_relations: Danh sách quan hệ cần tải (['user', 'book']).

        Returns:
            Danh sách Review.
        """
        query = select(Review)
        if book_id is not None:
            query = query.where(Review.book_id == book_id)
        if user_id is not None:
            query = query.where(Review.user_id == user_id)
        if is_approved is not None:
            query = query.where(Review.is_approved == is_approved)

        # Sắp xếp
        sort_column = Review.created_at
        if sort_by == "rating":
            sort_column = Review.rating
        elif sort_by == "likes_count":
            # Cần coalesce nếu likes_count có thể là None
            sort_column = func.coalesce(Review.likes_count, 0)

        order = desc(sort_column) if sort_desc else asc(sort_column)
        query = query.order_by(order)

        # Phân trang
        query = query.offset(skip).limit(limit)

        # Load relations
        if with_relations:
            options = []
            if "user" in with_relations:
                options.append(selectinload(Review.user))
            if "book" in with_relations:
                options.append(selectinload(Review.book))
            # Không nên load likes/reports ở list
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def count_reviews(
        self,
        book_id: Optional[int] = None,
        user_id: Optional[int] = None,
        is_approved: Optional[bool] = True,  # Mặc định đếm đã duyệt
    ) -> int:
        """Đếm số lượng đánh giá với bộ lọc."""
        query = select(func.count(Review.id)).select_from(Review)
        if book_id is not None:
            query = query.where(Review.book_id == book_id)
        if user_id is not None:
            query = query.where(Review.user_id == user_id)
        if is_approved is not None:
            query = query.where(Review.is_approved == is_approved)

        result = await self.db.execute(query)
        return result.scalar_one() or 0

    async def calculate_avg_rating(
        self, book_id: int, only_approved: bool = True
    ) -> Optional[float]:
        """Tính điểm đánh giá trung bình của một sách.
        Trả về None nếu không có đánh giá nào.
        """
        query = (
            select(func.avg(Review.rating))
            .select_from(Review)
            .where(Review.book_id == book_id)
        )
        if only_approved:
            query = query.where(Review.is_approved == True)

        result = await self.db.execute(query)
        avg_rating = result.scalar_one_or_none()
        return round(avg_rating, 1) if avg_rating is not None else None

    async def get_rating_distribution(
        self, book_id: int, only_approved: bool = True
    ) -> Dict[int, int]:
        """Lấy phân phối số lượng đánh giá theo từng mức điểm (1-5)."""
        query = (
            select(Review.rating, func.count(Review.id).label("count"))
            .select_from(Review)
            .where(Review.book_id == book_id)
        )

        if only_approved:
            query = query.where(Review.is_approved == True)

        query = query.group_by(Review.rating).order_by(Review.rating)

        result = await self.db.execute(query)
        distribution = {rating: 0 for rating in range(1, 6)}  # Khởi tạo
        for row in result:
            if row.rating in distribution:
                distribution[row.rating] = row.count
        return distribution

    async def approve_review(self, review_id: int) -> Optional[Review]:
        """Phê duyệt một đánh giá."""
        return await self.update(review_id, {"is_approved": True})

    async def reject_review(self, review_id: int) -> Optional[Review]:
        """Từ chối một đánh giá."""
        return await self.update(review_id, {"is_approved": False})

    # --- ReviewReport Methods --- #

    async def report_review(self, report_data: Dict[str, Any]) -> ReviewReport:
        """Báo cáo một đánh giá.
           Nếu người dùng đã báo cáo đánh giá này rồi, sẽ cập nhật lý do.

        Args:
            report_data: Dict chứa dữ liệu (reporter_id, review_id, reason).

        Returns:
            Đối tượng ReviewReport đã tạo hoặc cập nhật.

        Raises:
            ValidationException: Nếu thiếu trường, dữ liệu không hợp lệ, dependencies không tồn tại.
            ConflictException: Nếu có lỗi ràng buộc khác.
        """
        reporter_id = report_data.get("reporter_id")
        review_id = report_data.get("review_id")
        reason = report_data.get("reason")

        if not all([reporter_id, review_id, reason]):
            raise ValidationException(
                "Thiếu thông tin báo cáo: reporter_id, review_id, reason."
            )

        # Kiểm tra reporter và review tồn tại
        reporter = await self.db.get(User, reporter_id)
        if not reporter:
            raise ValidationException(f"Người báo cáo ID {reporter_id} không tồn tại.")
        review = await self.get_by_id(
            review_id
        )  # Dùng get_by_id của repo này để kiểm tra review
        if not review:
            raise ValidationException(f"Đánh giá ID {review_id} không tồn tại.")

        # Kiểm tra đã báo cáo chưa
        existing_report = await self.get_report(reporter_id, review_id)
        if existing_report:
            # Nếu đã tồn tại, cập nhật lý do và reset trạng thái nếu cần thiết?
            # Hoặc chỉ trả về báo cáo hiện có tùy logic
            if existing_report.reason != reason:
                existing_report.reason = reason
                # Có nên reset status về pending khi cập nhật lý do?
                # existing_report.status = "pending"
                # existing_report.resolved_at = None
                # existing_report.resolved_by = None
                try:
                    await self.db.commit()
                    await self.db.refresh(existing_report)
                except IntegrityError as e:
                    await self.db.rollback()
                    raise ConflictException(f"Không thể cập nhật báo cáo: {e}")
            return existing_report

        # Tạo báo cáo mới
        allowed_fields = {
            col.name
            for col in ReviewReport.__table__.columns
            if col.name not in ["id", "created_at", "resolved_at", "resolved_by"]
        }
        filtered_data = {
            k: v
            for k, v in report_data.items()
            if k in allowed_fields and v is not None
        }
        filtered_data["status"] = filtered_data.get(
            "status", "pending"
        )  # Mặc định là pending

        report = ReviewReport(**filtered_data)
        self.db.add(report)
        try:
            await self.db.commit()
            await self.db.refresh(report, attribute_names=["reporter", "review"])
            return report
        except IntegrityError as e:
            await self.db.rollback()
            raise ConflictException(f"Không thể tạo báo cáo: {e}")

    async def get_report(
        self, reporter_id: int, review_id: int, with_relations: List[str] = None
    ) -> Optional[ReviewReport]:
        """Lấy báo cáo cụ thể của một người dùng cho một đánh giá."""
        query = select(ReviewReport).where(
            ReviewReport.reporter_id == reporter_id, ReviewReport.review_id == review_id
        )
        if with_relations:
            options = []
            if "reporter" in with_relations:
                options.append(selectinload(ReviewReport.reporter))
            if "review" in with_relations:
                options.append(selectinload(ReviewReport.review))
            if "resolver" in with_relations:
                options.append(selectinload(ReviewReport.resolver))
            if options:
                query = query.options(*options)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_report_by_id(
        self, report_id: int, with_relations: List[str] = None
    ) -> Optional[ReviewReport]:
        """Lấy báo cáo theo ID."""
        query = select(ReviewReport).where(ReviewReport.id == report_id)
        if with_relations:
            options = []
            if "reporter" in with_relations:
                options.append(selectinload(ReviewReport.reporter))
            if "review" in with_relations:
                review_load = selectinload(ReviewReport.review)
                if "review.user" in with_relations:
                    review_load = review_load.selectinload(Review.user)
                if "review.book" in with_relations:
                    review_load = review_load.selectinload(Review.book)
                options.append(review_load)
            if "resolver" in with_relations:
                options.append(selectinload(ReviewReport.resolver))
            if options:
                query = query.options(*options)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def list_reports(
        self,
        skip: int = 0,
        limit: int = 20,
        status: Optional[str] = None,
        review_id: Optional[int] = None,
        reporter_id: Optional[int] = None,
        sort_by: str = "created_at",
        sort_desc: bool = True,
        with_relations: List[str] = [
            "reporter",
            "review",
        ],  # Thường cần reporter và review
    ) -> List[ReviewReport]:
        """Liệt kê báo cáo đánh giá (thường cho admin).

        Args:
            skip, limit: Phân trang.
            status: Lọc theo trạng thái.
            review_id: Lọc theo đánh giá bị báo cáo.
            reporter_id: Lọc theo người báo cáo.
            sort_by: Trường sắp xếp ('created_at', 'resolved_at').
            sort_desc: Sắp xếp giảm dần.
            with_relations: Danh sách quan hệ cần tải (['reporter', 'review', 'resolver', 'review.user']).

        Returns:
            Danh sách ReviewReport.
        """
        query = select(ReviewReport)
        if status:
            if status not in VALID_REPORT_STATUSES:
                raise ValidationException(f"Trạng thái báo cáo không hợp lệ: {status}")
            query = query.where(ReviewReport.status == status)
        if review_id is not None:
            query = query.where(ReviewReport.review_id == review_id)
        if reporter_id is not None:
            query = query.where(ReviewReport.reporter_id == reporter_id)

        # Sắp xếp
        sort_column = ReviewReport.created_at
        if sort_by == "resolved_at":
            sort_column = ReviewReport.resolved_at  # Có thể là None

        # Xử lý None khi sắp xếp
        if sort_desc:
            order = (
                desc(sort_column.nullslast())
                if sort_column is not None
                else desc(ReviewReport.created_at)
            )
        else:
            order = (
                asc(sort_column.nullsfirst())
                if sort_column is not None
                else asc(ReviewReport.created_at)
            )
        query = query.order_by(order)

        # Phân trang
        query = query.offset(skip).limit(limit)

        # Load relations
        if with_relations:
            options = []
            if "reporter" in with_relations:
                options.append(selectinload(ReviewReport.reporter))
            if "review" in with_relations:
                review_load = selectinload(ReviewReport.review)
                if "review.user" in with_relations:
                    review_load = review_load.selectinload(Review.user)
                if "review.book" in with_relations:
                    review_load = review_load.selectinload(Review.book)
                options.append(review_load)
            if "resolver" in with_relations:
                options.append(selectinload(ReviewReport.resolver))
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def count_reports(
        self,
        status: Optional[str] = None,
        review_id: Optional[int] = None,
        reporter_id: Optional[int] = None,
    ) -> int:
        """Đếm số lượng báo cáo với bộ lọc."""
        query = select(func.count(ReviewReport.id)).select_from(ReviewReport)
        if status:
            if status not in VALID_REPORT_STATUSES:
                raise ValidationException(f"Trạng thái báo cáo không hợp lệ: {status}")
            query = query.where(ReviewReport.status == status)
        if review_id is not None:
            query = query.where(ReviewReport.review_id == review_id)
        if reporter_id is not None:
            query = query.where(ReviewReport.reporter_id == reporter_id)

        result = await self.db.execute(query)
        return result.scalar_one() or 0

    async def update_report_status(
        self, report_id: int, status: str, resolved_by_id: Optional[int] = None
    ) -> Optional[ReviewReport]:
        """Cập nhật trạng thái báo cáo (chỉ admin).

        Args:
            report_id: ID báo cáo.
            status: Trạng thái mới.
            resolved_by_id: ID của admin xử lý (nếu status là resolved).

        Returns:
            Đối tượng ReviewReport đã cập nhật hoặc None nếu không tìm thấy.
        """
        if status not in VALID_REPORT_STATUSES:
            raise ValidationException(f"Trạng thái báo cáo không hợp lệ: {status}")

        report = await self.get_report_by_id(report_id)
        if not report:
            return None  # Hoặc raise NotFoundException

        updated = False
        if report.status != status:
            report.status = status
            updated = True

        # Nếu chuyển sang trạng thái đã xử lý, cập nhật resolver và thời gian
        if status in ["approved", "rejected", "resolved"]:
            if report.resolved_at is None:
                report.resolved_at = datetime.now(timezone.utc)
                updated = True
            if resolved_by_id and report.resolved_by_id != resolved_by_id:
                # Kiểm tra admin có tồn tại không?
                resolver = await self.db.get(User, resolved_by_id)
                if not resolver:
                    raise ValidationException(
                        f"Người xử lý ID {resolved_by_id} không tồn tại."
                    )
                report.resolved_by_id = resolved_by_id
                updated = True
        # Nếu chuyển về pending, xóa thông tin xử lý?
        elif status == "pending":
            if report.resolved_at is not None:
                report.resolved_at = None
                report.resolved_by_id = None
                updated = True

        if updated:
            try:
                await self.db.commit()
                await self.db.refresh(
                    report, attribute_names=["reporter", "review", "resolver"]
                )
            except IntegrityError as e:
                await self.db.rollback()
                raise ConflictException(f"Không thể cập nhật trạng thái báo cáo: {e}")

        return report
