from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
import logging

from app.user_site.models.recommendation import Recommendation, RecommendationType
from app.user_site.repositories.recommendation_repo import RecommendationRepository
from app.user_site.repositories.user_repo import UserRepository
from app.user_site.repositories.book_repo import BookRepository
from app.core.exceptions import (
    NotFoundException,
    ConflictException,
    ServerException,
    BadRequestException,
)
from app.common.utils.cache import cached, remove_cache, invalidate_cache
from app.logging.setup import get_logger
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate
from app.admin_site.schemas.recommendation import (
    RecommendationCreate,
    RecommendationUpdate,
)

# Logger cho recommendation service
logger = get_logger(__name__)


@cached(ttl=3600, namespace="admin:recommendations", tags=["recommendations"])
def get_all_recommendations(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    recommendation_type: Optional[str] = None,
    user_id: Optional[int] = None,
    book_id: Optional[int] = None,
    is_active: Optional[bool] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    order_by: str = "created_at",
    order_desc: bool = True,
    admin_id: Optional[int] = None,
) -> List[Recommendation]:
    """
    Lấy danh sách gợi ý.

    Args:
        db: Database session
        skip: Số lượng bản ghi bỏ qua
        limit: Số lượng bản ghi tối đa
        recommendation_type: Lọc theo loại gợi ý
        user_id: Lọc theo người dùng
        book_id: Lọc theo sách
        is_active: Lọc theo trạng thái hoạt động
        start_date: Lọc từ ngày
        end_date: Lọc đến ngày
        order_by: Trường sắp xếp
        order_desc: Sắp xếp giảm dần
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách gợi ý
    """
    try:
        recommendations = RecommendationRepository.get_all(
            db,
            skip,
            limit,
            recommendation_type,
            user_id,
            book_id,
            is_active,
            start_date,
            end_date,
            order_by,
            order_desc,
        )

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="RECOMMENDATIONS",
                        entity_id=0,
                        description="Viewed recommendations list",
                        metadata={
                            "skip": skip,
                            "limit": limit,
                            "recommendation_type": recommendation_type,
                            "user_id": user_id,
                            "book_id": book_id,
                            "is_active": is_active,
                            "start_date": (
                                start_date.isoformat() if start_date else None
                            ),
                            "end_date": end_date.isoformat() if end_date else None,
                            "order_by": order_by,
                            "order_desc": order_desc,
                            "results_count": len(recommendations),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return recommendations
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách gợi ý: {str(e)}")
        raise ServerException(detail=f"Lỗi khi lấy danh sách gợi ý: {str(e)}")


@cached(ttl=3600, namespace="admin:recommendations", tags=["recommendations"])
def get_recommendation_by_id(
    db: Session, recommendation_id: int, admin_id: Optional[int] = None
) -> Recommendation:
    """
    Lấy thông tin gợi ý theo ID.

    Args:
        db: Database session
        recommendation_id: ID gợi ý
        admin_id: ID của admin thực hiện hành động

    Returns:
        Recommendation object

    Raises:
        NotFoundException: Nếu không tìm thấy gợi ý
    """
    recommendation = RecommendationRepository.get_by_id(db, recommendation_id)
    if not recommendation:
        logger.warning(f"Không tìm thấy gợi ý với ID={recommendation_id}")
        raise NotFoundException(
            detail=f"Không tìm thấy gợi ý với ID={recommendation_id}"
        )

    # Log admin activity
    if admin_id:
        try:
            create_admin_activity_log(
                db,
                AdminActivityLogCreate(
                    admin_id=admin_id,
                    activity_type="VIEW",
                    entity_type="RECOMMENDATION",
                    entity_id=recommendation_id,
                    description=f"Viewed recommendation details",
                    metadata={
                        "recommendation_type": recommendation.recommendation_type,
                        "user_id": recommendation.user_id,
                        "book_id": recommendation.book_id,
                        "is_active": recommendation.is_active,
                        "created_at": (
                            recommendation.created_at.isoformat()
                            if recommendation.created_at
                            else None
                        ),
                    },
                ),
            )
        except Exception as e:
            logger.error(f"Failed to log admin activity: {str(e)}")

    return recommendation


@cached(ttl=3600, namespace="admin:recommendations:user", tags=["recommendations"])
def get_user_recommendations(
    db: Session, user_id: int, is_active: bool = True, admin_id: Optional[int] = None
) -> List[Recommendation]:
    """
    Lấy danh sách gợi ý của người dùng.

    Args:
        db: Database session
        user_id: ID người dùng
        is_active: Lọc theo trạng thái hoạt động
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách gợi ý
    """
    try:
        recommendations = RecommendationRepository.get_by_user(db, user_id, is_active)

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="USER_RECOMMENDATIONS",
                        entity_id=user_id,
                        description=f"Viewed recommendations for user ID: {user_id}",
                        metadata={
                            "user_id": user_id,
                            "is_active": is_active,
                            "results_count": len(recommendations),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return recommendations
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách gợi ý của người dùng: {str(e)}")
        raise ServerException(
            detail=f"Lỗi khi lấy danh sách gợi ý của người dùng: {str(e)}"
        )


@invalidate_cache(tags=["recommendations"])
def create_recommendation(
    db: Session,
    recommendation_data: RecommendationCreate,
    admin_id: Optional[int] = None,
) -> Recommendation:
    """
    Tạo gợi ý mới.

    Args:
        db: Database session
        recommendation_data: Thông tin gợi ý mới
        admin_id: ID của admin thực hiện hành động

    Returns:
        Recommendation object đã tạo

    Raises:
        BadRequestException: Nếu dữ liệu không hợp lệ
        NotFoundException: Nếu không tìm thấy book
        ConflictException: Nếu gợi ý đã tồn tại
        ServerException: Nếu có lỗi khác
    """
    # Kiểm tra dữ liệu
    if not recommendation_data.recommendation_type:
        raise BadRequestException(
            detail="Loại gợi ý không được trống", field="recommendation_type"
        )

    # Kiểm tra sách tồn tại
    if recommendation_data.book_id:
        book = BookRepository.get_by_id(db, recommendation_data.book_id)
        if not book:
            logger.warning(f"Không tìm thấy sách với ID={recommendation_data.book_id}")
            raise NotFoundException(
                detail=f"Không tìm thấy sách với ID={recommendation_data.book_id}"
            )

    # Kiểm tra gợi ý đã tồn tại (nếu cần)
    if recommendation_data.user_id and recommendation_data.book_id:
        existing_recommendation = RecommendationRepository.get_by_user_and_book(
            db, recommendation_data.user_id, recommendation_data.book_id
        )
        if existing_recommendation:
            logger.warning(
                f"Gợi ý cho user={recommendation_data.user_id} và book={recommendation_data.book_id} đã tồn tại"
            )
            raise ConflictException(
                detail="Gợi ý đã tồn tại cho người dùng và sách này",
                field="user_id,book_id",
            )

    # Chuẩn bị dữ liệu
    recommendation_dict = recommendation_data.model_dump()
    recommendation_dict.update(
        {
            "is_active": (
                True
                if recommendation_dict.get("is_active") is None
                else recommendation_dict["is_active"]
            ),
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    )

    # Tạo gợi ý mới
    try:
        created_recommendation = RecommendationRepository.create(
            db, recommendation_dict
        )

        # Log admin activity
        if admin_id:
            try:
                book_title = None
                if created_recommendation.book_id:
                    book = BookRepository.get_by_id(db, created_recommendation.book_id)
                    if book:
                        book_title = book.title

                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="CREATE",
                        entity_type="RECOMMENDATION",
                        entity_id=created_recommendation.id,
                        description=f"Created new recommendation",
                        metadata={
                            "recommendation_type": created_recommendation.recommendation_type,
                            "user_id": created_recommendation.user_id,
                            "book_id": created_recommendation.book_id,
                            "book_title": book_title,
                            "score": created_recommendation.score,
                            "is_active": created_recommendation.is_active,
                            "reason": created_recommendation.reason,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return created_recommendation
    except Exception as e:
        logger.error(f"Lỗi khi tạo gợi ý: {str(e)}")
        raise ServerException(detail=f"Không thể tạo gợi ý: {str(e)}")


@invalidate_cache(tags=["recommendations"])
def update_recommendation(
    db: Session,
    recommendation_id: int,
    recommendation_data: RecommendationUpdate,
    admin_id: Optional[int] = None,
) -> Recommendation:
    """
    Cập nhật thông tin gợi ý.

    Args:
        db: Database session
        recommendation_id: ID gợi ý
        recommendation_data: Thông tin cập nhật
        admin_id: ID của admin thực hiện hành động

    Returns:
        Recommendation object đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy gợi ý
        BadRequestException: Nếu dữ liệu không hợp lệ
        ServerException: Nếu có lỗi khác
    """
    # Kiểm tra gợi ý tồn tại
    recommendation = RecommendationRepository.get_by_id(db, recommendation_id)
    if not recommendation:
        logger.warning(f"Không tìm thấy gợi ý với ID={recommendation_id}")
        raise NotFoundException(
            detail=f"Không tìm thấy gợi ý với ID={recommendation_id}"
        )

    # Kiểm tra sách tồn tại nếu có cập nhật book_id
    if (
        recommendation_data.book_id is not None
        and recommendation_data.book_id != recommendation.book_id
    ):
        book = BookRepository.get_by_id(db, recommendation_data.book_id)
        if not book:
            logger.warning(f"Không tìm thấy sách với ID={recommendation_data.book_id}")
            raise NotFoundException(
                detail=f"Không tìm thấy sách với ID={recommendation_data.book_id}"
            )

    # Chuẩn bị dữ liệu cập nhật
    update_data = recommendation_data.model_dump(exclude_unset=True)
    update_data["updated_at"] = datetime.now(timezone.utc)

    # Lưu thông tin trước khi cập nhật cho việc ghi log
    previous_data = {
        "is_active": recommendation.is_active,
        "score": recommendation.score,
        "reason": recommendation.reason,
    }

    # Cập nhật gợi ý
    try:
        updated_recommendation = RecommendationRepository.update(
            db, recommendation_id, update_data
        )
        if not updated_recommendation:
            raise ServerException(
                detail=f"Không thể cập nhật gợi ý với ID={recommendation_id}"
            )

        # Log admin activity
        if admin_id:
            try:
                book_title = None
                if updated_recommendation.book_id:
                    book = BookRepository.get_by_id(db, updated_recommendation.book_id)
                    if book:
                        book_title = book.title

                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="RECOMMENDATION",
                        entity_id=recommendation_id,
                        description=f"Updated recommendation",
                        metadata={
                            "previous": previous_data,
                            "updated": {
                                k: v
                                for k, v in update_data.items()
                                if k != "updated_at"
                            },
                            "recommendation_type": recommendation.recommendation_type,
                            "user_id": recommendation.user_id,
                            "book_id": updated_recommendation.book_id,
                            "book_title": book_title,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return updated_recommendation
    except Exception as e:
        if isinstance(e, (NotFoundException, BadRequestException, ServerException)):
            raise e

        logger.error(f"Lỗi khi cập nhật gợi ý: {str(e)}")
        raise ServerException(detail=f"Không thể cập nhật gợi ý: {str(e)}")


@invalidate_cache(tags=["recommendations"])
def delete_recommendation(
    db: Session, recommendation_id: int, admin_id: Optional[int] = None
) -> bool:
    """
    Xóa gợi ý.

    Args:
        db: Database session
        recommendation_id: ID gợi ý
        admin_id: ID của admin thực hiện hành động

    Returns:
        True nếu xóa thành công

    Raises:
        NotFoundException: Nếu không tìm thấy gợi ý
        ServerException: Nếu có lỗi khác
    """
    # Kiểm tra gợi ý tồn tại
    recommendation = RecommendationRepository.get_by_id(db, recommendation_id)
    if not recommendation:
        logger.warning(f"Không tìm thấy gợi ý với ID={recommendation_id}")
        raise NotFoundException(
            detail=f"Không tìm thấy gợi ý với ID={recommendation_id}"
        )

    # Log admin activity before deletion
    if admin_id:
        try:
            book_title = None
            if recommendation.book_id:
                book = BookRepository.get_by_id(db, recommendation.book_id)
                if book:
                    book_title = book.title

            create_admin_activity_log(
                db,
                AdminActivityLogCreate(
                    admin_id=admin_id,
                    activity_type="DELETE",
                    entity_type="RECOMMENDATION",
                    entity_id=recommendation_id,
                    description=f"Deleted recommendation",
                    metadata={
                        "recommendation_type": recommendation.recommendation_type,
                        "user_id": recommendation.user_id,
                        "book_id": recommendation.book_id,
                        "book_title": book_title,
                        "score": recommendation.score,
                        "is_active": recommendation.is_active,
                        "created_at": (
                            recommendation.created_at.isoformat()
                            if recommendation.created_at
                            else None
                        ),
                    },
                ),
            )
        except Exception as e:
            logger.error(f"Failed to log admin activity: {str(e)}")

    # Xóa gợi ý
    try:
        success = RecommendationRepository.delete(db, recommendation_id)
        if not success:
            raise ServerException(
                detail=f"Không thể xóa gợi ý với ID={recommendation_id}"
            )

        return True
    except Exception as e:
        if isinstance(e, (NotFoundException, ServerException)):
            raise e

        logger.error(f"Lỗi khi xóa gợi ý: {str(e)}")
        raise ServerException(detail=f"Không thể xóa gợi ý: {str(e)}")


@invalidate_cache(tags=["recommendations"])
def deactivate_recommendation(
    db: Session, recommendation_id: int, admin_id: Optional[int] = None
) -> Recommendation:
    """
    Hủy kích hoạt gợi ý.

    Args:
        db: Database session
        recommendation_id: ID gợi ý
        admin_id: ID của admin thực hiện hành động

    Returns:
        Recommendation object đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy gợi ý
        ServerException: Nếu có lỗi khác
    """
    # Kiểm tra gợi ý tồn tại
    recommendation = RecommendationRepository.get_by_id(db, recommendation_id)
    if not recommendation:
        logger.warning(f"Không tìm thấy gợi ý với ID={recommendation_id}")
        raise NotFoundException(
            detail=f"Không tìm thấy gợi ý với ID={recommendation_id}"
        )

    # Nếu đã hủy kích hoạt rồi thì không cần thực hiện lại
    if not recommendation.is_active:
        return recommendation

    # Chuẩn bị dữ liệu cập nhật
    update_data = {"is_active": False, "updated_at": datetime.now(timezone.utc)}

    # Cập nhật gợi ý
    try:
        updated_recommendation = RecommendationRepository.update(
            db, recommendation_id, update_data
        )
        if not updated_recommendation:
            raise ServerException(
                detail=f"Không thể hủy kích hoạt gợi ý với ID={recommendation_id}"
            )

        # Log admin activity
        if admin_id:
            try:
                book_title = None
                if updated_recommendation.book_id:
                    book = BookRepository.get_by_id(db, updated_recommendation.book_id)
                    if book:
                        book_title = book.title

                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="RECOMMENDATION_STATUS",
                        entity_id=recommendation_id,
                        description=f"Deactivated recommendation",
                        metadata={
                            "recommendation_type": recommendation.recommendation_type,
                            "user_id": recommendation.user_id,
                            "book_id": recommendation.book_id,
                            "book_title": book_title,
                            "previous_status": True,
                            "new_status": False,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return updated_recommendation
    except Exception as e:
        if isinstance(e, (NotFoundException, ServerException)):
            raise e

        logger.error(f"Lỗi khi hủy kích hoạt gợi ý: {str(e)}")
        raise ServerException(detail=f"Không thể hủy kích hoạt gợi ý: {str(e)}")


@invalidate_cache(tags=["recommendations"])
def activate_recommendation(
    db: Session, recommendation_id: int, admin_id: Optional[int] = None
) -> Recommendation:
    """
    Kích hoạt gợi ý.

    Args:
        db: Database session
        recommendation_id: ID gợi ý
        admin_id: ID của admin thực hiện hành động

    Returns:
        Recommendation object đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy gợi ý
        ServerException: Nếu có lỗi khác
    """
    # Kiểm tra gợi ý tồn tại
    recommendation = RecommendationRepository.get_by_id(db, recommendation_id)
    if not recommendation:
        logger.warning(f"Không tìm thấy gợi ý với ID={recommendation_id}")
        raise NotFoundException(
            detail=f"Không tìm thấy gợi ý với ID={recommendation_id}"
        )

    # Nếu đã kích hoạt rồi thì không cần thực hiện lại
    if recommendation.is_active:
        return recommendation

    # Chuẩn bị dữ liệu cập nhật
    update_data = {"is_active": True, "updated_at": datetime.now(timezone.utc)}

    # Cập nhật gợi ý
    try:
        updated_recommendation = RecommendationRepository.update(
            db, recommendation_id, update_data
        )
        if not updated_recommendation:
            raise ServerException(
                detail=f"Không thể kích hoạt gợi ý với ID={recommendation_id}"
            )

        # Log admin activity
        if admin_id:
            try:
                book_title = None
                if updated_recommendation.book_id:
                    book = BookRepository.get_by_id(db, updated_recommendation.book_id)
                    if book:
                        book_title = book.title

                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="RECOMMENDATION_STATUS",
                        entity_id=recommendation_id,
                        description=f"Activated recommendation",
                        metadata={
                            "recommendation_type": recommendation.recommendation_type,
                            "user_id": recommendation.user_id,
                            "book_id": recommendation.book_id,
                            "book_title": book_title,
                            "previous_status": False,
                            "new_status": True,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return updated_recommendation
    except Exception as e:
        if isinstance(e, (NotFoundException, ServerException)):
            raise e

        logger.error(f"Lỗi khi kích hoạt gợi ý: {str(e)}")
        raise ServerException(detail=f"Không thể kích hoạt gợi ý: {str(e)}")


@cached(
    ttl=3600,
    namespace="admin:recommendations:statistics",
    tags=["recommendations", "statistics"],
)
def get_recommendation_statistics(
    db: Session,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    admin_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Lấy thống kê gợi ý.

    Args:
        db: Database session
        start_date: Thống kê từ ngày
        end_date: Thống kê đến ngày
        admin_id: ID của admin thực hiện hành động

    Returns:
        Dictionary chứa thông tin thống kê
    """
    # Mặc định lấy thống kê 30 ngày gần nhất
    if not end_date:
        end_date = datetime.now(timezone.utc)
    if not start_date:
        start_date = end_date - timedelta(days=30)

    try:
        # Tổng số gợi ý
        total_count = RecommendationRepository.count(
            db, None, None, None, None, start_date, end_date
        )

        # Số lượng gợi ý đang hoạt động
        active_count = RecommendationRepository.count(
            db, None, None, None, True, start_date, end_date
        )

        # Số lượng gợi ý theo loại
        types = RecommendationRepository.get_distinct_values(db, "recommendation_type")
        type_counts = {}
        for recommendation_type in types:
            type_counts[recommendation_type] = RecommendationRepository.count(
                db, recommendation_type, None, None, None, start_date, end_date
            )

        # Top 10 sách được gợi ý nhiều nhất
        top_books = RecommendationRepository.get_top_books(db, 10, start_date, end_date)

        # Số lượng gợi ý theo ngày
        daily_counts = RecommendationRepository.count_by_day(db, start_date, end_date)

        statistics = {
            "total_count": total_count,
            "active_count": active_count,
            "inactive_count": total_count - active_count,
            "type_counts": type_counts,
            "top_books": top_books,
            "daily_counts": daily_counts,
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
        }

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="RECOMMENDATION_STATISTICS",
                        entity_id=0,
                        description=f"Viewed recommendation statistics",
                        metadata={
                            "start_date": start_date.isoformat(),
                            "end_date": end_date.isoformat(),
                            "total_count": total_count,
                            "active_count": active_count,
                            "inactive_count": total_count - active_count,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return statistics
    except Exception as e:
        logger.error(f"Lỗi khi lấy thống kê gợi ý: {str(e)}")
        raise ServerException(detail=f"Lỗi khi lấy thống kê gợi ý: {str(e)}")


async def count_recommendations(
    db: Session,
    user_id: Optional[int] = None,
    type: Optional[RecommendationType] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
) -> int:
    """
    Đếm số lượng đề xuất.

    Args:
        db: Database session
        user_id: Lọc theo ID người dùng
        type: Lọc theo loại đề xuất
        from_date: Lọc từ ngày
        to_date: Lọc đến ngày

    Returns:
        Số lượng đề xuất
    """
    try:
        repo = RecommendationRepository(db)
        return await repo.count_recommendations(
            user_id=user_id, type=type, from_date=from_date, to_date=to_date
        )
    except Exception as e:
        logger.error(f"Error counting recommendations: {str(e)}")
        raise


async def get_user_recommendations(
    db: Session,
    user_id: int,
    type: Optional[RecommendationType] = None,
    skip: int = 0,
    limit: int = 20,
) -> List[Recommendation]:
    """
    Lấy danh sách đề xuất cho người dùng.

    Args:
        db: Database session
        user_id: ID của người dùng
        type: Lọc theo loại đề xuất
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về

    Returns:
        Danh sách đề xuất
    """
    try:
        repo = RecommendationRepository(db)
        return await repo.list_recommendations(
            user_id=user_id,
            type=type,
            skip=skip,
            limit=limit,
            sort_by="created_at",
            sort_desc=True,
        )
    except Exception as e:
        logger.error(f"Error retrieving user recommendations: {str(e)}")
        raise


async def create_recommendation(
    db: Session, recommendation_data: Dict[str, Any]
) -> Recommendation:
    """
    Tạo đề xuất mới.

    Args:
        db: Database session
        recommendation_data: Dữ liệu đề xuất

    Returns:
        Thông tin đề xuất đã tạo

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng hoặc sách
        ConflictException: Nếu đề xuất đã tồn tại
    """
    try:
        # Kiểm tra người dùng tồn tại
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(recommendation_data["user_id"])

        if not user:
            logger.warning(f"User with ID {recommendation_data['user_id']} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {recommendation_data['user_id']}"
            )

        # Kiểm tra sách tồn tại
        book_repo = BookRepository(db)
        book = await book_repo.get_by_id(recommendation_data["book_id"])

        if not book:
            logger.warning(f"Book with ID {recommendation_data['book_id']} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy sách với ID {recommendation_data['book_id']}"
            )

        # Kiểm tra đề xuất đã tồn tại
        repo = RecommendationRepository(db)
        existing_recommendation = await repo.get_by_user_and_book(
            user_id=recommendation_data["user_id"],
            book_id=recommendation_data["book_id"],
            type=recommendation_data["type"],
        )

        if existing_recommendation:
            logger.warning(
                f"Recommendation already exists for user {recommendation_data['user_id']} and book {recommendation_data['book_id']}"
            )
            raise ConflictException(
                detail=f"Đề xuất đã tồn tại cho người dùng và sách này"
            )

        # Tạo đề xuất mới
        recommendation = await repo.create(recommendation_data)

        logger.info(
            f"Created new recommendation with ID {recommendation.id} for user {recommendation.user_id}"
        )
        return recommendation
    except NotFoundException:
        raise
    except ConflictException:
        raise
    except Exception as e:
        logger.error(f"Error creating recommendation: {str(e)}")
        raise


async def update_recommendation(
    db: Session, recommendation_id: int, recommendation_data: Dict[str, Any]
) -> Recommendation:
    """
    Cập nhật thông tin đề xuất.

    Args:
        db: Database session
        recommendation_id: ID của đề xuất
        recommendation_data: Dữ liệu cập nhật

    Returns:
        Thông tin đề xuất đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy đề xuất
    """
    try:
        repo = RecommendationRepository(db)

        # Kiểm tra đề xuất tồn tại
        await get_recommendation_by_id(db, recommendation_id)

        # Cập nhật đề xuất
        recommendation = await repo.update(recommendation_id, recommendation_data)

        # Xóa cache
        remove_cache(f"admin_recommendation:{recommendation_id}")

        logger.info(f"Updated recommendation with ID {recommendation_id}")
        return recommendation
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error updating recommendation: {str(e)}")
        raise


async def delete_recommendation(db: Session, recommendation_id: int) -> None:
    """
    Xóa đề xuất.

    Args:
        db: Database session
        recommendation_id: ID của đề xuất

    Raises:
        NotFoundException: Nếu không tìm thấy đề xuất
    """
    try:
        repo = RecommendationRepository(db)

        # Kiểm tra đề xuất tồn tại
        await get_recommendation_by_id(db, recommendation_id)

        # Xóa đề xuất
        await repo.delete(recommendation_id)

        # Xóa cache
        remove_cache(f"admin_recommendation:{recommendation_id}")

        logger.info(f"Deleted recommendation with ID {recommendation_id}")
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error deleting recommendation: {str(e)}")
        raise


async def delete_user_recommendations(
    db: Session, user_id: int, type: Optional[RecommendationType] = None
) -> int:
    """
    Xóa tất cả đề xuất của người dùng.

    Args:
        db: Session
        user_id: ID của người dùng
        type: Loại đề xuất cần xóa (nếu None, xóa tất cả)

    Returns:
        Số lượng bản ghi đã xóa
    """
    try:
        repo = RecommendationRepository(db)
        count = await repo.delete_by_user(user_id, type)

        logger.info(f"Deleted {count} recommendations for user {user_id}")
        return count
    except Exception as e:
        logger.error(f"Error deleting user recommendations: {str(e)}")
        raise


async def create_batch_recommendations(
    db: Session, recommendations: List[Dict[str, Any]]
) -> int:
    """
    Tạo nhiều đề xuất cùng lúc.

    Args:
        db: Database session
        recommendations: Danh sách dữ liệu đề xuất

    Returns:
        Số lượng đề xuất đã tạo
    """
    try:
        repo = RecommendationRepository(db)
        count = await repo.create_batch(recommendations)

        logger.info(f"Created {count} recommendation(s) in batch")
        return count
    except Exception as e:
        logger.error(f"Error creating batch recommendations: {str(e)}")
        raise


async def regenerate_recommendations(
    db: Session,
    user_id: Optional[int] = None,
    type: Optional[RecommendationType] = None,
) -> Dict[str, Any]:
    """
    Tạo lại đề xuất cho người dùng.

    Args:
        db: Database session
        user_id: ID của người dùng (nếu None, tạo lại cho tất cả người dùng)
        type: Loại đề xuất cần tạo lại (nếu None, tạo lại tất cả loại)

    Returns:
        Kết quả tạo lại đề xuất
    """
    try:
        repo = RecommendationRepository(db)

        # Xóa đề xuất cũ
        if user_id:
            deleted = await repo.delete_by_user(user_id, type)
        else:
            deleted = await repo.delete_all(type)

        # Tạo đề xuất mới (logic tùy thuộc vào hệ thống đề xuất)
        # Đây là ví dụ, trong thực tế cần có một hệ thống đề xuất riêng
        generated = 0

        # Gọi API tạo đề xuất ở đây
        # ...

        result = {
            "deleted": deleted,
            "generated": generated,
            "user_id": user_id,
            "type": type.value if type else "all",
        }

        logger.info(f"Regenerated recommendations: {result}")
        return result
    except Exception as e:
        logger.error(f"Error regenerating recommendations: {str(e)}")
        raise


@cached(key_prefix="admin_recommendation_statistics", ttl=3600)
async def get_recommendation_statistics(db: Session) -> Dict[str, Any]:
    """
    Lấy thống kê đề xuất.

    Args:
        db: Database session

    Returns:
        Thống kê đề xuất
    """
    try:
        repo = RecommendationRepository(db)

        total = await repo.count_recommendations()

        # Thống kê theo loại đề xuất
        by_type = {}
        for recommendation_type in RecommendationType:
            count = await repo.count_recommendations(type=recommendation_type)
            by_type[recommendation_type.value] = count

        # Số người dùng có đề xuất
        users_with_recommendations = await repo.count_distinct_users()

        return {
            "total": total,
            "by_type": by_type,
            "users_with_recommendations": users_with_recommendations,
        }
    except Exception as e:
        logger.error(f"Error retrieving recommendation statistics: {str(e)}")
        raise


async def get_most_recommended_books(
    db: Session, limit: int = 10, type: Optional[RecommendationType] = None
) -> List[Dict[str, Any]]:
    """
    Lấy danh sách sách được đề xuất nhiều nhất.

    Args:
        db: Database session
        limit: Số lượng sách tối đa trả về
        type: Lọc theo loại đề xuất

    Returns:
        Danh sách sách kèm số lần được đề xuất
    """
    try:
        repo = RecommendationRepository(db)
        return await repo.get_most_recommended_books(limit, type)
    except Exception as e:
        logger.error(f"Error retrieving most recommended books: {str(e)}")
        raise


async def get_users_with_most_recommendations(
    db: Session, limit: int = 10, type: Optional[RecommendationType] = None
) -> List[Dict[str, Any]]:
    """
    Lấy danh sách người dùng có nhiều đề xuất nhất.

    Args:
        db: Database session
        limit: Số lượng người dùng tối đa trả về
        type: Lọc theo loại đề xuất

    Returns:
        Danh sách người dùng kèm số đề xuất
    """
    try:
        repo = RecommendationRepository(db)
        return await repo.get_users_with_most_recommendations(limit, type)
    except Exception as e:
        logger.error(f"Error retrieving users with most recommendations: {str(e)}")
        raise
