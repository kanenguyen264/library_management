from typing import Optional, List, Dict, Any
from sqlalchemy import (
    select,
    func,
    update,
    desc,
    asc,
    and_,
    or_,
    delete,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.exc import IntegrityError

from app.user_site.models.discussion import Discussion, DiscussionComment
from app.user_site.models.user import User
from app.user_site.models.book import Book
from app.user_site.models.chapter import Chapter
from app.core.exceptions import NotFoundException, ConflictException


class DiscussionRepository:
    """Repository cho các thao tác với thảo luận (Discussion) và bình luận (DiscussionComment)."""

    def __init__(self, db: AsyncSession):
        """Khởi tạo repository với AsyncSession."""
        self.db = db

    # --- Discussion Methods --- #

    async def create_discussion(self, data: Dict[str, Any]) -> Discussion:
        """Tạo một thảo luận mới.

        Args:
            data: Dữ liệu thảo luận (user_id, book_id, chapter_id, title, content, is_pinned, is_closed).

        Returns:
            Đối tượng Discussion đã tạo.

        Raises:
            NotFoundException: Nếu user_id, book_id, chapter_id không hợp lệ (nếu có check FK).
            ConflictException: Nếu có lỗi ràng buộc khác.
        """
        allowed_fields = {
            "user_id",
            "book_id",
            "chapter_id",
            "title",
            "content",
            "is_pinned",
            "is_closed",
        }
        filtered_data = {k: v for k, v in data.items() if k in allowed_fields}
        discussion = Discussion(**filtered_data)
        self.db.add(discussion)
        try:
            await self.db.commit()
            await self.db.refresh(discussion)
            return discussion
        except IntegrityError:
            await self.db.rollback()
            raise ConflictException("Không thể tạo thảo luận do lỗi ràng buộc dữ liệu.")

    async def get_by_id(
        self, discussion_id: int, with_relations: Optional[List[str]] = None
    ) -> Optional[Discussion]:
        """Lấy thảo luận theo ID.

        Args:
            discussion_id: ID của thảo luận.
            with_relations: Quan hệ cần load (["user", "book", "chapter", "comments"]).

        Returns:
            Đối tượng Discussion hoặc None.
        """
        query = select(Discussion).where(Discussion.id == discussion_id)

        if with_relations:
            options = []
            if "user" in with_relations:
                options.append(selectinload(Discussion.user))
            if "book" in with_relations:
                options.append(selectinload(Discussion.book))
            if "chapter" in with_relations:
                options.append(selectinload(Discussion.chapter))
            if "comments" in with_relations:
                options.append(
                    selectinload(Discussion.comments)
                    .where(DiscussionComment.parent_id.is_(None))
                    .options(
                        selectinload(DiscussionComment.user),
                        selectinload(DiscussionComment.replies).options(
                            selectinload(DiscussionComment.user)
                        ),
                    )
                )
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().first()

    async def list_discussions(
        self,
        book_id: Optional[int] = None,
        chapter_id: Optional[int] = None,
        user_id: Optional[int] = None,
        is_pinned: Optional[bool] = None,
        is_closed: Optional[bool] = None,
        skip: int = 0,
        limit: int = 20,
        sort_by: str = "created_at",
        sort_desc: bool = True,
        with_relations: Optional[List[str]] = ["user", "book"],
    ) -> List[Discussion]:
        """Lấy danh sách thảo luận với các bộ lọc và sắp xếp.

        Args:
            book_id, chapter_id, user_id: Lọc theo ID.
            is_pinned, is_closed: Lọc theo trạng thái.
            skip, limit: Phân trang.
            sort_by: Trường sắp xếp (created_at, upvotes, comments_count).
            sort_desc: Sắp xếp giảm dần.
            with_relations: Quan hệ cần load.

        Returns:
            Danh sách Discussion.
        """
        query = select(Discussion)

        # Áp dụng các bộ lọc
        if book_id is not None:
            query = query.filter(Discussion.book_id == book_id)
        if chapter_id is not None:
            query = query.filter(Discussion.chapter_id == chapter_id)
        if user_id is not None:
            query = query.filter(Discussion.user_id == user_id)
        if is_pinned is not None:
            query = query.filter(Discussion.is_pinned == is_pinned)
        if is_closed is not None:
            query = query.filter(Discussion.is_closed == is_closed)

        # Sắp xếp
        sort_attr = getattr(Discussion, sort_by, Discussion.created_at)
        if sort_desc:
            query = query.order_by(desc(sort_attr))
        else:
            query = query.order_by(asc(sort_attr))

        # Áp dụng phân trang
        query = query.offset(skip).limit(limit)

        # Load các mối quan hệ
        if with_relations:
            options = []
            if "user" in with_relations:
                options.append(selectinload(Discussion.user))
            if "book" in with_relations:
                options.append(selectinload(Discussion.book))
            if "chapter" in with_relations:
                options.append(selectinload(Discussion.chapter))
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def update_discussion(
        self, discussion_id: int, data: Dict[str, Any]
    ) -> Discussion:
        """Cập nhật thảo luận (title, content, is_pinned, is_closed).

        Args:
            discussion_id: ID thảo luận cần cập nhật.
            data: Dữ liệu cập nhật.

        Returns:
            Đối tượng Discussion đã cập nhật.

        Raises:
            NotFoundException: Nếu không tìm thấy thảo luận.
        """
        discussion = await self.get_by_id(discussion_id)
        if not discussion:
            raise NotFoundException(
                detail=f"Không tìm thấy thảo luận với ID {discussion_id}"
            )

        allowed_fields = {"title", "content", "is_pinned", "is_closed"}
        for key, value in data.items():
            if key in allowed_fields:
                setattr(discussion, key, value)

        await self.db.commit()
        await self.db.refresh(discussion)
        return discussion

    async def delete_discussion(self, discussion_id: int) -> bool:
        """Xóa thảo luận. Lưu ý: Cần xử lý các comment liên quan.

        Args:
            discussion_id: ID thảo luận cần xóa.

        Returns:
            True nếu xóa thành công, False nếu không tìm thấy.
        """
        discussion = await self.get_by_id(discussion_id)
        if not discussion:
            return False

        try:
            # Xóa các comment liên quan trước nếu không có cascade
            await self.db.execute(
                delete(DiscussionComment).where(
                    DiscussionComment.discussion_id == discussion_id
                )
            )
            await self.db.delete(discussion)
            await self.db.commit()
            return True
        except IntegrityError:
            await self.db.rollback()
            raise  # Ném lại lỗi nếu có vấn đề khác

    async def count_discussions(
        self,
        book_id: Optional[int] = None,
        chapter_id: Optional[int] = None,
        user_id: Optional[int] = None,
        is_pinned: Optional[bool] = None,
        is_closed: Optional[bool] = None,
    ) -> int:
        """Đếm số lượng thảo luận theo các bộ lọc.

        Args:
            book_id, chapter_id, user_id: Lọc theo ID.
            is_pinned, is_closed: Lọc theo trạng thái.

        Returns:
            Tổng số thảo luận khớp điều kiện.
        """
        query = select(func.count(Discussion.id))

        if book_id is not None:
            query = query.filter(Discussion.book_id == book_id)
        if chapter_id is not None:
            query = query.filter(Discussion.chapter_id == chapter_id)
        if user_id is not None:
            query = query.filter(Discussion.user_id == user_id)
        if is_pinned is not None:
            query = query.filter(Discussion.is_pinned == is_pinned)
        if is_closed is not None:
            query = query.filter(Discussion.is_closed == is_closed)

        result = await self.db.execute(query)
        return result.scalar_one() or 0

    async def update_votes(
        self, discussion_id: int, change: int = 1, vote_type: str = "up"
    ) -> Discussion:
        """Cập nhật số lượt vote cho thảo luận (yêu cầu logic kiểm tra vote trùng lặp bên ngoài).

        Args:
            discussion_id: ID thảo luận.
            change: Số lượng thay đổi (+1 hoặc -1).
            vote_type: 'up' hoặc 'down'.

        Returns:
            Đối tượng Discussion đã cập nhật.

        Raises:
            NotFoundException: Nếu không tìm thấy thảo luận.
        """
        discussion = await self.get_by_id(discussion_id)
        if not discussion:
            raise NotFoundException(
                detail=f"Không tìm thấy thảo luận với ID {discussion_id}"
            )

        if vote_type == "up":
            discussion.upvotes = max(0, discussion.upvotes + change)  # Đảm bảo không âm
        elif vote_type == "down":
            discussion.downvotes = max(0, discussion.downvotes + change)

        await self.db.commit()
        await self.db.refresh(discussion)
        return discussion

    # Phần bổ sung cho DiscussionComment

    async def create_comment(self, data: Dict[str, Any]) -> DiscussionComment:
        """Tạo một bình luận mới.

        Args:
            data: Dữ liệu bình luận (discussion_id, user_id, content, parent_id).

        Returns:
            Đối tượng DiscussionComment đã tạo.

        Raises:
            NotFoundException: Nếu discussion_id hoặc parent_id không hợp lệ.
            ConflictException: Nếu có lỗi ràng buộc khác.
        """
        allowed_fields = {"discussion_id", "user_id", "content", "parent_id"}
        filtered_data = {k: v for k, v in data.items() if k in allowed_fields}

        discussion_id = filtered_data.get("discussion_id")
        parent_id = filtered_data.get("parent_id")

        # Kiểm tra discussion tồn tại
        discussion = await self.get_by_id(discussion_id)
        if not discussion:
            raise NotFoundException(f"Thảo luận với ID {discussion_id} không tồn tại.")

        # Kiểm tra parent comment tồn tại nếu có
        if parent_id:
            parent_comment = await self.get_comment_by_id(parent_id)
            if not parent_comment:
                raise NotFoundException(
                    f"Bình luận cha với ID {parent_id} không tồn tại."
                )
            # Đảm bảo parent comment thuộc cùng discussion?
            if parent_comment.discussion_id != discussion_id:
                raise ConflictException("Bình luận cha không thuộc thảo luận này.")

        comment = DiscussionComment(**filtered_data)
        self.db.add(comment)

        try:
            # Tăng comments_count của discussion
            discussion.comments_count += 1
            await self.db.commit()
            await self.db.refresh(comment)
            return comment
        except IntegrityError:
            await self.db.rollback()
            raise ConflictException("Không thể tạo bình luận do lỗi ràng buộc dữ liệu.")

    async def get_comment_by_id(
        self, comment_id: int, with_relations: Optional[List[str]] = None
    ) -> Optional[DiscussionComment]:
        """Lấy bình luận theo ID.

        Args:
            comment_id: ID bình luận.
            with_relations: Quan hệ cần load (["user", "discussion", "parent", "replies"]).

        Returns:
            Đối tượng DiscussionComment hoặc None.
        """
        query = select(DiscussionComment).where(DiscussionComment.id == comment_id)

        if with_relations:
            options = []
            if "user" in with_relations:
                options.append(selectinload(DiscussionComment.user))
            if "discussion" in with_relations:
                options.append(selectinload(DiscussionComment.discussion))
            if "parent" in with_relations:
                options.append(selectinload(DiscussionComment.parent))
            if "replies" in with_relations:
                options.append(
                    selectinload(DiscussionComment.replies).options(
                        selectinload(DiscussionComment.user)
                    )
                )
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().first()

    async def list_comments(
        self,
        discussion_id: int,
        parent_id: Optional[int] = -1,
        skip: int = 0,
        limit: int = 50,
        sort_by: str = "created_at",
        sort_desc: bool = True,
        with_relations: Optional[List[str]] = ["user", "replies"],
    ) -> List[DiscussionComment]:
        """Lấy danh sách bình luận cho một thảo luận.

        Args:
            discussion_id: ID thảo luận.
            parent_id: Lọc theo ID cha (-1 lấy gốc, None lấy tất cả, ID cụ thể lấy replies).
            skip, limit: Phân trang.
            sort_by: Trường sắp xếp (created_at, upvotes).
            sort_desc: Sắp xếp giảm dần.
            with_relations: Quan hệ cần load.

        Returns:
            Danh sách DiscussionComment.
        """
        query = select(DiscussionComment).where(
            DiscussionComment.discussion_id == discussion_id
        )

        if parent_id == -1:
            query = query.filter(DiscussionComment.parent_id.is_(None))
        elif parent_id is not None:
            query = query.filter(DiscussionComment.parent_id == parent_id)

        sort_attr = getattr(DiscussionComment, sort_by, DiscussionComment.created_at)
        if sort_desc:
            query = query.order_by(desc(sort_attr))
        else:
            query = query.order_by(asc(sort_attr))

        query = query.offset(skip).limit(limit)

        if with_relations:
            options = []
            if "user" in with_relations:
                options.append(selectinload(DiscussionComment.user))
            if parent_id == -1 and "replies" in with_relations:
                options.append(
                    selectinload(DiscussionComment.replies).options(
                        selectinload(DiscussionComment.user)
                    )
                )
            if "parent" in with_relations:
                options.append(selectinload(DiscussionComment.parent))
            if options:
                query = query.options(*options)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def update_comment(
        self, comment_id: int, data: Dict[str, Any]
    ) -> DiscussionComment:
        """Cập nhật nội dung bình luận.

        Args:
            comment_id: ID bình luận cần cập nhật.
            data: Dữ liệu cập nhật (chỉ 'content').

        Returns:
            Đối tượng DiscussionComment đã cập nhật.

        Raises:
            NotFoundException: Nếu không tìm thấy bình luận.
        """
        comment = await self.get_comment_by_id(comment_id)
        if not comment:
            raise NotFoundException(
                detail=f"Không tìm thấy bình luận với ID {comment_id}"
            )

        allowed_fields = {"content"}
        updated = False
        for key, value in data.items():
            if key in allowed_fields and getattr(comment, key) != value:
                setattr(comment, key, value)
                updated = True

        if updated:
            await self.db.commit()
            await self.db.refresh(comment)
        return comment

    async def delete_comment(self, comment_id: int) -> bool:
        """Xóa bình luận và giảm comment_count của discussion.

        Args:
            comment_id: ID bình luận cần xóa.

        Returns:
            True nếu xóa thành công, False nếu không tìm thấy.
        """
        comment = await self.get_comment_by_id(comment_id)
        if not comment:
            return False

        discussion_id = comment.discussion_id
        await self.db.delete(comment)

        # Giảm comment_count sau khi xóa thành công
        discussion = await self.get_by_id(discussion_id)
        if discussion and discussion.comments_count > 0:
            discussion.comments_count -= 1

        await self.db.commit()
        return True

    async def count_comments(
        self, discussion_id: int, parent_id: Optional[int] = -1
    ) -> int:
        """Đếm số lượng bình luận cho một thảo luận.

        Args:
            discussion_id: ID thảo luận.
            parent_id: Lọc theo ID cha (-1 đếm gốc, None đếm tất cả, ID cụ thể đếm replies).

        Returns:
            Tổng số bình luận khớp điều kiện.
        """
        query = select(func.count(DiscussionComment.id)).where(
            DiscussionComment.discussion_id == discussion_id
        )

        if parent_id == -1:
            query = query.filter(DiscussionComment.parent_id.is_(None))
        elif parent_id is not None:
            query = query.filter(DiscussionComment.parent_id == parent_id)

        result = await self.db.execute(query)
        return result.scalar_one() or 0

    async def update_comment_votes(
        self, comment_id: int, change: int = 1, vote_type: str = "up"
    ) -> DiscussionComment:
        """Cập nhật số lượt vote cho bình luận (yêu cầu logic kiểm tra vote trùng lặp bên ngoài).

        Args:
            comment_id: ID bình luận.
            change: Số lượng thay đổi (+1 hoặc -1).
            vote_type: 'up' hoặc 'down'.

        Returns:
            Đối tượng DiscussionComment đã cập nhật.

        Raises:
            NotFoundException: Nếu không tìm thấy bình luận.
        """
        comment = await self.get_comment_by_id(comment_id)
        if not comment:
            raise NotFoundException(
                detail=f"Không tìm thấy bình luận với ID {comment_id}"
            )

        if vote_type == "up":
            comment.upvotes = max(0, comment.upvotes + change)
        elif vote_type == "down":
            comment.downvotes = max(0, comment.downvotes + change)

        await self.db.commit()
        await self.db.refresh(comment)
        return comment
