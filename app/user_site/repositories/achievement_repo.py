from typing import Optional, List, Dict, Any
from sqlalchemy import select, update, delete, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.user_site.models.achievement import UserAchievement
from app.core.exceptions import NotFoundException


class AchievementRepository:
    """Repository cho các thao tác liên quan đến thành tựu người dùng (UserAchievement)."""

    def __init__(self, db: AsyncSession):
        """Khởi tạo repository với AsyncSession."""
        self.db = db

    async def create(self, achievement_data: Dict[str, Any]) -> UserAchievement:
        """Tạo một bản ghi thành tựu mới cho người dùng.

        Args:
            achievement_data: Dữ liệu thành tựu (ví dụ: user_id, achievement_id, earned_at).

        Returns:
            Đối tượng UserAchievement đã được tạo.
        """
        # Lọc các trường hợp lệ cho UserAchievement
        allowed_fields = {"user_id", "achievement_id", "earned_at"}
        filtered_data = {
            k: v for k, v in achievement_data.items() if k in allowed_fields
        }
        achievement = UserAchievement(**filtered_data)
        self.db.add(achievement)
        await self.db.commit()
        await self.db.refresh(achievement)
        return achievement

    async def get_by_id(
        self, achievement_id: int, with_relations: Optional[List[str]] = None
    ) -> Optional[UserAchievement]:
        """Lấy thành tựu theo ID.

        Args:
            achievement_id: ID của bản ghi thành tựu.
            with_relations: Danh sách các mối quan hệ cần load (ví dụ: ["user"]).

        Returns:
            Đối tượng UserAchievement hoặc None nếu không tìm thấy.
        """
        query = select(UserAchievement).where(UserAchievement.id == achievement_id)

        if with_relations:
            options = []
            if "user" in with_relations:
                # Sử dụng selectinload thay vì joinedload nếu có thể load riêng lẻ
                options.append(selectinload(UserAchievement.user))
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_by_user_and_achievement(
        self, user_id: int, achievement_id: int
    ) -> Optional[UserAchievement]:
        """Lấy thành tựu cụ thể (dựa trên achievement_id gốc) của một người dùng.

        Args:
            user_id: ID của người dùng.
            achievement_id: ID của loại thành tựu (ví dụ: ID từ bảng Achievement gốc).

        Returns:
            Đối tượng UserAchievement hoặc None nếu người dùng chưa đạt được thành tựu đó.
        """
        # Giả định achievement_id trong UserAchievement là ID của loại thành tựu
        query = select(UserAchievement).where(
            UserAchievement.user_id == user_id,
            UserAchievement.achievement_id
            == achievement_id,  # Cần khớp với tên cột trong model
        )
        result = await self.db.execute(query)
        return result.scalars().first()

    async def list_by_user(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 20,
        with_relations: Optional[List[str]] = None,  # Thêm tùy chọn load relations
    ) -> List[UserAchievement]:
        """Lấy danh sách thành tựu theo user_id, sắp xếp theo ngày đạt được gần nhất.

        Args:
            user_id: ID của người dùng.
            skip: Số lượng bản ghi bỏ qua (phân trang).
            limit: Số lượng bản ghi tối đa trả về (phân trang).
            with_relations: Danh sách các mối quan hệ cần load.

        Returns:
            Danh sách các đối tượng UserAchievement.
        """
        query = select(UserAchievement).where(UserAchievement.user_id == user_id)

        if with_relations:
            options = []
            # Ví dụ: load achievement definition nếu có relation
            # if "achievement_definition" in with_relations:
            #     options.append(selectinload(UserAchievement.achievement_definition))
            if options:
                query = query.options(*options)

        query = query.order_by(
            desc(UserAchievement.earned_at)
        )  # Sắp xếp theo earned_at
        query = query.offset(skip).limit(limit)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def count_by_user(self, user_id: int) -> int:
        """Đếm số lượng thành tựu mà người dùng đã đạt được.

        Args:
            user_id: ID của người dùng.

        Returns:
            Tổng số thành tựu đã đạt được.
        """
        query = select(func.count(UserAchievement.id)).where(
            UserAchievement.user_id == user_id
        )
        result = await self.db.execute(query)
        return result.scalar_one() or 0  # Trả về 0 nếu chưa có thành tựu nào

    async def delete(self, achievement_id: int) -> bool:
        """Xóa một bản ghi thành tựu theo ID của nó.

        Args:
            achievement_id: ID của bản ghi UserAchievement cần xóa.

        Returns:
            True nếu xóa thành công.

        Raises:
            NotFoundException: Nếu không tìm thấy bản ghi thành tựu với ID cung cấp.
        """
        achievement = await self.get_by_id(achievement_id)
        if not achievement:
            raise NotFoundException(
                detail=f"Không tìm thấy thành tựu với ID {achievement_id}"
            )

        await self.db.delete(achievement)
        await self.db.commit()
        return True

    async def delete_by_user_and_achievement(
        self, user_id: int, achievement_id: int
    ) -> bool:
        """Xóa một thành tựu cụ thể của người dùng.

        Args:
            user_id: ID của người dùng.
            achievement_id: ID của loại thành tựu cần xóa.

        Returns:
            True nếu xóa thành công, False nếu người dùng chưa có thành tựu đó.
        """
        achievement = await self.get_by_user_and_achievement(user_id, achievement_id)
        if not achievement:
            return False  # Không tìm thấy, không có gì để xóa

        await self.db.delete(achievement)
        await self.db.commit()
        return True
