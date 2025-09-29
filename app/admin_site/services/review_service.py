from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
import logging

from app.user_site.models.review import Review, ReviewStatus
from app.user_site.repositories.review_repo import ReviewRepository
from app.user_site.repositories.review_like_repo import ReviewLikeRepository
from app.user_site.repositories.user_repo import UserRepository
from app.user_site.repositories.book_repo import BookRepository
from app.core.exceptions import (
    NotFoundException,
    ConflictException,
    BadRequestException,
)
from app.common.utils.cache import cached, remove_cache
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate

# Logger cho review service
logger = logging.getLogger(__name__)


async def get_all_reviews(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    user_id: Optional[int] = None,
    book_id: Optional[int] = None,
    status: Optional[ReviewStatus] = None,
    rating_min: Optional[int] = None,
    rating_max: Optional[int] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    search: Optional[str] = None,
    sort_by: str = "created_at",
    sort_desc: bool = True,
    admin_id: Optional[int] = None,
) -> List[Review]:
    """
    Lấy danh sách đánh giá với bộ lọc.

    Args:
        db: Database session
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về
        user_id: Lọc theo ID người dùng
        book_id: Lọc theo ID sách
        status: Lọc theo trạng thái
        rating_min: Lọc theo điểm đánh giá tối thiểu
        rating_max: Lọc theo điểm đánh giá tối đa
        from_date: Lọc từ ngày
        to_date: Lọc đến ngày
        search: Tìm kiếm theo nội dung
        sort_by: Sắp xếp theo trường
        sort_desc: Sắp xếp giảm dần
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách đánh giá
    """
    try:
        repo = ReviewRepository(db)
        reviews = await repo.list_reviews(
            skip=skip,
            limit=limit,
            user_id=user_id,
            book_id=book_id,
            status=status,
            rating_min=rating_min,
            rating_max=rating_max,
            from_date=from_date,
            to_date=to_date,
            search=search,
            sort_by=sort_by,
            sort_desc=sort_desc,
        )

        # Log admin activity
        if admin_id:
            try:
                activity_description = "Viewed reviews list"
                if user_id:
                    activity_description = f"Viewed reviews for user {user_id}"
                elif book_id:
                    activity_description = f"Viewed reviews for book {book_id}"

                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="REVIEWS",
                        entity_id=0,
                        description=activity_description,
                        metadata={
                            "skip": skip,
                            "limit": limit,
                            "user_id": user_id,
                            "book_id": book_id,
                            "status": status.value if status else None,
                            "rating_min": rating_min,
                            "rating_max": rating_max,
                            "from_date": from_date.isoformat() if from_date else None,
                            "to_date": to_date.isoformat() if to_date else None,
                            "search": search,
                            "sort_by": sort_by,
                            "sort_desc": sort_desc,
                            "results_count": len(reviews),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return reviews
    except Exception as e:
        logger.error(f"Error retrieving reviews: {str(e)}")
        raise


async def count_reviews(
    db: Session,
    user_id: Optional[int] = None,
    book_id: Optional[int] = None,
    status: Optional[ReviewStatus] = None,
    rating_min: Optional[int] = None,
    rating_max: Optional[int] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    search: Optional[str] = None,
) -> int:
    """
    Đếm số lượng đánh giá.

    Args:
        db: Database session
        user_id: Lọc theo ID người dùng
        book_id: Lọc theo ID sách
        status: Lọc theo trạng thái
        rating_min: Lọc theo điểm đánh giá tối thiểu
        rating_max: Lọc theo điểm đánh giá tối đa
        from_date: Lọc từ ngày
        to_date: Lọc đến ngày
        search: Tìm kiếm theo nội dung

    Returns:
        Số lượng đánh giá
    """
    try:
        repo = ReviewRepository(db)
        return await repo.count_reviews(
            user_id=user_id,
            book_id=book_id,
            status=status,
            rating_min=rating_min,
            rating_max=rating_max,
            from_date=from_date,
            to_date=to_date,
            search=search,
        )
    except Exception as e:
        logger.error(f"Error counting reviews: {str(e)}")
        raise


@cached(key_prefix="admin_review", ttl=300)
async def get_review_by_id(
    db: Session, review_id: int, admin_id: Optional[int] = None
) -> Review:
    """
    Lấy thông tin đánh giá theo ID.

    Args:
        db: Database session
        review_id: ID của đánh giá
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin đánh giá

    Raises:
        NotFoundException: Nếu không tìm thấy đánh giá
    """
    try:
        repo = ReviewRepository(db)
        review = await repo.get_by_id(review_id)

        if not review:
            logger.warning(f"Review with ID {review_id} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy đánh giá với ID {review_id}"
            )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="REVIEW",
                        entity_id=review_id,
                        description=f"Viewed review details for ID {review_id}",
                        metadata={
                            "user_id": (
                                review.user_id if hasattr(review, "user_id") else None
                            ),
                            "book_id": (
                                review.book_id if hasattr(review, "book_id") else None
                            ),
                            "rating": (
                                review.rating if hasattr(review, "rating") else None
                            ),
                            "status": (
                                review.status.value
                                if hasattr(review, "status")
                                else None
                            ),
                            "created_at": (
                                review.created_at.isoformat()
                                if hasattr(review, "created_at") and review.created_at
                                else None
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return review
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving review: {str(e)}")
        raise


async def get_user_reviews(
    db: Session,
    user_id: int,
    skip: int = 0,
    limit: int = 20,
    status: Optional[ReviewStatus] = None,
) -> List[Review]:
    """
    Lấy danh sách đánh giá của người dùng.

    Args:
        db: Database session
        user_id: ID của người dùng
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về
        status: Lọc theo trạng thái

    Returns:
        Danh sách đánh giá
    """
    try:
        repo = ReviewRepository(db)
        return await repo.list_reviews(
            user_id=user_id,
            skip=skip,
            limit=limit,
            status=status,
            sort_by="created_at",
            sort_desc=True,
        )
    except Exception as e:
        logger.error(f"Error retrieving user reviews: {str(e)}")
        raise


async def get_book_reviews(
    db: Session,
    book_id: int,
    skip: int = 0,
    limit: int = 20,
    status: Optional[ReviewStatus] = None,
) -> List[Review]:
    """
    Lấy danh sách đánh giá của một sách.

    Args:
        db: Database session
        book_id: ID của sách
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về
        status: Lọc theo trạng thái

    Returns:
        Danh sách đánh giá
    """
    try:
        repo = ReviewRepository(db)
        return await repo.list_reviews(
            book_id=book_id,
            skip=skip,
            limit=limit,
            status=status,
            sort_by="created_at",
            sort_desc=True,
        )
    except Exception as e:
        logger.error(f"Error retrieving book reviews: {str(e)}")
        raise


async def get_user_book_review(
    db: Session, user_id: int, book_id: int
) -> Optional[Review]:
    """
    Lấy đánh giá của người dùng cho một sách cụ thể.

    Args:
        db: Database session
        user_id: ID của người dùng
        book_id: ID của sách

    Returns:
        Thông tin đánh giá hoặc None nếu không có
    """
    try:
        repo = ReviewRepository(db)
        return await repo.get_by_user_and_book(user_id, book_id)
    except Exception as e:
        logger.error(f"Error retrieving user book review: {str(e)}")
        raise


async def create_review(
    db: Session, review_data: Dict[str, Any], admin_id: Optional[int] = None
) -> Review:
    """
    Tạo đánh giá mới.

    Args:
        db: Database session
        review_data: Dữ liệu đánh giá
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin đánh giá đã tạo

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng hoặc sách
        ConflictException: Nếu người dùng đã đánh giá sách này
        BadRequestException: Nếu dữ liệu không hợp lệ
    """
    try:
        # Kiểm tra người dùng tồn tại
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(review_data["user_id"])

        if not user:
            logger.warning(f"User with ID {review_data['user_id']} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {review_data['user_id']}"
            )

        # Kiểm tra sách tồn tại
        book_repo = BookRepository(db)
        book = await book_repo.get_by_id(review_data["book_id"])

        if not book:
            logger.warning(f"Book with ID {review_data['book_id']} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy sách với ID {review_data['book_id']}"
            )

        # Kiểm tra người dùng đã đánh giá sách này chưa
        review_repo = ReviewRepository(db)
        existing_review = await review_repo.get_by_user_and_book(
            user_id=review_data["user_id"], book_id=review_data["book_id"]
        )

        if existing_review:
            logger.warning(
                f"User {review_data['user_id']} already reviewed book {review_data['book_id']}"
            )
            raise ConflictException(detail=f"Người dùng đã đánh giá sách này")

        # Kiểm tra rating hợp lệ
        if not (1 <= review_data["rating"] <= 5):
            raise BadRequestException(detail="Điểm đánh giá phải từ 1 đến 5")

        # Thiết lập giá trị mặc định
        if "status" not in review_data:
            review_data["status"] = ReviewStatus.PUBLISHED

        # Tạo đánh giá mới
        review = await review_repo.create(review_data)

        # Cập nhật điểm đánh giá trung bình cho sách
        await book_repo.update_rating(book_id=review_data["book_id"])

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="CREATE",
                        entity_type="REVIEW",
                        entity_id=review.id,
                        description=f"Created new review for book {review.book_id} by user {review.user_id}",
                        metadata={
                            "user_id": review.user_id,
                            "username": (
                                user.username if hasattr(user, "username") else None
                            ),
                            "book_id": review.book_id,
                            "book_title": (
                                book.title if hasattr(book, "title") else None
                            ),
                            "rating": review.rating,
                            "status": (
                                review.status.value
                                if hasattr(review, "status")
                                else None
                            ),
                            "content_preview": (
                                review.content[:100] + "..."
                                if hasattr(review, "content")
                                and len(review.content) > 100
                                else (
                                    review.content
                                    if hasattr(review, "content")
                                    else None
                                )
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(
            f"Created new review with ID {review.id} for book {review.book_id} by user {review.user_id}"
        )
        return review
    except NotFoundException:
        raise
    except ConflictException:
        raise
    except BadRequestException:
        raise
    except Exception as e:
        logger.error(f"Error creating review: {str(e)}")
        raise


async def update_review(
    db: Session,
    review_id: int,
    review_data: Dict[str, Any],
    admin_id: Optional[int] = None,
) -> Review:
    """
    Cập nhật thông tin đánh giá.

    Args:
        db: Database session
        review_id: ID của đánh giá
        review_data: Dữ liệu cập nhật
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin đánh giá đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy đánh giá
        BadRequestException: Nếu dữ liệu không hợp lệ
    """
    try:
        review_repo = ReviewRepository(db)

        # Kiểm tra đánh giá tồn tại
        review = await get_review_by_id(db, review_id)

        # Kiểm tra rating hợp lệ
        if "rating" in review_data and not (1 <= review_data["rating"] <= 5):
            raise BadRequestException(detail="Điểm đánh giá phải từ 1 đến 5")

        # Cập nhật đánh giá
        updated_review = await review_repo.update(review_id, review_data)

        # Xóa cache
        remove_cache(f"admin_review:{review_id}")

        # Cập nhật điểm đánh giá trung bình cho sách nếu rating thay đổi
        if "rating" in review_data or "status" in review_data:
            book_repo = BookRepository(db)
            await book_repo.update_rating(book_id=review.book_id)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="REVIEW",
                        entity_id=review_id,
                        description=f"Updated review for book {review.book_id} by user {review.user_id}",
                        metadata={
                            "user_id": review.user_id,
                            "book_id": review.book_id,
                            "previous_rating": review.rating,
                            "new_rating": review_data.get("rating", review.rating),
                            "previous_status": (
                                review.status.value
                                if hasattr(review, "status")
                                else None
                            ),
                            "new_status": (
                                review_data.get("status", review.status).value
                                if isinstance(review_data.get("status"), ReviewStatus)
                                else review_data.get("status")
                            ),
                            "updates": {
                                k: (v.value if isinstance(v, ReviewStatus) else v)
                                for k, v in review_data.items()
                            },
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Updated review with ID {review_id}")
        return updated_review
    except NotFoundException:
        raise
    except BadRequestException:
        raise
    except Exception as e:
        logger.error(f"Error updating review: {str(e)}")
        raise


async def delete_review(
    db: Session, review_id: int, admin_id: Optional[int] = None
) -> None:
    """
    Xóa đánh giá.

    Args:
        db: Database session
        review_id: ID của đánh giá
        admin_id: ID của admin thực hiện hành động

    Raises:
        NotFoundException: Nếu không tìm thấy đánh giá
    """
    try:
        review_repo = ReviewRepository(db)

        # Kiểm tra đánh giá tồn tại
        review = await get_review_by_id(db, review_id)

        # Log admin activity before deletion
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="DELETE",
                        entity_type="REVIEW",
                        entity_id=review_id,
                        description=f"Deleted review for book {review.book_id} by user {review.user_id}",
                        metadata={
                            "user_id": review.user_id,
                            "book_id": review.book_id,
                            "rating": review.rating,
                            "status": (
                                review.status.value
                                if hasattr(review, "status")
                                else None
                            ),
                            "created_at": (
                                review.created_at.isoformat()
                                if hasattr(review, "created_at") and review.created_at
                                else None
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        # Xóa đánh giá
        await review_repo.delete(review_id)

        # Xóa cache
        remove_cache(f"admin_review:{review_id}")

        # Cập nhật điểm đánh giá trung bình cho sách
        book_repo = BookRepository(db)
        await book_repo.update_rating(book_id=review.book_id)

        logger.info(f"Deleted review with ID {review_id}")
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error deleting review: {str(e)}")
        raise


async def change_review_status(
    db: Session, review_id: int, status: ReviewStatus, admin_id: Optional[int] = None
) -> Review:
    """
    Thay đổi trạng thái đánh giá.

    Args:
        db: Database session
        review_id: ID của đánh giá
        status: Trạng thái mới
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin đánh giá đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy đánh giá
    """
    try:
        review_repo = ReviewRepository(db)

        # Kiểm tra đánh giá tồn tại
        review = await get_review_by_id(db, review_id)

        previous_status = review.status

        # Cập nhật trạng thái
        updated_review = await review_repo.update(review_id, {"status": status})

        # Xóa cache
        remove_cache(f"admin_review:{review_id}")

        # Cập nhật điểm đánh giá trung bình cho sách
        book_repo = BookRepository(db)
        await book_repo.update_rating(book_id=review.book_id)

        # Log admin activity
        if admin_id:
            try:
                activity_type = "UPDATE"
                if status == ReviewStatus.PUBLISHED:
                    activity_type = "PUBLISH"
                elif status == ReviewStatus.REJECTED:
                    activity_type = "REJECT"

                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type=activity_type,
                        entity_type="REVIEW",
                        entity_id=review_id,
                        description=f"Changed review status from {previous_status.value} to {status.value} for review ID {review_id}",
                        metadata={
                            "user_id": review.user_id,
                            "book_id": review.book_id,
                            "previous_status": previous_status.value,
                            "new_status": status.value,
                            "rating": review.rating,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Changed review status to {status} for review ID {review_id}")
        return updated_review
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error changing review status: {str(e)}")
        raise


async def like_review(db: Session, user_id: int, review_id: int) -> Dict[str, Any]:
    """
    Thích một đánh giá.

    Args:
        db: Database session
        user_id: ID của người dùng
        review_id: ID của đánh giá

    Returns:
        Kết quả thích đánh giá

    Raises:
        NotFoundException: Nếu không tìm thấy đánh giá
    """
    try:
        # Kiểm tra đánh giá tồn tại
        await get_review_by_id(db, review_id)

        # Kiểm tra người dùng tồn tại
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)

        if not user:
            logger.warning(f"User with ID {user_id} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        # Thêm lượt thích
        like_repo = ReviewLikeRepository(db)
        result = await like_repo.like_review(user_id, review_id)

        logger.info(f"User {user_id} liked review {review_id}")
        return result
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error liking review: {str(e)}")
        raise


async def unlike_review(db: Session, user_id: int, review_id: int) -> Dict[str, Any]:
    """
    Bỏ thích một đánh giá.

    Args:
        db: Database session
        user_id: ID của người dùng
        review_id: ID của đánh giá

    Returns:
        Kết quả bỏ thích đánh giá

    Raises:
        NotFoundException: Nếu không tìm thấy đánh giá
    """
    try:
        # Kiểm tra đánh giá tồn tại
        await get_review_by_id(db, review_id)

        # Bỏ lượt thích
        like_repo = ReviewLikeRepository(db)
        result = await like_repo.unlike_review(user_id, review_id)

        logger.info(f"User {user_id} unliked review {review_id}")
        return result
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error unliking review: {str(e)}")
        raise


async def get_review_likes(
    db: Session, review_id: int, skip: int = 0, limit: int = 20
) -> List[Dict[str, Any]]:
    """
    Lấy danh sách người dùng đã thích một đánh giá.

    Args:
        db: Database session
        review_id: ID của đánh giá
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về

    Returns:
        Danh sách người dùng

    Raises:
        NotFoundException: Nếu không tìm thấy đánh giá
    """
    try:
        # Kiểm tra đánh giá tồn tại
        await get_review_by_id(db, review_id)

        # Lấy danh sách lượt thích
        like_repo = ReviewLikeRepository(db)
        return await like_repo.get_review_likes(review_id, skip, limit)
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving review likes: {str(e)}")
        raise


async def count_review_likes(db: Session, review_id: int) -> int:
    """
    Đếm số lượt thích của một đánh giá.

    Args:
        db: Database session
        review_id: ID của đánh giá

    Returns:
        Số lượt thích

    Raises:
        NotFoundException: Nếu không tìm thấy đánh giá
    """
    try:
        # Kiểm tra đánh giá tồn tại
        await get_review_by_id(db, review_id)

        # Đếm số lượt thích
        like_repo = ReviewLikeRepository(db)
        return await like_repo.count_review_likes(review_id)
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error counting review likes: {str(e)}")
        raise


@cached(key_prefix="admin_review_statistics", ttl=3600)
async def get_review_statistics(
    db: Session, admin_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Lấy thống kê đánh giá.

    Args:
        db: Database session
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thống kê đánh giá
    """
    try:
        review_repo = ReviewRepository(db)

        total = await review_repo.count_reviews()
        published = await review_repo.count_reviews(status=ReviewStatus.PUBLISHED)
        pending = await review_repo.count_reviews(status=ReviewStatus.PENDING)
        rejected = await review_repo.count_reviews(status=ReviewStatus.REJECTED)

        # Thống kê theo thời gian
        now = datetime.now(timezone.utc)
        today = datetime(now.year, now.month, now.day)

        today_count = await review_repo.count_reviews(
            from_date=today, to_date=today + timedelta(days=1)
        )

        this_week = await review_repo.count_reviews(
            from_date=today - timedelta(days=today.weekday()),
            to_date=today + timedelta(days=1),
        )

        this_month = await review_repo.count_reviews(
            from_date=datetime(now.year, now.month, 1),
            to_date=(
                datetime(now.year, now.month + 1, 1)
                if now.month < 12
                else datetime(now.year + 1, 1, 1)
            ),
        )

        # Thống kê theo điểm đánh giá
        ratings = {}
        for rating in range(1, 6):
            count = await review_repo.count_reviews(
                rating_min=rating, rating_max=rating, status=ReviewStatus.PUBLISHED
            )
            ratings[str(rating)] = count

        # Điểm đánh giá trung bình
        avg_rating = await review_repo.get_average_rating()

        stats = {
            "total": total,
            "published": published,
            "pending": pending,
            "rejected": rejected,
            "today": today_count,
            "this_week": this_week,
            "this_month": this_month,
            "ratings": ratings,
            "avg_rating": round(avg_rating, 2) if avg_rating else 0,
        }

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="REVIEW_STATISTICS",
                        entity_id=0,
                        description="Viewed review statistics",
                        metadata=stats,
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return stats
    except Exception as e:
        logger.error(f"Error retrieving review statistics: {str(e)}")
        raise


async def get_popular_reviews(db: Session, limit: int = 10) -> List[Review]:
    """
    Lấy danh sách đánh giá phổ biến nhất (dựa trên số lượt thích).

    Args:
        db: Database session
        limit: Số lượng đánh giá tối đa trả về

    Returns:
        Danh sách đánh giá
    """
    try:
        review_repo = ReviewRepository(db)
        return await review_repo.get_popular_reviews(limit)
    except Exception as e:
        logger.error(f"Error retrieving popular reviews: {str(e)}")
        raise


async def get_recent_reviews(db: Session, limit: int = 10) -> List[Review]:
    """
    Lấy danh sách đánh giá gần đây.

    Args:
        db: Database session
        limit: Số lượng đánh giá tối đa trả về

    Returns:
        Danh sách đánh giá
    """
    try:
        review_repo = ReviewRepository(db)
        return await review_repo.list_reviews(
            status=ReviewStatus.PUBLISHED,
            limit=limit,
            sort_by="created_at",
            sort_desc=True,
        )
    except Exception as e:
        logger.error(f"Error retrieving recent reviews: {str(e)}")
        raise


async def get_pending_reviews(db: Session, limit: int = 10) -> List[Review]:
    """
    Lấy danh sách đánh giá đang chờ duyệt.

    Args:
        db: Database session
        limit: Số lượng đánh giá tối đa trả về

    Returns:
        Danh sách đánh giá
    """
    try:
        review_repo = ReviewRepository(db)
        return await review_repo.list_reviews(
            status=ReviewStatus.PENDING,
            limit=limit,
            sort_by="created_at",
            sort_desc=True,
        )
    except Exception as e:
        logger.error(f"Error retrieving pending reviews: {str(e)}")
        raise
