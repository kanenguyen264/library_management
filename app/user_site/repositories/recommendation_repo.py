from typing import Optional, List, Dict, Any
from sqlalchemy import (
    select,
    update,
    delete,
    func,
    or_,
    and_,
    desc,
    asc,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError

from app.user_site.models.recommendation import Recommendation
from app.user_site.models.user import User
from app.user_site.models.book import Book
from app.core.exceptions import (
    NotFoundException,
    ValidationException,
    ConflictException,
)

# Định nghĩa các loại gợi ý hợp lệ nếu cần
VALID_RECOMMENDATION_TYPES = [
    "system_generated",
    "user_curated",
    "based_on_reading",
    "based_on_likes",
]


class RecommendationRepository:
    """Repository cho các thao tác với Gợi ý Đọc (ReadingRecommendation)."""

    def __init__(self, db: AsyncSession):
        """Khởi tạo repository với AsyncSession."""
        self.db = db

    async def _validate_dependencies(self, user_id: int, book_id: int):
        """(Nội bộ) Kiểm tra sự tồn tại của user và book."""
        user = await self.db.get(User, user_id)
        if not user:
            raise ValidationException(f"Người dùng với ID {user_id} không tồn tại.")
        book = await self.db.get(Book, book_id)
        if not book:
            raise ValidationException(f"Sách với ID {book_id} không tồn tại.")

    async def create(self, recommendation_data: Dict[str, Any]) -> Recommendation:
        """Tạo gợi ý đọc mới.

        Args:
            recommendation_data: Dict chứa dữ liệu (user_id, book_id, recommendation_type, ...).

        Returns:
            Đối tượng ReadingRecommendation đã tạo.

        Raises:
            ValidationException: Nếu thiếu trường, dữ liệu không hợp lệ, dependencies không tồn tại.
            ConflictException: Nếu gợi ý cho user-book này đã tồn tại hoặc có lỗi ràng buộc khác.
        """
        user_id = recommendation_data.get("user_id")
        book_id = recommendation_data.get("book_id")
        rec_type = recommendation_data.get("recommendation_type")
        confidence = recommendation_data.get("confidence_score")

        if not all([user_id, book_id, rec_type]):
            raise ValidationException(
                "Thiếu thông tin bắt buộc: user_id, book_id, recommendation_type."
            )

        await self._validate_dependencies(user_id, book_id)

        if rec_type not in VALID_RECOMMENDATION_TYPES:
            raise ValidationException(
                f"Loại gợi ý không hợp lệ: {rec_type}. Các loại hợp lệ: {VALID_RECOMMENDATION_TYPES}"
            )
        if confidence is not None and not isinstance(confidence, (int, float)):
            raise ValidationException(
                f"Điểm tin cậy không hợp lệ: {confidence}. Phải là số."
            )

        # Kiểm tra xem gợi ý đã tồn tại chưa (tránh trùng lặp)
        existing = await self.get_by_user_book(user_id, book_id)
        if existing:
            # Có thể cập nhật lý do/score nếu logic cho phép, hoặc báo lỗi
            raise ConflictException(
                f"Gợi ý cho người dùng {user_id} và sách {book_id} đã tồn tại (ID: {existing.id})."
            )
            # Hoặc: return await self.update(existing.id, recommendation_data) # Cập nhật nếu tồn tại

        # Lọc dữ liệu
        allowed_fields = {
            col.name
            for col in Recommendation.__table__.columns
            if col.name not in ["id", "created_at"]
        }
        filtered_data = {
            k: v
            for k, v in recommendation_data.items()
            if k in allowed_fields and v is not None
        }
        filtered_data["is_dismissed"] = filtered_data.get(
            "is_dismissed", False
        )  # Mặc định chưa bỏ qua

        recommendation = Recommendation(**filtered_data)
        self.db.add(recommendation)
        try:
            await self.db.commit()
            await self.db.refresh(
                recommendation, attribute_names=["user", "book"]
            )  # Load quan hệ
            return recommendation
        except IntegrityError as e:
            await self.db.rollback()
            raise ConflictException(f"Không thể tạo gợi ý đọc: {e}")

    async def get_by_id(
        self, recommendation_id: int, with_relations: List[str] = None
    ) -> Optional[Recommendation]:
        """Lấy gợi ý đọc theo ID.

        Args:
            recommendation_id: ID gợi ý.
            with_relations: Danh sách quan hệ cần tải (['user', 'book']).

        Returns:
            Đối tượng ReadingRecommendation hoặc None.
        """
        query = select(Recommendation).where(Recommendation.id == recommendation_id)

        if with_relations:
            options = []
            if "user" in with_relations:
                options.append(selectinload(Recommendation.user))
            if "book" in with_relations:
                options.append(selectinload(Recommendation.book))
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_by_user_book(
        self, user_id: int, book_id: int, with_relations: List[str] = None
    ) -> Optional[Recommendation]:
        """Lấy gợi ý đọc theo user_id và book_id.

        Args:
            user_id: ID người dùng.
            book_id: ID sách.
            with_relations: Danh sách quan hệ cần tải.

        Returns:
            Đối tượng ReadingRecommendation hoặc None.
        """
        query = select(Recommendation).where(
            Recommendation.user_id == user_id,
            Recommendation.book_id == book_id,
        )

        if with_relations:
            options = []
            if "user" in with_relations:
                options.append(selectinload(Recommendation.user))
            if "book" in with_relations:
                options.append(selectinload(Recommendation.book))
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().first()

    async def list_by_user(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 20,
        recommendation_type: Optional[str] = None,
        is_dismissed: Optional[bool] = False,  # Mặc định chỉ lấy chưa bị bỏ qua
        sort_by: str = "confidence_score",  # 'confidence_score', 'created_at'
        sort_desc: bool = True,
        with_relations: List[str] = ["book"],  # Mặc định tải book
    ) -> List[Recommendation]:
        """Liệt kê gợi ý đọc của người dùng với bộ lọc và sắp xếp.

        Args:
            user_id: ID người dùng.
            skip, limit: Phân trang.
            recommendation_type: Lọc theo loại gợi ý.
            is_dismissed: Lọc theo trạng thái bỏ qua (True, False, None để lấy tất cả).
            sort_by: Trường sắp xếp.
            sort_desc: Sắp xếp giảm dần.
            with_relations: Danh sách quan hệ cần tải.

        Returns:
            Danh sách ReadingRecommendation.
        """
        query = select(Recommendation).where(Recommendation.user_id == user_id)

        if recommendation_type:
            if recommendation_type not in VALID_RECOMMENDATION_TYPES:
                raise ValidationException(
                    f"Loại gợi ý không hợp lệ: {recommendation_type}"
                )
            query = query.where(
                Recommendation.recommendation_type == recommendation_type
            )

        if is_dismissed is not None:
            query = query.where(Recommendation.is_dismissed == is_dismissed)

        # Sắp xếp
        sort_column = Recommendation.confidence_score  # Mặc định
        if sort_by == "created_at":
            sort_column = Recommendation.created_at
        # Coalesce score để xử lý None nếu cần
        order = (
            desc(func.coalesce(sort_column, -1.0))
            if sort_desc
            else asc(func.coalesce(sort_column, -1.0))
        )
        query = query.order_by(order)

        # Phân trang
        query = query.offset(skip).limit(limit)

        # Load relations
        if with_relations:
            options = []
            if "user" in with_relations:
                options.append(selectinload(Recommendation.user))
            if "book" in with_relations:
                options.append(selectinload(Recommendation.book))
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def count_by_user(
        self,
        user_id: int,
        recommendation_type: Optional[str] = None,
        is_dismissed: Optional[bool] = False,  # Mặc định đếm chưa bị bỏ qua
    ) -> int:
        """Đếm số lượng gợi ý đọc của người dùng với bộ lọc."""
        query = (
            select(func.count(Recommendation.id))
            .select_from(Recommendation)
            .where(Recommendation.user_id == user_id)
        )

        if recommendation_type:
            if recommendation_type not in VALID_RECOMMENDATION_TYPES:
                raise ValidationException(
                    f"Loại gợi ý không hợp lệ: {recommendation_type}"
                )
            query = query.where(
                Recommendation.recommendation_type == recommendation_type
            )
        if is_dismissed is not None:
            query = query.where(Recommendation.is_dismissed == is_dismissed)

        result = await self.db.execute(query)
        return result.scalar_one() or 0

    async def update(
        self, recommendation_id: int, data: Dict[str, Any]
    ) -> Optional[Recommendation]:
        """Cập nhật thông tin gợi ý đọc (vd: score, reason, is_dismissed).

        Args:
            recommendation_id: ID gợi ý.
            data: Dict chứa dữ liệu cập nhật.

        Returns:
            Đối tượng ReadingRecommendation đã cập nhật hoặc None nếu không tìm thấy.
        """
        recommendation = await self.get_by_id(recommendation_id)
        if not recommendation:
            return None  # Hoặc raise NotFoundException

        allowed_fields = {"reason", "confidence_score", "is_dismissed"}
        updated = False

        for key, value in data.items():
            if key in allowed_fields and value is not None:
                # Validate score
                if key == "confidence_score" and not isinstance(value, (int, float)):
                    raise ValidationException(
                        f"Điểm tin cậy không hợp lệ: {value}. Phải là số."
                    )

                if getattr(recommendation, key) != value:
                    setattr(recommendation, key, value)
                    updated = True

        if updated:
            try:
                await self.db.commit()
                await self.db.refresh(recommendation, attribute_names=["user", "book"])
            except IntegrityError as e:
                await self.db.rollback()
                raise ConflictException(f"Không thể cập nhật gợi ý đọc: {e}")

        return recommendation

    async def dismiss(self, recommendation_id: int) -> Optional[Recommendation]:
        """Đánh dấu gợi ý đọc là đã bị bỏ qua.

        Args:
            recommendation_id: ID gợi ý.

        Returns:
            Đối tượng ReadingRecommendation đã cập nhật hoặc None.
        """
        return await self.update(recommendation_id, {"is_dismissed": True})

    async def delete(self, recommendation_id: int) -> bool:
        """Xóa gợi ý đọc.

        Args:
            recommendation_id: ID gợi ý cần xóa.

        Returns:
            True nếu xóa thành công, False nếu không tìm thấy.
        """
        query = delete(Recommendation).where(Recommendation.id == recommendation_id)
        result = await self.db.execute(query)
        await self.db.commit()
        return result.rowcount > 0

    async def delete_by_user(self, user_id: int) -> int:
        """Xóa tất cả gợi ý đọc của một người dùng.

        Args:
            user_id: ID người dùng.

        Returns:
            Số lượng gợi ý đã xóa.
        """
        query = delete(Recommendation).where(Recommendation.user_id == user_id)
        result = await self.db.execute(query)
        await self.db.commit()
        return result.rowcount

    async def bulk_create(
        self, recommendations_data: List[Dict[str, Any]]
    ) -> List[Recommendation]:
        """Tạo nhiều gợi ý cùng lúc.
           Lưu ý: Nên có cơ chế xử lý lỗi/trùng lặp tinh vi hơn nếu cần.
                  Phiên bản này sẽ bỏ qua các lỗi IntegrityError và trả về những cái tạo thành công.

        Args:
            recommendations_data: Danh sách các dict chứa dữ liệu gợi ý.

        Returns:
            Danh sách các đối tượng ReadingRecommendation đã được tạo thành công.
        """
        if not recommendations_data:
            return []

        recommendation_objects = []
        created_objects = []
        ids_to_refresh = []

        # Validate và tạo objects trước
        for data in recommendations_data:
            user_id = data.get("user_id")
            book_id = data.get("book_id")
            rec_type = data.get("recommendation_type")
            if not all([user_id, book_id, rec_type]):
                # Log warning or skip invalid data
                print(f"Skipping invalid recommendation data: {data}")
                continue
            # Có thể thêm validation khác ở đây

            allowed_fields = {
                col.name
                for col in Recommendation.__table__.columns
                if col.name not in ["id", "created_at"]
            }
            filtered_data = {
                k: v for k, v in data.items() if k in allowed_fields and v is not None
            }
            filtered_data["is_dismissed"] = filtered_data.get("is_dismissed", False)

            recommendation_objects.append(Recommendation(**filtered_data))

        if not recommendation_objects:
            return []

        # Thêm tất cả vào session
        self.db.add_all(recommendation_objects)

        try:
            # Flush để lấy lỗi IntegrityError sớm
            await self.db.flush()
            # Nếu flush thành công, tất cả đều hợp lệ (hoặc DB không có constraint)
            await self.db.commit()
            created_objects = recommendation_objects  # Tất cả đều được tạo

        except IntegrityError as e:
            await self.db.rollback()  # Rollback toàn bộ batch nếu có lỗi
            print(
                f"IntegrityError during bulk create recommendations: {e}. Rolling back batch."
            )
            # TODO: Có thể thử lại từng cái một hoặc có logic xử lý lỗi tinh vi hơn
            # Ví dụ: Lấy những cái đã tồn tại và cập nhật nếu cần.
            # Phiên bản đơn giản: rollback và trả về list rỗng hoặc raise lỗi
            # return []
            raise ConflictException(
                f"Lỗi khi tạo hàng loạt gợi ý, có thể do trùng lặp: {e}"
            )

        # Refresh các đối tượng đã tạo thành công để có ID và quan hệ
        refreshed_objects = []
        for obj in created_objects:
            try:
                # Chỉ refresh nếu đối tượng thực sự được persist (có ID)
                if getattr(obj, "id", None):
                    await self.db.refresh(obj, attribute_names=["user", "book"])
                    refreshed_objects.append(obj)
            except Exception as refresh_err:
                print(
                    f"Error refreshing recommendation {getattr(obj, 'id', 'N/A')}: {refresh_err}"
                )

        return refreshed_objects

    async def get_top_recommendations(
        self,
        user_id: int,
        limit: int = 10,
        recommendation_type: Optional[str] = None,
        with_relations: List[str] = ["book"],
    ) -> List[Recommendation]:
        """Lấy danh sách gợi ý hàng đầu chưa bị bỏ qua, sắp xếp theo điểm tin cậy.

        Args:
            user_id: ID người dùng.
            limit: Số lượng tối đa.
            recommendation_type: Lọc theo loại gợi ý (tùy chọn).
            with_relations: Danh sách quan hệ cần tải.

        Returns:
            Danh sách ReadingRecommendation.
        """
        query = select(Recommendation).where(
            Recommendation.user_id == user_id,
            Recommendation.is_dismissed == False,
        )

        if recommendation_type:
            if recommendation_type not in VALID_RECOMMENDATION_TYPES:
                raise ValidationException(
                    f"Loại gợi ý không hợp lệ: {recommendation_type}"
                )
            query = query.where(
                Recommendation.recommendation_type == recommendation_type
            )

        # Sắp xếp theo score giảm dần, score None coi như thấp nhất
        query = query.order_by(
            desc(func.coalesce(Recommendation.confidence_score, -1.0))
        )
        query = query.limit(limit)

        # Load relations
        if with_relations:
            options = []
            if "user" in with_relations:
                options.append(selectinload(Recommendation.user))
            if "book" in with_relations:
                options.append(selectinload(Recommendation.book))
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().all()
