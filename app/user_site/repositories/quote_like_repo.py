from typing import Optional, List, Dict, Any
from sqlalchemy import select, update, delete, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.exc import IntegrityError

from app.user_site.models.quote import QuoteLike, Quote
from app.user_site.models.user import User
from app.core.exceptions import NotFoundException, ConflictException


class QuoteLikeRepository:
    """Repository cho các thao tác liên quan đến việc "thích" trích dẫn (QuoteLike)."""

    def __init__(self, db: AsyncSession):
        """Khởi tạo repository với AsyncSession.

        Args:
            db: Đối tượng AsyncSession để tương tác với cơ sở dữ liệu.
        """
        self.db = db

    async def create(self, like_data: Dict[str, Any]) -> QuoteLike:
        """Tạo mới một lượt thích cho trích dẫn."""
        like = QuoteLike(**like_data)
        self.db.add(like)
        await self.db.commit()
        await self.db.refresh(like)
        return like

    async def get_by_id(self, like_id: int) -> Optional[QuoteLike]:
        """Lấy thông tin lượt thích theo ID."""
        query = select(QuoteLike).where(QuoteLike.id == like_id)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_by_user_and_quote(
        self, user_id: int, quote_id: int
    ) -> Optional[QuoteLike]:
        """Kiểm tra người dùng đã thích trích dẫn chưa."""
        query = select(QuoteLike).where(
            and_(QuoteLike.user_id == user_id, QuoteLike.quote_id == quote_id)
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

    async def count_by_quote(self, quote_id: int) -> int:
        """Đếm số lượng lượt thích của một trích dẫn."""
        query = select(func.count(QuoteLike.id)).where(QuoteLike.quote_id == quote_id)
        result = await self.db.execute(query)
        return result.scalar_one()

    async def delete_by_quote(self, quote_id: int) -> int:
        """Xóa tất cả lượt thích của một trích dẫn."""
        query = delete(QuoteLike).where(QuoteLike.quote_id == quote_id)
        result = await self.db.execute(query)
        await self.db.commit()
        return result.rowcount

    async def delete_by_user(self, user_id: int) -> int:
        """Xóa tất cả lượt thích của một người dùng."""
        query = delete(QuoteLike).where(QuoteLike.user_id == user_id)
        result = await self.db.execute(query)
        await self.db.commit()
        return result.rowcount

    async def list_by_user(
        self, user_id: int, skip: int = 0, limit: int = 20
    ) -> List[QuoteLike]:
        """Lấy danh sách lượt thích của một người dùng."""
        query = select(QuoteLike).where(QuoteLike.user_id == user_id)
        query = query.options(joinedload(QuoteLike.quote))
        query = query.order_by(QuoteLike.created_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return result.scalars().all()

    async def count_by_user(self, user_id: int) -> int:
        """Đếm số lượng lượt thích của một người dùng."""
        query = select(func.count(QuoteLike.id)).where(QuoteLike.user_id == user_id)
        result = await self.db.execute(query)
        return result.scalar_one()

    async def list_by_quote(
        self, quote_id: int, skip: int = 0, limit: int = 20
    ) -> List[QuoteLike]:
        """Lấy danh sách người dùng đã thích một trích dẫn."""
        query = select(QuoteLike).where(QuoteLike.quote_id == quote_id)
        query = query.options(joinedload(QuoteLike.user))
        query = query.order_by(QuoteLike.created_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return result.scalars().all()

    async def like_quote(self, user_id: int, quote_id: int) -> QuoteLike:
        """Người dùng (user_id) thích một trích dẫn (quote_id).

        Nếu đã thích rồi, trả về bản ghi hiện có.

        Args:
            user_id: ID của người dùng thực hiện thích.
            quote_id: ID của trích dẫn được thích.

        Returns:
            Đối tượng QuoteLike đại diện cho lượt thích.

        Raises:
            NotFoundException: Nếu user_id hoặc quote_id không tồn tại.
            ConflictException: Nếu có lỗi xảy ra khi thêm vào CSDL (ví dụ: lỗi ràng buộc khác).
        """
        # Kiểm tra xem đã thích chưa
        existing_like = await self.get_like(user_id, quote_id)
        if existing_like:
            return existing_like

        # Kiểm tra sự tồn tại của user và quote trước khi tạo like
        user = await self.db.get(User, user_id)
        if not user:
            raise NotFoundException(f"Người dùng với ID {user_id} không tồn tại.")
        quote = await self.db.get(Quote, quote_id)
        if not quote:
            raise NotFoundException(f"Trích dẫn với ID {quote_id} không tồn tại.")

        # Tạo mới lượt thích
        like = QuoteLike(user_id=user_id, quote_id=quote_id)
        self.db.add(like)
        try:
            await self.db.commit()
            await self.db.refresh(like)
            return like
        except IntegrityError as e:
            await self.db.rollback()
            # Kiểm tra lại xem có phải do race condition không
            existing_like = await self.get_like(user_id, quote_id)
            if existing_like:
                return existing_like  # Trả về cái đã tồn tại nếu người khác vừa tạo
            raise ConflictException(f"Không thể thích trích dẫn: {e}")

    async def unlike_quote(self, user_id: int, quote_id: int) -> bool:
        """Người dùng (user_id) bỏ thích một trích dẫn (quote_id).

        Args:
            user_id: ID của người dùng bỏ thích.
            quote_id: ID của trích dẫn bị bỏ thích.

        Returns:
            True nếu bỏ thích thành công (tìm thấy và xóa được), False nếu không tìm thấy lượt thích.
        """
        query = delete(QuoteLike).where(
            and_(QuoteLike.user_id == user_id, QuoteLike.quote_id == quote_id)
        )
        result = await self.db.execute(query)
        await self.db.commit()
        # result.rowcount trả về số dòng bị ảnh hưởng (đã xóa)
        return result.rowcount > 0

    async def get_like(self, user_id: int, quote_id: int) -> Optional[QuoteLike]:
        """Lấy bản ghi lượt thích cụ thể của người dùng cho một trích dẫn.

        Args:
            user_id: ID người dùng.
            quote_id: ID trích dẫn.

        Returns:
            Đối tượng QuoteLike hoặc None nếu chưa thích.
        """
        query = select(QuoteLike).where(
            and_(QuoteLike.user_id == user_id, QuoteLike.quote_id == quote_id)
        )
        result = await self.db.execute(query)
        return result.scalars().first()

    async def check_user_like(self, user_id: int, quote_id: int) -> bool:
        """Kiểm tra nhanh xem người dùng đã thích trích dẫn này chưa.

        Args:
            user_id: ID người dùng.
            quote_id: ID trích dẫn.

        Returns:
            True nếu đã thích, False nếu chưa.
        """
        query = select(func.count(QuoteLike.id)).where(
            QuoteLike.user_id == user_id, QuoteLike.quote_id == quote_id
        )
        result = await self.db.execute(query)
        # Chỉ cần kiểm tra > 0 là đủ
        return (result.scalar_one() or 0) > 0

    async def count_likes_for_quote(self, quote_id: int) -> int:
        """Đếm tổng số lượt thích cho một trích dẫn.

        Args:
            quote_id: ID của trích dẫn.

        Returns:
            Tổng số lượt thích (int), trả về 0 nếu không có lượt thích nào.
        """
        query = select(func.count(QuoteLike.id)).where(QuoteLike.quote_id == quote_id)
        result = await self.db.execute(query)
        # scalar_one() trả về None nếu count = 0, nên cần or 0
        return result.scalar_one() or 0

    async def list_users_who_liked_quote(
        self, quote_id: int, skip: int = 0, limit: int = 20
    ) -> List[User]:
        """Lấy danh sách người dùng đã thích một trích dẫn.

        Args:
            quote_id: ID của trích dẫn.
            skip: Số lượng bỏ qua (phân trang).
            limit: Giới hạn số lượng kết quả (phân trang).

        Returns:
            Danh sách các đối tượng User đã thích trích dẫn.
        """
        query = (
            select(User)
            .join(QuoteLike, QuoteLike.user_id == User.id)
            .where(QuoteLike.quote_id == quote_id)
            .options(selectinload(User.social_profiles))  # Load thêm profile nếu cần
            .order_by(User.username)  # Sắp xếp theo tên người dùng
            .offset(skip)
            .limit(limit)
        )
        result = await self.db.execute(query)
        return result.scalars().all()

    async def list_quotes_liked_by_user(
        self, user_id: int, skip: int = 0, limit: int = 20
    ) -> List[Quote]:
        """Lấy danh sách các trích dẫn mà người dùng đã thích.

        Args:
            user_id: ID của người dùng.
            skip: Số lượng bỏ qua (phân trang).
            limit: Giới hạn số lượng kết quả (phân trang).

        Returns:
            Danh sách các đối tượng Quote mà người dùng đã thích.
        """
        query = (
            select(Quote)
            .join(QuoteLike, QuoteLike.quote_id == Quote.id)
            .where(QuoteLike.user_id == user_id)
            .options(
                selectinload(Quote.book),  # Load thông tin sách của trích dẫn
                selectinload(Quote.user),  # Load người tạo trích dẫn
            )
            .order_by(
                QuoteLike.created_at.desc()
            )  # Sắp xếp theo thời gian thích gần nhất
            .offset(skip)
            .limit(limit)
        )
        result = await self.db.execute(query)
        return result.scalars().all()

    async def count_quotes_liked_by_user(self, user_id: int) -> int:
        """Đếm số lượng trích dẫn mà người dùng đã thích.

        Args:
            user_id: ID của người dùng.

        Returns:
            Số lượng trích dẫn đã thích.
        """
        query = select(func.count(QuoteLike.id)).where(QuoteLike.user_id == user_id)
        result = await self.db.execute(query)
        return result.scalar_one() or 0
