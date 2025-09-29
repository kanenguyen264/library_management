from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime
import logging

from app.user_site.models.discussion import Discussion, DiscussionComment
from app.user_site.repositories.discussion_repo import DiscussionRepository
from app.user_site.repositories.user_repo import UserRepository
from app.user_site.repositories.book_repo import BookRepository
from app.user_site.repositories.chapter_repo import ChapterRepository
from app.core.exceptions import NotFoundException, ForbiddenException
from app.cache.decorators import cached, invalidate_cache
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate

# Logger cho discussion service
logger = logging.getLogger(__name__)


async def get_all_discussions(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    book_id: Optional[int] = None,
    chapter_id: Optional[int] = None,
    user_id: Optional[int] = None,
    is_pinned: Optional[bool] = None,
    sort_by: str = "created_at",
    sort_desc: bool = True,
    admin_id: Optional[int] = None,
) -> List[Discussion]:
    """
    Lấy danh sách thảo luận với bộ lọc.

    Args:
        db: Database session
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về
        book_id: Lọc theo ID sách
        chapter_id: Lọc theo ID chương
        user_id: Lọc theo ID người dùng
        is_pinned: Lọc theo trạng thái ghim
        sort_by: Sắp xếp theo trường
        sort_desc: Sắp xếp giảm dần
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách thảo luận
    """
    try:
        repo = DiscussionRepository(db)
        discussions = await repo.list_discussions(
            skip=skip,
            limit=limit,
            book_id=book_id,
            chapter_id=chapter_id,
            user_id=user_id,
            is_pinned=is_pinned,
            sort_by=sort_by,
            sort_desc=sort_desc,
        )

        # Log admin activity
        if admin_id:
            try:
                activity_description = "Viewed discussions list"
                if book_id:
                    activity_description = f"Viewed discussions for book {book_id}"
                elif user_id:
                    activity_description = f"Viewed discussions by user {user_id}"

                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="DISCUSSIONS",
                        entity_id=0,
                        description=activity_description,
                        metadata={
                            "skip": skip,
                            "limit": limit,
                            "book_id": book_id,
                            "chapter_id": chapter_id,
                            "user_id": user_id,
                            "is_pinned": is_pinned,
                            "sort_by": sort_by,
                            "sort_desc": sort_desc,
                            "results_count": len(discussions),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return discussions
    except Exception as e:
        logger.error(f"Error retrieving discussions: {str(e)}")
        raise


async def count_discussions(
    db: Session,
    book_id: Optional[int] = None,
    chapter_id: Optional[int] = None,
    user_id: Optional[int] = None,
    is_pinned: Optional[bool] = None,
) -> int:
    """
    Đếm số lượng thảo luận.

    Args:
        db: Database session
        book_id: Lọc theo ID sách
        chapter_id: Lọc theo ID chương
        user_id: Lọc theo ID người dùng
        is_pinned: Lọc theo trạng thái ghim

    Returns:
        Số lượng thảo luận
    """
    try:
        repo = DiscussionRepository(db)
        return await repo.count_discussions(
            book_id=book_id, chapter_id=chapter_id, user_id=user_id
        )
    except Exception as e:
        logger.error(f"Error counting discussions: {str(e)}")
        raise


@cached(key_prefix="admin_discussion", ttl=300)
async def get_discussion_by_id(
    db: Session,
    discussion_id: int,
    with_relations: bool = False,
    admin_id: Optional[int] = None,
) -> Discussion:
    """
    Lấy thông tin thảo luận theo ID.

    Args:
        db: Database session
        discussion_id: ID của thảo luận
        with_relations: Có load các mối quan hệ không
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin thảo luận

    Raises:
        NotFoundException: Nếu không tìm thấy thảo luận
    """
    try:
        repo = DiscussionRepository(db)
        discussion = await repo.get_by_id(discussion_id, with_relations)

        if not discussion:
            logger.warning(f"Discussion with ID {discussion_id} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy thảo luận với ID {discussion_id}"
            )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="DISCUSSION",
                        entity_id=discussion_id,
                        description=f"Viewed discussion details for ID {discussion_id}",
                        metadata={
                            "title": (
                                discussion.title
                                if hasattr(discussion, "title")
                                else None
                            ),
                            "user_id": (
                                discussion.user_id
                                if hasattr(discussion, "user_id")
                                else None
                            ),
                            "book_id": (
                                discussion.book_id
                                if hasattr(discussion, "book_id")
                                else None
                            ),
                            "chapter_id": (
                                discussion.chapter_id
                                if hasattr(discussion, "chapter_id")
                                else None
                            ),
                            "upvotes": (
                                discussion.upvotes
                                if hasattr(discussion, "upvotes")
                                else 0
                            ),
                            "downvotes": (
                                discussion.downvotes
                                if hasattr(discussion, "downvotes")
                                else 0
                            ),
                            "is_pinned": (
                                discussion.is_pinned
                                if hasattr(discussion, "is_pinned")
                                else False
                            ),
                            "with_relations": with_relations,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return discussion
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving discussion: {str(e)}")
        raise


async def create_discussion(
    db: Session, discussion_data: Dict[str, Any], admin_id: Optional[int] = None
) -> Discussion:
    """
    Tạo thảo luận mới.

    Args:
        db: Database session
        discussion_data: Dữ liệu thảo luận
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin thảo luận đã tạo

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng, sách hoặc chương
    """
    try:
        # Kiểm tra người dùng tồn tại
        user = None
        if "user_id" in discussion_data:
            user_repo = UserRepository(db)
            user = await user_repo.get_by_id(discussion_data["user_id"])

            if not user:
                logger.warning(f"User with ID {discussion_data['user_id']} not found")
                raise NotFoundException(
                    detail=f"Không tìm thấy người dùng với ID {discussion_data['user_id']}"
                )

        # Kiểm tra sách tồn tại
        book = None
        if "book_id" in discussion_data:
            book_repo = BookRepository(db)
            book = await book_repo.get_by_id(discussion_data["book_id"])

            if not book:
                logger.warning(f"Book with ID {discussion_data['book_id']} not found")
                raise NotFoundException(
                    detail=f"Không tìm thấy sách với ID {discussion_data['book_id']}"
                )

        # Kiểm tra chương tồn tại
        chapter = None
        if (
            "chapter_id" in discussion_data
            and discussion_data["chapter_id"] is not None
        ):
            chapter_repo = ChapterRepository(db)
            chapter = await chapter_repo.get_by_id(discussion_data["chapter_id"])

            if not chapter:
                logger.warning(
                    f"Chapter with ID {discussion_data['chapter_id']} not found"
                )
                raise NotFoundException(
                    detail=f"Không tìm thấy chương với ID {discussion_data['chapter_id']}"
                )

        # Tạo thảo luận mới
        repo = DiscussionRepository(db)
        discussion = await repo.create(discussion_data)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="CREATE",
                        entity_type="DISCUSSION",
                        entity_id=discussion.id,
                        description=f"Created new discussion: {discussion.title if hasattr(discussion, 'title') else 'No title'}",
                        metadata={
                            "title": discussion_data.get("title"),
                            "content": discussion_data.get("content"),
                            "user_id": discussion_data.get("user_id"),
                            "username": (
                                user.username
                                if user and hasattr(user, "username")
                                else None
                            ),
                            "book_id": discussion_data.get("book_id"),
                            "book_title": (
                                book.title if book and hasattr(book, "title") else None
                            ),
                            "chapter_id": discussion_data.get("chapter_id"),
                            "chapter_title": (
                                chapter.title
                                if chapter and hasattr(chapter, "title")
                                else None
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Created new discussion with ID {discussion.id}")
        return discussion
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error creating discussion: {str(e)}")
        raise


async def update_discussion(
    db: Session,
    discussion_id: int,
    discussion_data: Dict[str, Any],
    admin_id: Optional[int] = None,
) -> Discussion:
    """
    Cập nhật thông tin thảo luận.

    Args:
        db: Database session
        discussion_id: ID của thảo luận
        discussion_data: Dữ liệu cập nhật
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin thảo luận đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy thảo luận
    """
    try:
        # Kiểm tra thảo luận tồn tại
        discussion = await get_discussion_by_id(db, discussion_id)

        # Cập nhật thảo luận
        repo = DiscussionRepository(db)
        updated_discussion = await repo.update(discussion_id, discussion_data)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="DISCUSSION",
                        entity_id=discussion_id,
                        description=f"Updated discussion: {updated_discussion.title if hasattr(updated_discussion, 'title') else 'No title'}",
                        metadata={
                            "user_id": (
                                discussion.user_id
                                if hasattr(discussion, "user_id")
                                else None
                            ),
                            "book_id": (
                                discussion.book_id
                                if hasattr(discussion, "book_id")
                                else None
                            ),
                            "updates": discussion_data,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        # Remove cache
        invalidate_cache(f"admin_discussion:{discussion_id}")

        logger.info(f"Updated discussion with ID {discussion_id}")
        return updated_discussion
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error updating discussion: {str(e)}")
        raise


async def delete_discussion(
    db: Session, discussion_id: int, admin_id: Optional[int] = None
) -> None:
    """
    Xóa thảo luận.

    Args:
        db: Database session
        discussion_id: ID của thảo luận
        admin_id: ID của admin thực hiện hành động

    Raises:
        NotFoundException: Nếu không tìm thấy thảo luận
    """
    try:
        # Kiểm tra thảo luận tồn tại
        discussion = await get_discussion_by_id(db, discussion_id)

        # Log admin activity before deletion
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="DELETE",
                        entity_type="DISCUSSION",
                        entity_id=discussion_id,
                        description=f"Deleted discussion: {discussion.title if hasattr(discussion, 'title') else 'No title'}",
                        metadata={
                            "title": (
                                discussion.title
                                if hasattr(discussion, "title")
                                else None
                            ),
                            "user_id": (
                                discussion.user_id
                                if hasattr(discussion, "user_id")
                                else None
                            ),
                            "book_id": (
                                discussion.book_id
                                if hasattr(discussion, "book_id")
                                else None
                            ),
                            "chapter_id": (
                                discussion.chapter_id
                                if hasattr(discussion, "chapter_id")
                                else None
                            ),
                            "upvotes": (
                                discussion.upvotes
                                if hasattr(discussion, "upvotes")
                                else 0
                            ),
                            "downvotes": (
                                discussion.downvotes
                                if hasattr(discussion, "downvotes")
                                else 0
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        # Xóa thảo luận
        repo = DiscussionRepository(db)
        await repo.delete(discussion_id)

        # Remove cache
        invalidate_cache(f"admin_discussion:{discussion_id}")

        logger.info(f"Deleted discussion with ID {discussion_id}")
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error deleting discussion: {str(e)}")
        raise


async def update_discussion_votes(
    db: Session, discussion_id: int, upvote: bool = True, increment: bool = True
) -> Discussion:
    """
    Cập nhật số lượt vote cho thảo luận.

    Args:
        db: Database session
        discussion_id: ID của thảo luận
        upvote: True nếu là upvote, False nếu là downvote
        increment: True nếu tăng, False nếu giảm

    Returns:
        Thông tin thảo luận đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy thảo luận
    """
    try:
        # Kiểm tra thảo luận tồn tại
        await get_discussion_by_id(db, discussion_id)

        # Cập nhật votes
        repo = DiscussionRepository(db)
        discussion = await repo.update_votes(discussion_id, upvote, increment)

        # Xóa cache
        invalidate_cache(f"admin_discussion:{discussion_id}")

        logger.info(f"Updated votes for discussion with ID {discussion_id}")
        return discussion
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error updating discussion votes: {str(e)}")
        raise


async def pin_discussion(
    db: Session, discussion_id: int, admin_id: Optional[int] = None
) -> Discussion:
    """
    Ghim thảo luận.

    Args:
        db: Database session
        discussion_id: ID của thảo luận
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin thảo luận đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy thảo luận
    """
    try:
        # Kiểm tra thảo luận tồn tại
        discussion = await get_discussion_by_id(db, discussion_id)

        # Cập nhật trạng thái ghim
        repo = DiscussionRepository(db)
        updated_discussion = await repo.update(discussion_id, {"is_pinned": True})

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="PIN",
                        entity_type="DISCUSSION",
                        entity_id=discussion_id,
                        description=f"Pinned discussion: {discussion.title if hasattr(discussion, 'title') else 'No title'}",
                        metadata={
                            "title": (
                                discussion.title
                                if hasattr(discussion, "title")
                                else None
                            ),
                            "user_id": (
                                discussion.user_id
                                if hasattr(discussion, "user_id")
                                else None
                            ),
                            "book_id": (
                                discussion.book_id
                                if hasattr(discussion, "book_id")
                                else None
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        # Remove cache
        invalidate_cache(f"admin_discussion:{discussion_id}")

        logger.info(f"Pinned discussion with ID {discussion_id}")
        return updated_discussion
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error pinning discussion: {str(e)}")
        raise


async def unpin_discussion(
    db: Session, discussion_id: int, admin_id: Optional[int] = None
) -> Discussion:
    """
    Bỏ ghim thảo luận.

    Args:
        db: Database session
        discussion_id: ID của thảo luận
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin thảo luận đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy thảo luận
    """
    try:
        # Kiểm tra thảo luận tồn tại
        discussion = await get_discussion_by_id(db, discussion_id)

        # Cập nhật trạng thái ghim
        repo = DiscussionRepository(db)
        updated_discussion = await repo.update(discussion_id, {"is_pinned": False})

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UNPIN",
                        entity_type="DISCUSSION",
                        entity_id=discussion_id,
                        description=f"Unpinned discussion: {discussion.title if hasattr(discussion, 'title') else 'No title'}",
                        metadata={
                            "title": (
                                discussion.title
                                if hasattr(discussion, "title")
                                else None
                            ),
                            "user_id": (
                                discussion.user_id
                                if hasattr(discussion, "user_id")
                                else None
                            ),
                            "book_id": (
                                discussion.book_id
                                if hasattr(discussion, "book_id")
                                else None
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        # Remove cache
        invalidate_cache(f"admin_discussion:{discussion_id}")

        logger.info(f"Unpinned discussion with ID {discussion_id}")
        return updated_discussion
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error unpinning discussion: {str(e)}")
        raise


# Phần bổ sung cho DiscussionComment


async def get_comments(
    db: Session,
    discussion_id: int,
    parent_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 20,
    sort_by: str = "created_at",
    sort_desc: bool = True,
) -> List[DiscussionComment]:
    """
    Lấy danh sách bình luận cho một thảo luận.

    Args:
        db: Database session
        discussion_id: ID của thảo luận
        parent_id: ID của bình luận cha (None nếu lấy các bình luận gốc)
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về
        sort_by: Sắp xếp theo trường
        sort_desc: Sắp xếp giảm dần

    Returns:
        Danh sách bình luận
    """
    try:
        repo = DiscussionRepository(db)
        return await repo.list_comments(
            discussion_id=discussion_id,
            parent_id=parent_id,
            skip=skip,
            limit=limit,
            sort_by=sort_by,
            sort_desc=sort_desc,
        )
    except Exception as e:
        logger.error(f"Error retrieving comments: {str(e)}")
        raise


async def count_comments(
    db: Session, discussion_id: int, parent_id: Optional[int] = None
) -> int:
    """
    Đếm số lượng bình luận cho một thảo luận.

    Args:
        db: Database session
        discussion_id: ID của thảo luận
        parent_id: ID của bình luận cha (None nếu đếm các bình luận gốc)

    Returns:
        Số lượng bình luận
    """
    try:
        repo = DiscussionRepository(db)
        return await repo.count_comments(discussion_id, parent_id)
    except Exception as e:
        logger.error(f"Error counting comments: {str(e)}")
        raise


async def get_comment_by_id(
    db: Session, comment_id: int, with_relations: bool = False
) -> DiscussionComment:
    """
    Lấy thông tin bình luận theo ID.

    Args:
        db: Database session
        comment_id: ID của bình luận
        with_relations: Có load các mối quan hệ không

    Returns:
        Thông tin bình luận

    Raises:
        NotFoundException: Nếu không tìm thấy bình luận
    """
    try:
        repo = DiscussionRepository(db)
        comment = await repo.get_comment_by_id(comment_id, with_relations)

        if not comment:
            logger.warning(f"Comment with ID {comment_id} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy bình luận với ID {comment_id}"
            )

        return comment
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving comment: {str(e)}")
        raise


async def create_comment(
    db: Session, comment_data: Dict[str, Any]
) -> DiscussionComment:
    """
    Tạo bình luận mới.

    Args:
        db: Database session
        comment_data: Dữ liệu bình luận

    Returns:
        Thông tin bình luận đã tạo

    Raises:
        NotFoundException: Nếu không tìm thấy thảo luận, bình luận cha hoặc người dùng
    """
    try:
        # Kiểm tra người dùng tồn tại
        if "user_id" in comment_data:
            user_repo = UserRepository(db)
            user = await user_repo.get_by_id(comment_data["user_id"])

            if not user:
                logger.warning(f"User with ID {comment_data['user_id']} not found")
                raise NotFoundException(
                    detail=f"Không tìm thấy người dùng với ID {comment_data['user_id']}"
                )

        # Kiểm tra thảo luận tồn tại
        if "discussion_id" in comment_data:
            await get_discussion_by_id(db, comment_data["discussion_id"])

        # Kiểm tra bình luận cha tồn tại nếu có
        if "parent_id" in comment_data and comment_data["parent_id"]:
            await get_comment_by_id(db, comment_data["parent_id"])

        # Tạo bình luận mới
        repo = DiscussionRepository(db)
        comment = await repo.create_comment(comment_data)

        logger.info(f"Created new comment with ID {comment.id}")
        return comment
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error creating comment: {str(e)}")
        raise


async def update_comment(
    db: Session, comment_id: int, comment_data: Dict[str, Any]
) -> DiscussionComment:
    """
    Cập nhật thông tin bình luận.

    Args:
        db: Database session
        comment_id: ID của bình luận
        comment_data: Dữ liệu cập nhật

    Returns:
        Thông tin bình luận đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy bình luận
    """
    try:
        # Kiểm tra bình luận tồn tại
        await get_comment_by_id(db, comment_id)

        # Cập nhật bình luận
        repo = DiscussionRepository(db)
        comment = await repo.update_comment(comment_id, comment_data)

        logger.info(f"Updated comment with ID {comment_id}")
        return comment
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error updating comment: {str(e)}")
        raise


async def delete_comment(db: Session, comment_id: int) -> None:
    """
    Xóa bình luận.

    Args:
        db: Database session
        comment_id: ID của bình luận

    Raises:
        NotFoundException: Nếu không tìm thấy bình luận
    """
    try:
        # Kiểm tra bình luận tồn tại
        await get_comment_by_id(db, comment_id)

        # Xóa bình luận
        repo = DiscussionRepository(db)
        await repo.delete_comment(comment_id)

        logger.info(f"Deleted comment with ID {comment_id}")
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error deleting comment: {str(e)}")
        raise


async def update_comment_votes(
    db: Session, comment_id: int, upvote: bool = True, increment: bool = True
) -> DiscussionComment:
    """
    Cập nhật số lượt vote cho bình luận.

    Args:
        db: Database session
        comment_id: ID của bình luận
        upvote: True nếu là upvote, False nếu là downvote
        increment: True nếu tăng, False nếu giảm

    Returns:
        Thông tin bình luận đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy bình luận
    """
    try:
        # Kiểm tra bình luận tồn tại
        await get_comment_by_id(db, comment_id)

        # Cập nhật votes
        repo = DiscussionRepository(db)
        comment = await repo.update_comment_votes(comment_id, upvote, increment)

        logger.info(f"Updated votes for comment with ID {comment_id}")
        return comment
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error updating comment votes: {str(e)}")
        raise


@cached(key_prefix="admin_discussion_statistics", ttl=3600)
async def get_discussion_statistics(
    db: Session, admin_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Lấy thống kê về thảo luận.

    Args:
        db: Database session
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thống kê thảo luận
    """
    try:
        # Đây là code demo, cần bổ sung các phương thức hỗ trợ trong repository
        stats = {
            "total_discussions": 0,  # Cần bổ sung phương thức count_all
            "total_comments": 0,  # Cần bổ sung phương thức count_all_comments
            "pinned_discussions": 0,  # Cần bổ sung phương thức count_pinned
            "books_with_discussions": 0,  # Cần bổ sung phương thức count_books_with_discussions
            "most_discussed_books": [],  # Cần bổ sung phương thức get_most_discussed_books
            "most_active_users": [],  # Cần bổ sung phương thức get_most_active_users
        }

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="DISCUSSION_STATISTICS",
                        entity_id=0,
                        description="Viewed discussion statistics",
                        metadata=stats,
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return stats
    except Exception as e:
        logger.error(f"Error retrieving discussion statistics: {str(e)}")
        raise
