from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
import logging

from app.user_site.models.annotation import Annotation
from app.user_site.repositories.annotation_repo import AnnotationRepository
from app.user_site.repositories.user_repo import UserRepository
from app.user_site.repositories.book_repo import BookRepository
from app.user_site.repositories.chapter_repo import ChapterRepository
from app.core.exceptions import NotFoundException, ForbiddenException
from app.cache.decorators import cached, invalidate_cache
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate

# Logger cho annotation service
logger = logging.getLogger(__name__)


async def get_all_annotations(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    user_id: Optional[int] = None,
    book_id: Optional[int] = None,
    chapter_id: Optional[int] = None,
    only_public: Optional[bool] = None,
    admin_id: Optional[int] = None,
) -> List[Annotation]:
    """
    Lấy danh sách ghi chú với bộ lọc.

    Args:
        db: Database session
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về
        user_id: Lọc theo ID người dùng
        book_id: Lọc theo ID sách
        chapter_id: Lọc theo ID chương
        only_public: Chỉ lấy ghi chú công khai
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách ghi chú
    """
    try:
        repo = AnnotationRepository(db)

        annotations = []
        if user_id:
            annotations = await repo.list_by_user(
                user_id,
                book_id=book_id,
                chapter_id=chapter_id,
                only_public=only_public if only_public is not None else False,
                skip=skip,
                limit=limit,
            )
        elif book_id and only_public:
            annotations = await repo.list_public_by_book(
                book_id=book_id, chapter_id=chapter_id, skip=skip, limit=limit
            )
        else:
            logger.warning("Yêu cầu lấy tất cả ghi chú không được hỗ trợ")

        # Log admin activity
        if admin_id:
            try:
                activity_description = "Viewed annotations"
                if user_id:
                    activity_description = f"Viewed annotations for user {user_id}"
                elif book_id:
                    activity_description = (
                        f"Viewed public annotations for book {book_id}"
                    )

                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="ANNOTATIONS",
                        entity_id=0,
                        description=activity_description,
                        metadata={
                            "skip": skip,
                            "limit": limit,
                            "user_id": user_id,
                            "book_id": book_id,
                            "chapter_id": chapter_id,
                            "only_public": only_public,
                            "results_count": len(annotations),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return annotations
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách ghi chú: {str(e)}")
        raise


async def count_annotations(
    db: Session,
    user_id: Optional[int] = None,
    book_id: Optional[int] = None,
    chapter_id: Optional[int] = None,
) -> int:
    """
    Đếm số lượng ghi chú.

    Args:
        db: Database session
        user_id: Lọc theo ID người dùng
        book_id: Lọc theo ID sách
        chapter_id: Lọc theo ID chương

    Returns:
        Số lượng ghi chú
    """
    try:
        repo = AnnotationRepository(db)

        if user_id:
            return await repo.count_by_user(user_id, book_id, chapter_id)
        else:
            logger.warning("Yêu cầu đếm tất cả ghi chú không được hỗ trợ")
            return 0
    except Exception as e:
        logger.error(f"Lỗi khi đếm ghi chú: {str(e)}")
        raise


@cached(key_prefix="admin_annotation", ttl=300)
async def get_annotation_by_id(
    db: Session,
    annotation_id: int,
    with_relations: bool = False,
    admin_id: Optional[int] = None,
) -> Annotation:
    """
    Lấy thông tin ghi chú theo ID.

    Args:
        db: Database session
        annotation_id: ID của ghi chú
        with_relations: Có load các mối quan hệ không
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin ghi chú

    Raises:
        NotFoundException: Nếu không tìm thấy ghi chú
    """
    try:
        repo = AnnotationRepository(db)
        annotation = await repo.get_by_id(annotation_id, with_relations)

        if not annotation:
            logger.warning(f"Không tìm thấy ghi chú với ID {annotation_id}")
            raise NotFoundException(
                detail=f"Không tìm thấy ghi chú với ID {annotation_id}"
            )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="ANNOTATION",
                        entity_id=annotation_id,
                        description=f"Viewed annotation details for ID {annotation_id}",
                        metadata={
                            "user_id": (
                                annotation.user_id
                                if hasattr(annotation, "user_id")
                                else None
                            ),
                            "book_id": (
                                annotation.book_id
                                if hasattr(annotation, "book_id")
                                else None
                            ),
                            "chapter_id": (
                                annotation.chapter_id
                                if hasattr(annotation, "chapter_id")
                                else None
                            ),
                            "content": (
                                annotation.content
                                if hasattr(annotation, "content")
                                else None
                            ),
                            "is_public": (
                                annotation.is_public
                                if hasattr(annotation, "is_public")
                                else None
                            ),
                            "with_relations": with_relations,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return annotation
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin ghi chú: {str(e)}")
        raise


async def create_annotation(
    db: Session, annotation_data: Dict[str, Any], admin_id: Optional[int] = None
) -> Annotation:
    """
    Tạo ghi chú mới.

    Args:
        db: Database session
        annotation_data: Dữ liệu ghi chú
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin ghi chú đã tạo

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng, sách hoặc chương
    """
    try:
        # Kiểm tra người dùng tồn tại
        user = None
        if "user_id" in annotation_data:
            user_repo = UserRepository(db)
            user = await user_repo.get_by_id(annotation_data["user_id"])

            if not user:
                logger.warning(
                    f"Không tìm thấy người dùng với ID {annotation_data['user_id']}"
                )
                raise NotFoundException(
                    detail=f"Không tìm thấy người dùng với ID {annotation_data['user_id']}"
                )

        # Kiểm tra sách tồn tại
        book = None
        if "book_id" in annotation_data:
            book_repo = BookRepository(db)
            book = await book_repo.get_by_id(annotation_data["book_id"])

            if not book:
                logger.warning(
                    f"Không tìm thấy sách với ID {annotation_data['book_id']}"
                )
                raise NotFoundException(
                    detail=f"Không tìm thấy sách với ID {annotation_data['book_id']}"
                )

        # Kiểm tra chương tồn tại
        chapter = None
        if (
            "chapter_id" in annotation_data
            and annotation_data["chapter_id"] is not None
        ):
            chapter_repo = ChapterRepository(db)
            chapter = await chapter_repo.get_by_id(annotation_data["chapter_id"])

            if not chapter:
                logger.warning(
                    f"Không tìm thấy chương với ID {annotation_data['chapter_id']}"
                )
                raise NotFoundException(
                    detail=f"Không tìm thấy chương với ID {annotation_data['chapter_id']}"
                )

        # Tạo ghi chú mới
        repo = AnnotationRepository(db)
        annotation = await repo.create(annotation_data)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="CREATE",
                        entity_type="ANNOTATION",
                        entity_id=annotation.id,
                        description=f"Created new annotation for {'user ' + str(annotation_data.get('user_id')) if annotation_data.get('user_id') else 'book ' + str(annotation_data.get('book_id'))}",
                        metadata={
                            "user_id": annotation_data.get("user_id"),
                            "username": (
                                user.username
                                if user and hasattr(user, "username")
                                else None
                            ),
                            "book_id": annotation_data.get("book_id"),
                            "book_title": (
                                book.title if book and hasattr(book, "title") else None
                            ),
                            "chapter_id": annotation_data.get("chapter_id"),
                            "chapter_title": (
                                chapter.title
                                if chapter and hasattr(chapter, "title")
                                else None
                            ),
                            "content": annotation_data.get("content"),
                            "is_public": annotation_data.get("is_public", False),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Đã tạo ghi chú mới với ID {annotation.id}")
        return annotation
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi tạo ghi chú: {str(e)}")
        raise


async def update_annotation(
    db: Session,
    annotation_id: int,
    annotation_data: Dict[str, Any],
    admin_id: Optional[int] = None,
) -> Annotation:
    """
    Cập nhật thông tin ghi chú.

    Args:
        db: Database session
        annotation_id: ID của ghi chú
        annotation_data: Dữ liệu cập nhật
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin ghi chú đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy ghi chú
    """
    try:
        # Kiểm tra ghi chú tồn tại
        annotation = await get_annotation_by_id(db, annotation_id)

        # Cập nhật ghi chú
        repo = AnnotationRepository(db)
        updated_annotation = await repo.update(annotation_id, annotation_data)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="ANNOTATION",
                        entity_id=annotation_id,
                        description=f"Updated annotation for user {annotation.user_id}",
                        metadata={
                            "user_id": (
                                annotation.user_id
                                if hasattr(annotation, "user_id")
                                else None
                            ),
                            "book_id": (
                                annotation.book_id
                                if hasattr(annotation, "book_id")
                                else None
                            ),
                            "chapter_id": (
                                annotation.chapter_id
                                if hasattr(annotation, "chapter_id")
                                else None
                            ),
                            "updates": annotation_data,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        # Remove cache
        invalidate_cache(f"admin_annotation:{annotation_id}")
        if hasattr(annotation, "user_id") and annotation.user_id:
            invalidate_cache(f"admin_user_annotations:{annotation.user_id}")
        if hasattr(annotation, "book_id") and annotation.book_id:
            invalidate_cache(f"admin_book_public_annotations:{annotation.book_id}")

        logger.info(f"Đã cập nhật ghi chú với ID {annotation_id}")
        return updated_annotation
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật ghi chú: {str(e)}")
        raise


async def delete_annotation(
    db: Session, annotation_id: int, admin_id: Optional[int] = None
) -> bool:
    """
    Xóa ghi chú.

    Args:
        db: Database session
        annotation_id: ID của ghi chú
        admin_id: ID của admin thực hiện hành động

    Returns:
        True nếu xóa thành công

    Raises:
        NotFoundException: Nếu không tìm thấy ghi chú
    """
    try:
        # Kiểm tra ghi chú tồn tại
        annotation = await get_annotation_by_id(db, annotation_id)

        # Xóa ghi chú
        repo = AnnotationRepository(db)
        result = await repo.delete(annotation_id)

        # Log admin activity
        if admin_id and result:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="DELETE",
                        entity_type="ANNOTATION",
                        entity_id=annotation_id,
                        description=f"Deleted annotation for user {annotation.user_id if hasattr(annotation, 'user_id') else 'unknown'}",
                        metadata={
                            "user_id": (
                                annotation.user_id
                                if hasattr(annotation, "user_id")
                                else None
                            ),
                            "book_id": (
                                annotation.book_id
                                if hasattr(annotation, "book_id")
                                else None
                            ),
                            "chapter_id": (
                                annotation.chapter_id
                                if hasattr(annotation, "chapter_id")
                                else None
                            ),
                            "content": (
                                annotation.content
                                if hasattr(annotation, "content")
                                else None
                            ),
                            "is_public": (
                                annotation.is_public
                                if hasattr(annotation, "is_public")
                                else None
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        # Remove cache
        invalidate_cache(f"admin_annotation:{annotation_id}")
        if hasattr(annotation, "user_id") and annotation.user_id:
            invalidate_cache(f"admin_user_annotations:{annotation.user_id}")
        if hasattr(annotation, "book_id") and annotation.book_id:
            invalidate_cache(f"admin_book_public_annotations:{annotation.book_id}")

        logger.info(f"Đã xóa ghi chú với ID {annotation_id}")
        return result
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi xóa ghi chú: {str(e)}")
        raise


@cached(key_prefix="admin_user_annotations", ttl=300)
async def get_user_annotations(
    db: Session,
    user_id: int,
    book_id: Optional[int] = None,
    chapter_id: Optional[int] = None,
    only_public: bool = False,
    skip: int = 0,
    limit: int = 20,
) -> List[Annotation]:
    """
    Lấy danh sách ghi chú của người dùng.

    Args:
        db: Database session
        user_id: ID của người dùng
        book_id: Lọc theo ID sách
        chapter_id: Lọc theo ID chương
        only_public: Chỉ lấy ghi chú công khai
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về

    Returns:
        Danh sách ghi chú của người dùng

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng
    """
    try:
        # Kiểm tra người dùng tồn tại
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)

        if not user:
            logger.warning(f"Không tìm thấy người dùng với ID {user_id}")
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        # Lấy danh sách ghi chú
        repo = AnnotationRepository(db)
        annotations = await repo.list_by_user(
            user_id,
            book_id=book_id,
            chapter_id=chapter_id,
            only_public=only_public,
            skip=skip,
            limit=limit,
        )

        return annotations
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách ghi chú của người dùng: {str(e)}")
        raise


@cached(key_prefix="admin_book_public_annotations", ttl=300)
async def get_book_public_annotations(
    db: Session,
    book_id: int,
    chapter_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 20,
) -> List[Annotation]:
    """
    Lấy danh sách ghi chú công khai của sách.

    Args:
        db: Database session
        book_id: ID của sách
        chapter_id: Lọc theo ID chương
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về

    Returns:
        Danh sách ghi chú công khai của sách

    Raises:
        NotFoundException: Nếu không tìm thấy sách
    """
    try:
        # Kiểm tra sách tồn tại
        book_repo = BookRepository(db)
        book = await book_repo.get_by_id(book_id)

        if not book:
            logger.warning(f"Không tìm thấy sách với ID {book_id}")
            raise NotFoundException(detail=f"Không tìm thấy sách với ID {book_id}")

        # Lấy danh sách ghi chú công khai
        repo = AnnotationRepository(db)
        annotations = await repo.list_public_by_book(
            book_id, chapter_id=chapter_id, skip=skip, limit=limit
        )

        return annotations
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách ghi chú công khai của sách: {str(e)}")
        raise


async def toggle_annotation_visibility(
    db: Session, annotation_id: int, admin_id: Optional[int] = None
) -> Annotation:
    """
    Chuyển đổi trạng thái công khai của ghi chú.

    Args:
        db: Database session
        annotation_id: ID của ghi chú
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin ghi chú đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy ghi chú
    """
    try:
        # Lấy thông tin ghi chú
        annotation = await get_annotation_by_id(db, annotation_id)

        # Cập nhật trạng thái công khai
        new_visibility = not annotation.is_public

        # Cập nhật ghi chú
        repo = AnnotationRepository(db)
        updated_annotation = await repo.update(
            annotation_id, {"is_public": new_visibility}
        )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="ANNOTATION_VISIBILITY",
                        entity_id=annotation_id,
                        description=f"Changed annotation visibility to {'public' if new_visibility else 'private'}",
                        metadata={
                            "user_id": (
                                annotation.user_id
                                if hasattr(annotation, "user_id")
                                else None
                            ),
                            "book_id": (
                                annotation.book_id
                                if hasattr(annotation, "book_id")
                                else None
                            ),
                            "chapter_id": (
                                annotation.chapter_id
                                if hasattr(annotation, "chapter_id")
                                else None
                            ),
                            "previous_visibility": (
                                annotation.is_public
                                if hasattr(annotation, "is_public")
                                else None
                            ),
                            "new_visibility": new_visibility,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        # Remove cache
        invalidate_cache(f"admin_annotation:{annotation_id}")
        if hasattr(annotation, "user_id") and annotation.user_id:
            invalidate_cache(f"admin_user_annotations:{annotation.user_id}")
        if hasattr(annotation, "book_id") and annotation.book_id:
            invalidate_cache(f"admin_book_public_annotations:{annotation.book_id}")

        logger.info(
            f"Đã chuyển đổi trạng thái công khai của ghi chú {annotation_id} thành {new_visibility}"
        )
        return updated_annotation
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi chuyển đổi trạng thái công khai của ghi chú: {str(e)}")
        raise


@cached(key_prefix="admin_annotation_statistics", ttl=3600)
async def get_annotation_statistics(
    db: Session, admin_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Lấy thống kê về ghi chú.

    Args:
        db: Database session
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thống kê ghi chú
    """
    try:
        # Đây là code demo, cần bổ sung các phương thức hỗ trợ trong repository
        stats = {
            "total_annotations": 0,  # Cần bổ sung phương thức count_all
            "public_annotations": 0,  # Cần bổ sung phương thức count_public
            "books_with_annotations": 0,  # Cần bổ sung phương thức count_books_with_annotations
            "users_with_annotations": 0,  # Cần bổ sung phương thức count_users_with_annotations
            "most_annotated_books": [],  # Cần bổ sung phương thức get_most_annotated_books
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
                        entity_type="ANNOTATION_STATISTICS",
                        entity_id=0,
                        description="Viewed annotation statistics",
                        metadata=stats,
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return stats
    except Exception as e:
        logger.error(f"Lỗi khi lấy thống kê ghi chú: {str(e)}")
        raise
