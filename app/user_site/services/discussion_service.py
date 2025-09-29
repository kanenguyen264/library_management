from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.user_site.repositories.discussion_repo import DiscussionRepository
from app.user_site.repositories.book_repo import BookRepository
from app.user_site.repositories.chapter_repo import ChapterRepository
from app.user_site.repositories.user_repo import UserRepository
from app.core.exceptions import (
    NotFoundException,
    BadRequestException,
    ForbiddenException,
)
from app.cache.decorators import cached, invalidate_cache
from app.performance.profiling.code_profiler import CodeProfiler
from app.monitoring.metrics import Metrics
from app.cache import get_cache
from app.cache.keys import CacheKeyBuilder
from app.security.input_validation.sanitizers import sanitize_html
from app.security.access_control.rbac import check_permission
from app.logs_manager.services.user_activity_log_service import UserActivityLogService
from app.core.config import get_settings

settings = get_settings()


class DiscussionService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.discussion_repo = DiscussionRepository(db)
        self.book_repo = BookRepository(db)
        self.chapter_repo = ChapterRepository(db)
        self.user_repo = UserRepository(db)
        self.metrics = Metrics()
        self.user_log_service = UserActivityLogService()
        self.cache = get_cache()

    @CodeProfiler.profile_time(threshold=0.5)
    @invalidate_cache(
        namespace="discussions", tags=["book_discussions", "chapter_discussions"]
    )
    async def create_discussion(
        self,
        user_id: int,
        title: str,
        content: str,
        book_id: int,
        chapter_id: Optional[int] = None,
        is_spoiler: bool = False,
    ) -> Dict[str, Any]:
        """
        Tạo một cuộc thảo luận mới.

        Args:
            user_id: ID của người dùng tạo thảo luận
            title: Tiêu đề của thảo luận
            content: Nội dung thảo luận
            book_id: ID của sách liên quan
            chapter_id: ID của chương liên quan (tùy chọn)
            is_spoiler: Đánh dấu có spoiler hay không

        Returns:
            Thông tin thảo luận đã tạo

        Raises:
            NotFoundException: Nếu không tìm thấy sách hoặc chương
        """
        # Kiểm tra dữ liệu đầu vào
        if not title or not content or not book_id:
            raise BadRequestException("Thiếu thông tin bắt buộc để tạo thảo luận")

        # Làm sạch dữ liệu
        title = sanitize_html(title)
        content = sanitize_html(content)

        # Kiểm tra user tồn tại
        user = await self.user_repo.get(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng với ID {user_id}")

        # Kiểm tra sách tồn tại
        book = await self.book_repo.get(book_id)
        if not book:
            raise NotFoundException(f"Không tìm thấy sách với ID {book_id}")

        # Kiểm tra chương tồn tại nếu có
        if chapter_id:
            chapter = await self.chapter_repo.get(chapter_id)
            if not chapter:
                raise NotFoundException(f"Không tìm thấy chương với ID {chapter_id}")

            # Kiểm tra chương có thuộc sách này không
            if chapter["book_id"] != book_id:
                raise BadRequestException("Chương không thuộc sách này")

        # Tạo thảo luận
        discussion_data = {
            "user_id": user_id,
            "book_id": book_id,
            "chapter_id": chapter_id,
            "title": title,
            "content": content,
            "is_spoiler": is_spoiler,
            "is_pinned": False,
            "vote_count": 0,
            "status": "active",
        }

        discussion = await self.discussion_repo.create(discussion_data)

        # Ghi log hoạt động
        await self.user_log_service.log_activity(
            self.db,
            user_id=user_id,
            activity_type="CREATE_DISCUSSION",
            resource_type="discussion",
            resource_id=str(discussion["id"]),
            metadata={"book_id": book_id, "chapter_id": chapter_id, "title": title},
        )

        # Metrics
        self.metrics.track_user_activity("create_discussion", "registered")

        return discussion

    @CodeProfiler.profile_time()
    @cached(ttl=3600, namespace="discussions", tags=["discussion_details"])
    async def get_discussion(self, discussion_id: int) -> Dict[str, Any]:
        """
        Lấy thông tin thảo luận theo ID.

        Args:
            discussion_id: ID của thảo luận

        Returns:
            Thông tin thảo luận

        Raises:
            NotFoundException: Nếu không tìm thấy thảo luận
        """
        # Lấy discussion
        discussion = await self.discussion_repo.get(discussion_id)
        if not discussion:
            raise NotFoundException(f"Không tìm thấy thảo luận với ID {discussion_id}")

        # Lấy thông tin người dùng
        user = await self.user_repo.get(discussion["user_id"])
        if user:
            discussion["user"] = {
                "id": user["id"],
                "username": user["username"],
                "avatar": user.get("avatar"),
            }

        # Lấy thông tin sách
        book = await self.book_repo.get(discussion["book_id"])
        if book:
            discussion["book"] = {
                "id": book["id"],
                "title": book["title"],
                "cover_image": book.get("cover_image"),
            }

        # Lấy thông tin chương nếu có
        if discussion.get("chapter_id"):
            chapter = await self.chapter_repo.get(discussion["chapter_id"])
            if chapter:
                discussion["chapter"] = {
                    "id": chapter["id"],
                    "title": chapter["title"],
                    "number": chapter.get("number"),
                }

        # Cập nhật số lượt xem
        await self.discussion_repo.increment_view_count(discussion_id)

        return discussion

    @CodeProfiler.profile_time(threshold=0.5)
    @invalidate_cache(namespace="discussions", tags=["discussion_details"])
    async def update_discussion(
        self, discussion_id: int, user_id: int, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Cập nhật thông tin thảo luận.

        Args:
            discussion_id: ID của thảo luận
            user_id: ID của người dùng (để kiểm tra quyền)
            data: Dữ liệu cập nhật

        Returns:
            Thông tin thảo luận đã cập nhật

        Raises:
            NotFoundException: Nếu không tìm thấy thảo luận
            ForbiddenException: Nếu user_id không phải chủ sở hữu
        """
        # Kiểm tra discussion tồn tại
        discussion = await self.discussion_repo.get(discussion_id)
        if not discussion:
            raise NotFoundException(f"Không tìm thấy thảo luận với ID {discussion_id}")

        # Kiểm tra quyền
        if discussion["user_id"] != user_id:
            # Kiểm tra xem user có phải là admin không
            try:
                is_admin = await check_permission(user_id, "manage_discussions")
                if not is_admin:
                    raise ForbiddenException(
                        "Bạn không có quyền cập nhật thảo luận này"
                    )
            except:
                raise ForbiddenException("Bạn không có quyền cập nhật thảo luận này")

        # Lưu trạng thái cũ
        before_state = dict(discussion)

        # Làm sạch dữ liệu
        if "title" in data and data["title"]:
            data["title"] = sanitize_html(data["title"])

        if "content" in data and data["content"]:
            data["content"] = sanitize_html(data["content"])

        # Giới hạn các trường có thể cập nhật
        allowed_fields = ["title", "content", "is_spoiler", "status"]
        update_data = {k: v for k, v in data.items() if k in allowed_fields}

        # Cập nhật
        updated_discussion = await self.discussion_repo.update(
            discussion_id, update_data
        )

        # Ghi log hoạt động
        await self.user_log_service.log_activity(
            self.db,
            user_id=user_id,
            activity_type="UPDATE_DISCUSSION",
            resource_type="discussion",
            resource_id=str(discussion_id),
            before_state=before_state,
            after_state=dict(updated_discussion),
            metadata={
                "book_id": discussion["book_id"],
                "title": updated_discussion["title"],
            },
        )

        # Metrics
        self.metrics.track_user_activity("update_discussion", "registered")

        return updated_discussion

    @CodeProfiler.profile_time()
    @invalidate_cache(
        namespace="discussions",
        tags=["discussion_details", "book_discussions", "chapter_discussions"],
    )
    async def delete_discussion(
        self, discussion_id: int, user_id: int
    ) -> Dict[str, Any]:
        """
        Xóa thảo luận.

        Args:
            discussion_id: ID của thảo luận
            user_id: ID của người dùng (để kiểm tra quyền)

        Returns:
            Thông báo kết quả

        Raises:
            NotFoundException: Nếu không tìm thấy thảo luận
            ForbiddenException: Nếu user_id không phải chủ sở hữu
        """
        # Kiểm tra discussion tồn tại
        discussion = await self.discussion_repo.get(discussion_id)
        if not discussion:
            raise NotFoundException(f"Không tìm thấy thảo luận với ID {discussion_id}")

        # Kiểm tra quyền
        if discussion["user_id"] != user_id:
            # Kiểm tra xem user có phải là admin không
            try:
                is_admin = await check_permission(user_id, "manage_discussions")
                if not is_admin:
                    raise ForbiddenException("Bạn không có quyền xóa thảo luận này")
            except:
                raise ForbiddenException("Bạn không có quyền xóa thảo luận này")

        # Xóa discussion (có thể chỉ cập nhật trạng thái thành "deleted")
        # result = await self.discussion_repo.delete(discussion_id)
        result = await self.discussion_repo.update(discussion_id, {"status": "deleted"})

        # Ghi log hoạt động
        await self.user_log_service.log_activity(
            self.db,
            user_id=user_id,
            activity_type="DELETE_DISCUSSION",
            resource_type="discussion",
            resource_id=str(discussion_id),
            before_state=dict(discussion),
            metadata={"book_id": discussion["book_id"], "title": discussion["title"]},
        )

        # Metrics
        self.metrics.track_user_activity("delete_discussion", "registered")

        return {"success": True, "message": "Thảo luận đã được xóa"}

    @CodeProfiler.profile_time()
    @cached(ttl=1800, namespace="discussions", tags=["book_discussions"])
    async def list_book_discussions(
        self, book_id: int, skip: int = 0, limit: int = 20, only_pinned: bool = False
    ) -> Dict[str, Any]:
        """
        Lấy danh sách thảo luận của một sách.

        Args:
            book_id: ID của sách
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa trả về
            only_pinned: Chỉ lấy các thảo luận được ghim

        Returns:
            Danh sách thảo luận và thông tin phân trang
        """
        # Kiểm tra sách tồn tại
        book = await self.book_repo.get(book_id)
        if not book:
            raise NotFoundException(f"Không tìm thấy sách với ID {book_id}")

        # Lấy danh sách discussion
        filters = {"book_id": book_id, "status": "active"}

        if only_pinned:
            filters["is_pinned"] = True

        discussions = await self.discussion_repo.get_multi(
            skip=skip, limit=limit, **filters
        )

        # Lấy tổng số lượng
        total = await self.discussion_repo.count(**filters)

        # Lấy thông tin người dùng cho mỗi discussion
        for discussion in discussions:
            user = await self.user_repo.get(discussion["user_id"])
            if user:
                discussion["user"] = {
                    "id": user["id"],
                    "username": user["username"],
                    "avatar": user.get("avatar"),
                }

        return {
            "items": discussions,
            "total": total,
            "book": {"id": book["id"], "title": book["title"]},
            "skip": skip,
            "limit": limit,
        }

    @CodeProfiler.profile_time()
    @cached(ttl=1800, namespace="discussions", tags=["chapter_discussions"])
    async def list_chapter_discussions(
        self, chapter_id: int, skip: int = 0, limit: int = 20
    ) -> Dict[str, Any]:
        """
        Lấy danh sách thảo luận của một chương.

        Args:
            chapter_id: ID của chương
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa trả về

        Returns:
            Danh sách thảo luận và thông tin phân trang
        """
        # Kiểm tra chương tồn tại
        chapter = await self.chapter_repo.get(chapter_id)
        if not chapter:
            raise NotFoundException(f"Không tìm thấy chương với ID {chapter_id}")

        # Lấy danh sách discussion
        filters = {"chapter_id": chapter_id, "status": "active"}

        discussions = await self.discussion_repo.get_multi(
            skip=skip, limit=limit, **filters
        )

        # Lấy tổng số lượng
        total = await self.discussion_repo.count(**filters)

        # Lấy thông tin người dùng cho mỗi discussion
        for discussion in discussions:
            user = await self.user_repo.get(discussion["user_id"])
            if user:
                discussion["user"] = {
                    "id": user["id"],
                    "username": user["username"],
                    "avatar": user.get("avatar"),
                }

        # Lấy thông tin sách
        book = await self.book_repo.get(chapter["book_id"])

        return {
            "items": discussions,
            "total": total,
            "chapter": {
                "id": chapter["id"],
                "title": chapter["title"],
                "number": chapter.get("number"),
            },
            "book": {"id": book["id"], "title": book["title"]} if book else None,
            "skip": skip,
            "limit": limit,
        }

    @CodeProfiler.profile_time()
    @cached(ttl=1800, namespace="discussions", tags=["user_discussions"])
    async def list_user_discussions(
        self, user_id: int, skip: int = 0, limit: int = 20
    ) -> Dict[str, Any]:
        """
        Lấy danh sách thảo luận của một người dùng.

        Args:
            user_id: ID của người dùng
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa trả về

        Returns:
            Danh sách thảo luận và thông tin phân trang
        """
        # Kiểm tra user tồn tại
        user = await self.user_repo.get(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng với ID {user_id}")

        # Lấy danh sách discussion
        filters = {"user_id": user_id, "status": "active"}

        discussions = await self.discussion_repo.get_multi(
            skip=skip, limit=limit, **filters
        )

        # Lấy tổng số lượng
        total = await self.discussion_repo.count(**filters)

        # Lấy thông tin sách cho mỗi discussion
        for discussion in discussions:
            book = await self.book_repo.get(discussion["book_id"])
            if book:
                discussion["book"] = {
                    "id": book["id"],
                    "title": book["title"],
                    "cover_image": book.get("cover_image"),
                }

            if discussion.get("chapter_id"):
                chapter = await self.chapter_repo.get(discussion["chapter_id"])
                if chapter:
                    discussion["chapter"] = {
                        "id": chapter["id"],
                        "title": chapter["title"],
                        "number": chapter.get("number"),
                    }

        return {
            "items": discussions,
            "total": total,
            "user": {
                "id": user["id"],
                "username": user["username"],
                "avatar": user.get("avatar"),
            },
            "skip": skip,
            "limit": limit,
        }

    @CodeProfiler.profile_time()
    @invalidate_cache(
        namespace="discussions", tags=["book_discussions", "discussion_details"]
    )
    async def pin_discussion(
        self, discussion_id: int, is_pinned: bool = True, admin_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Ghim hoặc bỏ ghim thảo luận.

        Args:
            discussion_id: ID của thảo luận
            is_pinned: Trạng thái ghim
            admin_id: ID của admin thực hiện hành động (tùy chọn)

        Returns:
            Thông tin thảo luận đã cập nhật

        Raises:
            NotFoundException: Nếu không tìm thấy thảo luận
        """
        # Kiểm tra discussion tồn tại
        discussion = await self.discussion_repo.get(discussion_id)
        if not discussion:
            raise NotFoundException(f"Không tìm thấy thảo luận với ID {discussion_id}")

        # Kiểm tra quyền
        if admin_id:
            try:
                is_admin = await check_permission(admin_id, "manage_discussions")
                if not is_admin:
                    raise ForbiddenException(
                        "Bạn không có quyền ghim/bỏ ghim thảo luận"
                    )
            except:
                raise ForbiddenException("Bạn không có quyền ghim/bỏ ghim thảo luận")

        # Cập nhật is_pinned
        update_data = {"is_pinned": is_pinned}
        updated_discussion = await self.discussion_repo.update(
            discussion_id, update_data
        )

        # Ghi log hoạt động
        if admin_id:
            from app.logs_manager.services.admin_activity_log_service import (
                AdminActivityLogService,
            )

            admin_log_service = AdminActivityLogService()

            await admin_log_service.log_activity(
                self.db,
                admin_id=admin_id,
                activity_type="PIN_DISCUSSION" if is_pinned else "UNPIN_DISCUSSION",
                action="pin_discussion" if is_pinned else "unpin_discussion",
                resource_type="discussion",
                resource_id=str(discussion_id),
                details={
                    "book_id": discussion["book_id"],
                    "title": discussion["title"],
                },
            )

        # Metrics
        self.metrics.track_user_activity(
            "pin_discussion" if is_pinned else "unpin_discussion", "admin"
        )

        return updated_discussion

    @CodeProfiler.profile_time()
    @invalidate_cache(namespace="discussions", tags=["discussion_details"])
    async def vote_discussion(
        self, discussion_id: int, user_id: int, is_upvote: bool
    ) -> Dict[str, Any]:
        """
        Bỏ phiếu cho thảo luận.

        Args:
            discussion_id: ID của thảo luận
            user_id: ID của người dùng
            is_upvote: True nếu upvote, False nếu downvote

        Returns:
            Thông tin thảo luận sau khi cập nhật

        Raises:
            NotFoundException: Nếu không tìm thấy thảo luận
        """
        # Kiểm tra discussion tồn tại
        discussion = await self.discussion_repo.get(discussion_id)
        if not discussion:
            raise NotFoundException(f"Không tìm thấy thảo luận với ID {discussion_id}")

        # Kiểm tra user tồn tại
        user = await self.user_repo.get(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng với ID {user_id}")

        # Kiểm tra xem user đã vote trước đó chưa
        existing_vote = await self.discussion_repo.get_user_vote(discussion_id, user_id)

        # Xử lý vote
        if existing_vote:
            # Nếu vote giống nhau -> hủy vote
            if existing_vote["is_upvote"] == is_upvote:
                await self.discussion_repo.remove_vote(discussion_id, user_id)

                # Cập nhật vote_count
                if is_upvote:
                    await self.discussion_repo.update(
                        discussion_id, {"vote_count": discussion["vote_count"] - 1}
                    )
                else:
                    await self.discussion_repo.update(
                        discussion_id, {"vote_count": discussion["vote_count"] + 1}
                    )

                return {
                    "success": True,
                    "message": "Đã hủy đánh giá",
                    "discussion_id": discussion_id,
                    "vote_removed": True,
                    "vote_count": (
                        discussion["vote_count"] - 1
                        if is_upvote
                        else discussion["vote_count"] + 1
                    ),
                }
            else:
                # Nếu vote khác nhau -> cập nhật vote
                await self.discussion_repo.update_vote(
                    discussion_id, user_id, is_upvote
                )

                # Cập nhật vote_count
                if is_upvote:
                    await self.discussion_repo.update(
                        discussion_id, {"vote_count": discussion["vote_count"] + 2}
                    )
                else:
                    await self.discussion_repo.update(
                        discussion_id, {"vote_count": discussion["vote_count"] - 2}
                    )

                return {
                    "success": True,
                    "message": "Đã cập nhật đánh giá",
                    "discussion_id": discussion_id,
                    "is_upvote": is_upvote,
                    "vote_count": (
                        discussion["vote_count"] + 2
                        if is_upvote
                        else discussion["vote_count"] - 2
                    ),
                }
        else:
            # Chưa vote -> tạo vote mới
            await self.discussion_repo.add_vote(discussion_id, user_id, is_upvote)

            # Cập nhật vote_count
            if is_upvote:
                await self.discussion_repo.update(
                    discussion_id, {"vote_count": discussion["vote_count"] + 1}
                )
            else:
                await self.discussion_repo.update(
                    discussion_id, {"vote_count": discussion["vote_count"] - 1}
                )

            return {
                "success": True,
                "message": "Đã thêm đánh giá",
                "discussion_id": discussion_id,
                "is_upvote": is_upvote,
                "vote_count": (
                    discussion["vote_count"] + 1
                    if is_upvote
                    else discussion["vote_count"] - 1
                ),
            }

    @CodeProfiler.profile_time()
    @cached(ttl=600, namespace="discussions", tags=["trending_discussions"])
    async def get_trending_discussions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Lấy danh sách thảo luận xu hướng.

        Args:
            limit: Số lượng bản ghi tối đa trả về

        Returns:
            Danh sách thảo luận xu hướng
        """
        # Lấy danh sách discussion
        trending_discussions = await self.discussion_repo.get_trending(limit)

        # Lấy thông tin người dùng và sách
        for discussion in trending_discussions:
            # Thông tin người dùng
            user = await self.user_repo.get(discussion["user_id"])
            if user:
                discussion["user"] = {
                    "id": user["id"],
                    "username": user["username"],
                    "avatar": user.get("avatar"),
                }

            # Thông tin sách
            book = await self.book_repo.get(discussion["book_id"])
            if book:
                discussion["book"] = {
                    "id": book["id"],
                    "title": book["title"],
                    "cover_image": book.get("cover_image"),
                }

            # Thông tin chương nếu có
            if discussion.get("chapter_id"):
                chapter = await self.chapter_repo.get(discussion["chapter_id"])
                if chapter:
                    discussion["chapter"] = {
                        "id": chapter["id"],
                        "title": chapter["title"],
                        "number": chapter.get("number"),
                    }

        return trending_discussions
