from typing import Optional, List, Dict, Any
from sqlalchemy import select, update, delete, func, or_, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.user_site.models.review import ReviewLike
from app.core.exceptions import NotFoundException


class ReviewLikeRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, like_data: Dict[str, Any]) -> ReviewLike:
        """Tạo mới một lượt thích cho đánh giá."""
        like = ReviewLike(**like_data)
        self.db.add(like)
        await self.db.commit()
        await self.db.refresh(like)
        return like

    async def get_by_id(self, like_id: int) -> Optional[ReviewLike]:
        """Lấy thông tin lượt thích theo ID."""
        query = select(ReviewLike).where(ReviewLike.id == like_id)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_by_user_and_review(
        self, user_id: int, review_id: int
    ) -> Optional[ReviewLike]:
        """Kiểm tra người dùng đã thích đánh giá chưa."""
        query = select(ReviewLike).where(
            and_(ReviewLike.user_id == user_id, ReviewLike.review_id == review_id)
        )
        result = await self.db.execute(query)
        return result.scalars().first()

    async def delete(self, like_id: int) -> bool:
        """Xóa lượt thích."""
        like = await self.get_by_id(like_id)
        if not like:
            raise NotFoundException(
                detail=f"Không tìm thấy lượt thích với ID {like_id}"
            )

        await self.db.delete(like)
        await self.db.commit()
        return True

    async def count_by_review(self, review_id: int) -> int:
        """Đếm số lượng lượt thích của một đánh giá."""
        query = select(func.count(ReviewLike.id)).where(
            ReviewLike.review_id == review_id
        )
        result = await self.db.execute(query)
        return result.scalar_one()

    async def delete_by_review(self, review_id: int) -> int:
        """Xóa tất cả lượt thích của một đánh giá."""
        query = delete(ReviewLike).where(ReviewLike.review_id == review_id)
        result = await self.db.execute(query)
        await self.db.commit()
        return result.rowcount

    async def delete_by_user(self, user_id: int) -> int:
        """Xóa tất cả lượt thích của một người dùng."""
        query = delete(ReviewLike).where(ReviewLike.user_id == user_id)
        result = await self.db.execute(query)
        await self.db.commit()
        return result.rowcount

    async def list_by_user(
        self, user_id: int, skip: int = 0, limit: int = 20
    ) -> List[ReviewLike]:
        """Lấy danh sách lượt thích của một người dùng."""
        query = select(ReviewLike).where(ReviewLike.user_id == user_id)
        query = query.options(joinedload(ReviewLike.review))
        query = query.order_by(ReviewLike.created_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return result.scalars().all()

    async def count_by_user(self, user_id: int) -> int:
        """Đếm số lượng lượt thích của một người dùng."""
        query = select(func.count(ReviewLike.id)).where(ReviewLike.user_id == user_id)
        result = await self.db.execute(query)
        return result.scalar_one()

    async def list_by_review(
        self, review_id: int, skip: int = 0, limit: int = 20
    ) -> List[ReviewLike]:
        """Lấy danh sách người dùng đã thích một đánh giá."""
        query = select(ReviewLike).where(ReviewLike.review_id == review_id)
        query = query.options(joinedload(ReviewLike.user))
        query = query.order_by(ReviewLike.created_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return result.scalars().all()
