from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, date, timedelta
import logging

from app.admin_site.models import Promotion
from app.admin_site.schemas.promotion import PromotionCreate, PromotionUpdate
from app.admin_site.repositories.promotion_repo import PromotionRepository
from app.cache.decorators import cached, invalidate_cache
from app.core.exceptions import (
    NotFoundException,
    ServerException,
    BadRequestException,
    ConflictException,
)
from app.logging.setup import get_logger
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate

# Logger cho promotion service
logger = logging.getLogger(__name__)


@cached(ttl=300, namespace="admin:promotions", tags=["promotions"])
async def get_all_promotions(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
    is_expired: Optional[bool] = False,
    order_by: str = "created_at",
    order_desc: bool = True,
    admin_id: Optional[int] = None,
) -> List[Promotion]:
    """
    Lấy danh sách khuyến mãi.

    Args:
        db: Database session
        skip: Số lượng bản ghi bỏ qua
        limit: Số lượng bản ghi tối đa
        search: Tìm kiếm theo tên hoặc mã khuyến mãi
        is_active: Lọc theo trạng thái kích hoạt
        is_expired: Lọc các khuyến mãi đã hết hạn
        order_by: Trường sắp xếp
        order_desc: Sắp xếp giảm dần
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách khuyến mãi
    """
    try:
        promotions = await PromotionRepository.get_all(
            db, skip, limit, search, is_active, is_expired, order_by, order_desc
        )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="PROMOTIONS",
                        entity_id=0,
                        description="Viewed promotion list",
                        metadata={
                            "skip": skip,
                            "limit": limit,
                            "search_query": search,
                            "status": is_active,
                            "sort_by": order_by,
                            "sort_desc": order_desc,
                            "results_count": len(promotions),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return promotions
    except Exception as e:
        logger.error(f"Error retrieving promotions: {str(e)}")
        raise ServerException(detail=f"Lỗi khi lấy danh sách khuyến mãi: {str(e)}")


def count_promotions(
    db: Session,
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
    is_expired: Optional[bool] = False,
) -> int:
    """
    Đếm số lượng khuyến mãi.

    Args:
        db: Database session
        search: Tìm kiếm theo tên hoặc mã khuyến mãi
        is_active: Lọc theo trạng thái kích hoạt
        is_expired: Lọc các khuyến mãi đã hết hạn

    Returns:
        Tổng số khuyến mãi
    """
    try:
        return PromotionRepository.count(db, search, is_active, is_expired)
    except Exception as e:
        logger.error(f"Lỗi khi đếm khuyến mãi: {str(e)}")
        raise ServerException(detail=f"Lỗi khi đếm khuyến mãi: {str(e)}")


@cached(ttl=3600, namespace="admin:promotions", tags=["promotions"])
async def get_promotion_by_id(
    db: Session, promotion_id: int, admin_id: Optional[int] = None
) -> Promotion:
    """
    Lấy thông tin khuyến mãi theo ID.

    Args:
        db: Database session
        promotion_id: ID khuyến mãi
        admin_id: ID của admin thực hiện hành động

    Returns:
        Promotion object

    Raises:
        NotFoundException: Nếu không tìm thấy khuyến mãi
    """
    promotion = await PromotionRepository.get_by_id(db, promotion_id)
    if not promotion:
        logger.warning(f"Không tìm thấy khuyến mãi với ID={promotion_id}")
        raise NotFoundException(
            detail=f"Không tìm thấy khuyến mãi với ID={promotion_id}"
        )

    # Log admin activity
    if admin_id:
        try:
            await create_admin_activity_log(
                db,
                AdminActivityLogCreate(
                    admin_id=admin_id,
                    activity_type="VIEW",
                    entity_type="PROMOTION",
                    entity_id=promotion_id,
                    description=f"Viewed promotion details: {promotion.name}",
                    metadata={
                        "name": promotion.name,
                        "description": promotion.description,
                        "discount_percent": promotion.discount_percent,
                        "start_date": (
                            promotion.start_date.isoformat()
                            if promotion.start_date
                            else None
                        ),
                        "end_date": (
                            promotion.end_date.isoformat()
                            if promotion.end_date
                            else None
                        ),
                        "status": promotion.status,
                        "books_count": (
                            len(promotion.books) if hasattr(promotion, "books") else 0
                        ),
                    },
                ),
            )
        except Exception as e:
            logger.error(f"Failed to log admin activity: {str(e)}")

    return promotion


@cached(ttl=3600, namespace="admin:promotions:code", tags=["promotions"])
def get_promotion_by_code(db: Session, code: str) -> Optional[Promotion]:
    """
    Lấy thông tin khuyến mãi theo mã.

    Args:
        db: Database session
        code: Mã khuyến mãi

    Returns:
        Promotion object hoặc None nếu không tìm thấy
    """
    return PromotionRepository.get_by_code(db, code)


@invalidate_cache(tags=["promotions"])
async def create_promotion(
    db: Session, promotion_data: PromotionCreate, admin_id: Optional[int] = None
) -> Promotion:
    """
    Tạo khuyến mãi mới.

    Args:
        db: Database session
        promotion_data: Thông tin khuyến mãi mới
        admin_id: ID của admin thực hiện hành động

    Returns:
        Promotion object đã tạo

    Raises:
        ConflictException: Nếu mã khuyến mãi đã tồn tại
        BadRequestException: Nếu thông tin không hợp lệ
        ServerException: Nếu có lỗi khác
    """
    # Kiểm tra mã khuyến mãi đã tồn tại chưa
    if promotion_data.coupon_code:
        existing_coupon = PromotionRepository.get_by_code(
            db, promotion_data.coupon_code
        )
        if existing_coupon:
            logger.warning(f"Mã khuyến mãi đã tồn tại: {promotion_data.coupon_code}")
            raise ConflictException(
                detail=f"Mã khuyến mãi '{promotion_data.coupon_code}' đã tồn tại",
                field="coupon_code",
            )

    # Kiểm tra ngày bắt đầu và kết thúc hợp lệ
    if promotion_data.end_date and promotion_data.start_date > promotion_data.end_date:
        raise BadRequestException(detail="Ngày bắt đầu phải trước ngày kết thúc")

    # Kiểm tra giá trị giảm giá hợp lệ
    if (
        promotion_data.discount_type == "percentage"
        and promotion_data.discount_value > 100
    ):
        raise BadRequestException(
            detail="Giá trị giảm giá phần trăm không được vượt quá 100%"
        )

    # Chuẩn bị dữ liệu
    promotion_dict = promotion_data.model_dump()
    promotion_dict.update(
        {
            "usage_count": 0,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    )

    # Tạo khuyến mãi mới
    try:
        promotion = await PromotionRepository.create(db, promotion_dict)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="CREATE",
                        entity_type="PROMOTION",
                        entity_id=promotion.id,
                        description=f"Created new promotion: {promotion.name}",
                        metadata={
                            "name": promotion.name,
                            "description": promotion.description,
                            "discount_percent": promotion.discount_percent,
                            "start_date": (
                                promotion.start_date.isoformat()
                                if promotion.start_date
                                else None
                            ),
                            "end_date": (
                                promotion.end_date.isoformat()
                                if promotion.end_date
                                else None
                            ),
                            "status": promotion.status,
                            "book_ids": promotion_dict.get("book_ids", []),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Created new promotion with ID {promotion.id}")
        return promotion
    except Exception as e:
        logger.error(f"Lỗi khi tạo khuyến mãi: {str(e)}")
        raise ServerException(detail=f"Không thể tạo khuyến mãi: {str(e)}")


@invalidate_cache(tags=["promotions"])
async def update_promotion(
    db: Session,
    promotion_id: int,
    promotion_data: PromotionUpdate,
    admin_id: Optional[int] = None,
) -> Promotion:
    """
    Cập nhật thông tin khuyến mãi.

    Args:
        db: Database session
        promotion_id: ID khuyến mãi
        promotion_data: Thông tin cập nhật
        admin_id: ID của admin thực hiện hành động

    Returns:
        Promotion object đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy khuyến mãi
        ConflictException: Nếu mã khuyến mãi đã tồn tại
        BadRequestException: Nếu thông tin không hợp lệ
        ServerException: Nếu có lỗi khác
    """
    # Kiểm tra khuyến mãi tồn tại
    promotion = await get_promotion_by_id(db, promotion_id)
    if not promotion:
        logger.warning(f"Không tìm thấy khuyến mãi với ID={promotion_id}")
        raise NotFoundException(
            detail=f"Không tìm thấy khuyến mãi với ID={promotion_id}"
        )

    # Kiểm tra mã khuyến mãi đã tồn tại chưa nếu có thay đổi
    if (
        promotion_data.coupon_code
        and promotion_data.coupon_code != promotion.coupon_code
    ):
        existing_coupon = PromotionRepository.get_by_code(
            db, promotion_data.coupon_code
        )
        if existing_coupon and existing_coupon.id != promotion_id:
            logger.warning(f"Mã khuyến mãi đã tồn tại: {promotion_data.coupon_code}")
            raise ConflictException(
                detail=f"Mã khuyến mãi '{promotion_data.coupon_code}' đã tồn tại",
                field="coupon_code",
            )

    # Kiểm tra ngày bắt đầu và kết thúc hợp lệ
    start_date = (
        promotion_data.start_date if promotion_data.start_date else promotion.start_date
    )
    end_date = (
        promotion_data.end_date if promotion_data.end_date else promotion.end_date
    )

    if end_date and start_date > end_date:
        raise BadRequestException(detail="Ngày bắt đầu phải trước ngày kết thúc")

    # Kiểm tra giá trị giảm giá hợp lệ
    discount_type = (
        promotion_data.discount_type
        if promotion_data.discount_type
        else promotion.discount_type
    )
    discount_value = (
        promotion_data.discount_value
        if promotion_data.discount_value
        else promotion.discount_value
    )

    if discount_type == "percentage" and discount_value > 100:
        raise BadRequestException(
            detail="Giá trị giảm giá phần trăm không được vượt quá 100%"
        )

    # Chuẩn bị dữ liệu cập nhật
    update_data = promotion_data.model_dump(exclude_unset=True)
    update_data["updated_at"] = datetime.now(timezone.utc)

    # Cập nhật khuyến mãi
    try:
        updated_promotion = await PromotionRepository.update(
            db, promotion_id, update_data
        )
        if not updated_promotion:
            raise ServerException(
                detail=f"Không thể cập nhật khuyến mãi với ID={promotion_id}"
            )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="PROMOTION",
                        entity_id=promotion_id,
                        description=f"Updated promotion: {updated_promotion.name}",
                        metadata={
                            "updated_fields": list(update_data.keys()),
                            "old_values": {
                                k: getattr(promotion, k) for k in update_data.keys()
                            },
                            "new_values": {
                                k: getattr(updated_promotion, k)
                                for k in update_data.keys()
                            },
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Updated promotion with ID {promotion_id}")
        return updated_promotion
    except Exception as e:
        if isinstance(
            e,
            (
                NotFoundException,
                ConflictException,
                BadRequestException,
                ServerException,
            ),
        ):
            raise e

        logger.error(f"Lỗi khi cập nhật khuyến mãi: {str(e)}")
        raise ServerException(detail=f"Không thể cập nhật khuyến mãi: {str(e)}")


@invalidate_cache(tags=["promotions"])
async def delete_promotion(
    db: Session, promotion_id: int, admin_id: Optional[int] = None
) -> bool:
    """
    Xóa khuyến mãi.

    Args:
        db: Database session
        promotion_id: ID khuyến mãi
        admin_id: ID của admin thực hiện hành động

    Returns:
        True nếu xóa thành công

    Raises:
        NotFoundException: Nếu không tìm thấy khuyến mãi
        ServerException: Nếu có lỗi khác
    """
    # Kiểm tra khuyến mãi tồn tại
    promotion = await get_promotion_by_id(db, promotion_id)
    if not promotion:
        logger.warning(f"Không tìm thấy khuyến mãi với ID={promotion_id}")
        raise NotFoundException(
            detail=f"Không tìm thấy khuyến mãi với ID={promotion_id}"
        )

    # Xóa khuyến mãi
    try:
        success = await PromotionRepository.delete(db, promotion_id)
        if not success:
            raise ServerException(
                detail=f"Không thể xóa khuyến mãi với ID={promotion_id}"
            )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="DELETE",
                        entity_type="PROMOTION",
                        entity_id=promotion_id,
                        description=f"Deleted promotion: {promotion.name}",
                        metadata={
                            "name": promotion.name,
                            "description": promotion.description,
                            "discount_percent": promotion.discount_percent,
                            "start_date": (
                                promotion.start_date.isoformat()
                                if promotion.start_date
                                else None
                            ),
                            "end_date": (
                                promotion.end_date.isoformat()
                                if promotion.end_date
                                else None
                            ),
                            "status": promotion.status,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Deleted promotion with ID {promotion_id}")
        return True
    except Exception as e:
        if isinstance(e, (NotFoundException, ServerException)):
            raise e

        logger.error(f"Lỗi khi xóa khuyến mãi: {str(e)}")
        raise ServerException(detail=f"Không thể xóa khuyến mãi: {str(e)}")


@invalidate_cache(tags=["promotions"])
async def toggle_promotion_status(db: Session, promotion_id: int) -> Promotion:
    """
    Bật/tắt trạng thái khuyến mãi.

    Args:
        db: Database session
        promotion_id: ID khuyến mãi

    Returns:
        Promotion object đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy khuyến mãi
        ServerException: Nếu có lỗi khác
    """
    try:
        # Gọi repository để toggle status
        promotion = await PromotionRepository.toggle_status(db, promotion_id)
        if not promotion:
            raise NotFoundException(
                detail=f"Không tìm thấy khuyến mãi với ID={promotion_id}"
            )

        return promotion
    except Exception as e:
        if isinstance(e, NotFoundException):
            raise e

        logger.error(f"Lỗi khi thay đổi trạng thái khuyến mãi: {str(e)}")
        raise ServerException(
            detail=f"Không thể thay đổi trạng thái khuyến mãi: {str(e)}"
        )


@invalidate_cache(tags=["promotions"])
async def increment_promotion_usage(db: Session, promotion_id: int) -> Promotion:
    """
    Tăng số lần sử dụng khuyến mãi.

    Args:
        db: Database session
        promotion_id: ID khuyến mãi

    Returns:
        Promotion object đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy khuyến mãi
        ServerException: Nếu có lỗi khác
    """
    try:
        # Gọi repository để tăng số lần sử dụng
        promotion = await PromotionRepository.increment_usage(db, promotion_id)
        if not promotion:
            raise NotFoundException(
                detail=f"Không tìm thấy khuyến mãi với ID={promotion_id}"
            )

        return promotion
    except Exception as e:
        if isinstance(e, NotFoundException):
            raise e

        logger.error(f"Lỗi khi tăng số lần sử dụng khuyến mãi: {str(e)}")
        raise ServerException(
            detail=f"Không thể tăng số lần sử dụng khuyến mãi: {str(e)}"
        )


@cached(ttl=300, namespace="admin:promotions:valid", tags=["promotions"])
def get_valid_promotions(
    db: Session, skip: int = 0, limit: int = 100
) -> List[Promotion]:
    """
    Lấy danh sách khuyến mãi còn hiệu lực và chưa hết lượt sử dụng.

    Args:
        db: Database session
        skip: Số lượng bản ghi bỏ qua
        limit: Số lượng bản ghi tối đa

    Returns:
        Danh sách khuyến mãi hợp lệ
    """
    try:
        return PromotionRepository.get_valid(db, skip, limit)
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách khuyến mãi hợp lệ: {str(e)}")
        raise ServerException(
            detail=f"Lỗi khi lấy danh sách khuyến mãi hợp lệ: {str(e)}"
        )


@cached(key_prefix="admin_promotion_statistics", ttl=3600)
async def get_promotion_statistics(
    db: Session, admin_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Lấy thống kê khuyến mãi.

    Args:
        db: Database session
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thống kê khuyến mãi
    """
    try:
        repo = PromotionRepository(db)

        total = await repo.count_promotions()

        # Thống kê theo trạng thái
        by_status = await repo.count_promotions_by_status()

        # Thống kê theo mức giảm giá
        by_discount = await repo.count_promotions_by_discount()

        # Thống kê theo thời gian
        by_time = await repo.count_promotions_by_time()

        stats = {
            "total": total,
            "by_status": by_status,
            "by_discount": by_discount,
            "by_time": by_time,
        }

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="PROMOTION_STATISTICS",
                        entity_id=0,
                        description="Viewed promotion statistics",
                        metadata=stats,
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return stats
    except Exception as e:
        logger.error(f"Error retrieving promotion statistics: {str(e)}")
        raise
