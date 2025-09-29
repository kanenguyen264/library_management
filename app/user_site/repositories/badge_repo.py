from typing import Optional, List, Dict, Any
from sqlalchemy import select, update, delete, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.user_site.models.badge import UserBadge
from app.core.exceptions import NotFoundException


class BadgeRepository:
    """Repository cho các thao tác liên quan đến huy hiệu người dùng (UserBadge)."""

    def __init__(self, db: AsyncSession):
        """Khởi tạo repository với AsyncSession."""
        self.db = db

    async def create(self, badge_data: Dict[str, Any]) -> UserBadge:
        """Tạo một bản ghi huy hiệu mới cho người dùng.

        Args:
            badge_data: Dữ liệu huy hiệu (ví dụ: user_id, badge_id, earned_at).

        Returns:
            Đối tượng UserBadge đã được tạo.
        """
        # Lọc các trường hợp lệ cho UserBadge
        allowed_fields = {"user_id", "badge_id", "earned_at"}
        filtered_data = {k: v for k, v in badge_data.items() if k in allowed_fields}
        badge = UserBadge(**filtered_data)
        self.db.add(badge)
        await self.db.commit()
        await self.db.refresh(badge)
        return badge

    async def get_by_id(
        self, badge_id: int, with_relations: Optional[List[str]] = None
    ) -> Optional[UserBadge]:
        """Lấy huy hiệu theo ID của bản ghi UserBadge.

        Args:
            badge_id: ID của bản ghi UserBadge.
            with_relations: Danh sách các mối quan hệ cần load (ví dụ: ["user", "badge_definition"]).

        Returns:
            Đối tượng UserBadge hoặc None nếu không tìm thấy.
        """
        query = select(UserBadge).where(UserBadge.id == badge_id)

        if with_relations:
            options = []
            if "user" in with_relations:
                options.append(selectinload(UserBadge.user))
            # Giả sử có mối quan hệ tới định nghĩa Badge gốc
            # if "badge_definition" in with_relations:
            #     options.append(selectinload(UserBadge.badge))
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_by_user_and_badge(
        self, user_id: int, badge_id: int
    ) -> Optional[UserBadge]:
        """Lấy huy hiệu cụ thể (dựa trên badge_id gốc) của một người dùng.

        Args:
            user_id: ID của người dùng.
            badge_id: ID của loại huy hiệu (ví dụ: ID từ bảng Badge gốc).

        Returns:
            Đối tượng UserBadge hoặc None nếu người dùng chưa có huy hiệu đó.
        """
        # Giả định badge_id trong UserBadge là ID của loại huy hiệu
        query = select(UserBadge).where(
            UserBadge.user_id == user_id,
            UserBadge.badge_id == badge_id,  # Cần khớp với tên cột trong model
        )
        result = await self.db.execute(query)
        return result.scalars().first()

    async def list_by_user(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 20,
        with_relations: Optional[List[str]] = None,
    ) -> List[UserBadge]:
        """Lấy danh sách huy hiệu theo user_id, sắp xếp theo ngày nhận gần nhất.

        Args:
            user_id: ID của người dùng.
            skip: Số lượng bản ghi bỏ qua.
            limit: Số lượng bản ghi tối đa trả về.
            with_relations: Danh sách các mối quan hệ cần load.

        Returns:
            Danh sách các đối tượng UserBadge.
        """
        query = select(UserBadge).where(UserBadge.user_id == user_id)

        if with_relations:
            options = []
            # Ví dụ: load badge definition
            # if "badge_definition" in with_relations:
            #     options.append(selectinload(UserBadge.badge))
            if options:
                query = query.options(*options)

        query = query.order_by(desc(UserBadge.earned_at))
        query = query.offset(skip).limit(limit)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def count_by_user(self, user_id: int) -> int:
        """Đếm số lượng huy hiệu mà người dùng đã đạt được.

        Args:
            user_id: ID của người dùng.

        Returns:
            Tổng số huy hiệu đã đạt được.
        """
        query = select(func.count(UserBadge.id)).where(UserBadge.user_id == user_id)
        result = await self.db.execute(query)
        return result.scalar_one() or 0

    async def delete(self, badge_id: int) -> bool:
        """Xóa một bản ghi huy hiệu theo ID của nó.

        Args:
            badge_id: ID của bản ghi UserBadge cần xóa.

        Returns:
            True nếu xóa thành công.

        Raises:
            NotFoundException: Nếu không tìm thấy bản ghi huy hiệu với ID cung cấp.
        """
        badge = await self.get_by_id(badge_id)
        if not badge:
            raise NotFoundException(detail=f"Không tìm thấy huy hiệu với ID {badge_id}")

        await self.db.delete(badge)
        await self.db.commit()
        return True

    async def delete_by_user_and_badge(self, user_id: int, badge_id: int) -> bool:
        """Xóa một huy hiệu cụ thể của người dùng.

        Args:
            user_id: ID của người dùng.
            badge_id: ID của loại huy hiệu cần xóa.

        Returns:
            True nếu xóa thành công, False nếu người dùng chưa có huy hiệu đó.
        """
        badge = await self.get_by_user_and_badge(user_id, badge_id)
        if not badge:
            return False

        await self.db.delete(badge)
        await self.db.commit()
        return True
