from typing import Optional, List, Tuple
from sqlalchemy import select, func, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from datetime import datetime

from app.user_site.models.following import UserFollowing
from app.user_site.models.user import User
from app.core.exceptions import NotFoundException, ForbiddenException


class FollowingRepository:
    """Repository cho các thao tác liên quan đến việc theo dõi giữa người dùng."""

    def __init__(self, db: AsyncSession):
        """Khởi tạo repository với AsyncSession.

        Args:
            db: Đối tượng AsyncSession để tương tác với cơ sở dữ liệu.
        """
        self.db = db

    async def follow_user(self, follower_id: int, following_id: int) -> UserFollowing:
        """Thực hiện hành động người dùng (follower_id) theo dõi người dùng khác (following_id).

        Nếu đã theo dõi rồi, trả về bản ghi hiện có.
        Không cho phép người dùng tự theo dõi chính mình.

        Args:
            follower_id: ID của người thực hiện theo dõi.
            following_id: ID của người được theo dõi.

        Returns:
            Đối tượng UserFollowing đại diện cho mối quan hệ theo dõi.

        Raises:
            ForbiddenException: Nếu follower_id và following_id giống nhau.
            IntegrityError: Nếu có lỗi ràng buộc khóa ngoại (ví dụ: user_id không tồn tại).
        """
        # Kiểm tra không thể tự follow chính mình
        if follower_id == following_id:
            raise ForbiddenException(detail="Không thể tự theo dõi chính mình")

        # Kiểm tra xem đã follow chưa
        existing = await self.get_following(follower_id, following_id)
        if existing:
            return existing

        # Tạo mới nếu chưa theo dõi
        following = UserFollowing(follower_id=follower_id, following_id=following_id)
        self.db.add(following)
        await self.db.commit()
        await self.db.refresh(following)
        return following

    async def unfollow_user(self, follower_id: int, following_id: int) -> bool:
        """Thực hiện hành động người dùng (follower_id) hủy theo dõi người dùng khác (following_id).

        Args:
            follower_id: ID của người hủy theo dõi.
            following_id: ID của người bị hủy theo dõi.

        Returns:
            True nếu hủy theo dõi thành công (đã tồn tại và đã xóa), False nếu không tìm thấy mối quan hệ để xóa.
        """
        query = delete(UserFollowing).where(
            and_(
                UserFollowing.follower_id == follower_id,
                UserFollowing.following_id == following_id,
            )
        )
        result = await self.db.execute(query)
        await self.db.commit()

        # result.rowcount trả về số dòng bị ảnh hưởng (bị xóa)
        return result.rowcount > 0

    async def get_following(
        self, follower_id: int, following_id: int
    ) -> Optional[UserFollowing]:
        """Lấy bản ghi mối quan hệ theo dõi cụ thể.

        Args:
            follower_id: ID của người theo dõi.
            following_id: ID của người được theo dõi.

        Returns:
            Đối tượng UserFollowing hoặc None nếu không tồn tại.
        """
        query = select(UserFollowing).where(
            and_(
                UserFollowing.follower_id == follower_id,
                UserFollowing.following_id == following_id,
            )
        )
        result = await self.db.execute(query)
        return result.scalars().first()

    async def list_followers(
        self, user_id: int, skip: int = 0, limit: int = 20
    ) -> List[User]:
        """Lấy danh sách những người đang theo dõi user_id.

        Args:
            user_id: ID của người dùng được theo dõi.
            skip: Số lượng bỏ qua (phân trang).
            limit: Giới hạn số lượng kết quả (phân trang).

        Returns:
            Danh sách các đối tượng User là người theo dõi.
        """
        query = (
            select(User)
            .join(UserFollowing, UserFollowing.follower_id == User.id)
            .where(UserFollowing.following_id == user_id)
            .options(selectinload(User.social_profiles))
        )
        query = query.order_by(User.username).offset(skip).limit(limit)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def list_following(
        self, user_id: int, skip: int = 0, limit: int = 20
    ) -> List[User]:
        """Lấy danh sách những người mà user_id đang theo dõi.

        Args:
            user_id: ID của người dùng đang theo dõi.
            skip: Số lượng bỏ qua (phân trang).
            limit: Giới hạn số lượng kết quả (phân trang).

        Returns:
            Danh sách các đối tượng User đang được theo dõi.
        """
        query = (
            select(User)
            .join(UserFollowing, UserFollowing.following_id == User.id)
            .where(UserFollowing.follower_id == user_id)
            .options(selectinload(User.social_profiles))
        )
        query = query.order_by(User.username).offset(skip).limit(limit)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def count_followers(self, user_id: int) -> int:
        """Đếm số người đang theo dõi user_id."""
        query = select(func.count(UserFollowing.follower_id)).where(
            UserFollowing.following_id == user_id
        )
        result = await self.db.execute(query)
        return result.scalar_one() or 0

    async def count_following(self, user_id: int) -> int:
        """Đếm số người mà user_id đang theo dõi."""
        query = select(func.count(UserFollowing.following_id)).where(
            UserFollowing.follower_id == user_id
        )
        result = await self.db.execute(query)
        return result.scalar_one() or 0

    async def check_is_following(self, follower_id: int, following_id: int) -> bool:
        """Kiểm tra nhanh xem follower_id có đang theo dõi following_id không.

        Args:
            follower_id: ID người kiểm tra.
            following_id: ID người bị kiểm tra.

        Returns:
            True nếu đang theo dõi, False nếu không.
        """
        query = select(func.count(UserFollowing.id)).where(
            UserFollowing.follower_id == follower_id,
            UserFollowing.following_id == following_id,
        )
        result = await self.db.execute(query)
        return (result.scalar_one() or 0) > 0

    async def get_mutual_followers(
        self, user_id: int, other_user_id: int
    ) -> List[User]:
        """Lấy danh sách những người dùng cùng theo dõi cả user_id và other_user_id."""
        # Người theo dõi user_id
        followers1_subquery = (
            select(UserFollowing.follower_id)
            .where(UserFollowing.following_id == user_id)
            .scalar_subquery()
        )

        # Người theo dõi other_user_id
        followers2_subquery = (
            select(UserFollowing.follower_id)
            .where(UserFollowing.following_id == other_user_id)
            .scalar_subquery()
        )

        # Lấy những người dùng có ID nằm trong cả hai danh sách trên
        query = (
            select(User)
            .where(User.id.in_(followers1_subquery), User.id.in_(followers2_subquery))
            .options(selectinload(User.social_profiles))
        )
        query = query.order_by(User.username)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_followers_with_limit(
        self, user_id: int, limit: int = 5
    ) -> List[User]:
        """Lấy danh sách giới hạn người đang follow người dùng này."""
        query = (
            select(User)
            .join(UserFollowing, UserFollowing.follower_id == User.id)
            .where(UserFollowing.following_id == user_id)
            .limit(limit)
        )

        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_recent_followers(
        self, user_id: int, limit: int = 5
    ) -> List[Tuple[User, datetime]]:
        """Lấy danh sách những người mới theo dõi user_id gần đây nhất.

        Args:
            user_id: ID của người dùng được theo dõi.
            limit: Giới hạn số lượng kết quả.

        Returns:
            Danh sách các tuple chứa (Đối tượng User, Thời gian theo dõi).
        """
        query = (
            select(User, UserFollowing.created_at)
            .join(UserFollowing, UserFollowing.follower_id == User.id)
            .where(UserFollowing.following_id == user_id)
            .order_by(UserFollowing.created_at.desc())
            .options(selectinload(User.social_profiles))
            .limit(limit)
        )

        result = await self.db.execute(query)
        return [(row.User, row.created_at) for row in result]

    async def get_follow_suggestions(self, user_id: int, limit: int = 10) -> List[User]:
        """Đề xuất người dùng để user_id theo dõi (ví dụ: bạn của bạn bè).

        Logic ví dụ: Lấy những người mà những người user_id đang theo dõi cũng theo dõi,
        nhưng user_id chưa theo dõi.

        Args:
            user_id: ID của người dùng cần đề xuất.
            limit: Giới hạn số lượng đề xuất.

        Returns:
            Danh sách các đối tượng User được đề xuất.
        """
        # Những người mà user_id đang theo dõi
        following_subquery = (
            select(UserFollowing.following_id)
            .where(UserFollowing.follower_id == user_id)
            .scalar_subquery()
        )

        # Những người được theo dõi bởi những người trong `following_subquery`
        # và không phải là user_id, cũng như user_id chưa theo dõi họ
        query = (
            select(User)
            .join(UserFollowing, UserFollowing.following_id == User.id)
            .where(
                UserFollowing.follower_id.in_(following_subquery),
                User.id != user_id,
                ~User.id.in_(following_subquery),
            )
            .group_by(User.id)
            .order_by(func.count(User.id).desc())
        )
        query = query.options(selectinload(User.social_profiles)).limit(limit)

        result = await self.db.execute(query)
        return result.scalars().all()
