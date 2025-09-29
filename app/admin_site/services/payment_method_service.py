from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
import logging
from datetime import datetime

from app.user_site.models.payment import PaymentMethod
from app.user_site.repositories.payment_method_repo import PaymentMethodRepository
from app.user_site.repositories.user_repo import UserRepository
from app.core.exceptions import (
    NotFoundException,
    ForbiddenException,
    ConflictException,
    ServerException,
)
from app.cache.decorators import cached, invalidate_cache
from app.logging.setup import get_logger
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate
from app.user_site.schemas.payment import (
    PaymentMethodCreate,
    PaymentMethodUpdate,
)

# Logger cho payment method service
logger = logging.getLogger(__name__)


@cached(ttl=300, namespace="admin:payment_methods", tags=["payment_methods"])
async def get_all_payment_methods(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
    order_by: str = "created_at",
    order_desc: bool = True,
    admin_id: Optional[int] = None,
) -> List[PaymentMethod]:
    """
    Lấy danh sách phương thức thanh toán.

    Args:
        db: Database session
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về
        search: Từ khóa tìm kiếm
        is_active: Trạng thái hoạt động
        order_by: Trường sắp xếp
        order_desc: Sắp xếp giảm dần
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách phương thức thanh toán
    """
    try:
        payment_methods = await PaymentMethodRepository.get_all(
            db, skip, limit, search, is_active, order_by, order_desc
        )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="PAYMENT_METHODS",
                        entity_id=0,
                        description="Viewed payment method list",
                        metadata={
                            "skip": skip,
                            "limit": limit,
                            "search_query": search,
                            "is_active": is_active,
                            "sort_by": order_by,
                            "sort_desc": order_desc,
                            "results_count": len(payment_methods),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return payment_methods
    except Exception as e:
        logger.error(f"Error retrieving payment methods: {str(e)}")
        raise ServerException(
            detail=f"Lỗi khi lấy danh sách phương thức thanh toán: {str(e)}"
        )


async def count_payment_methods(
    db: Session, user_id: Optional[int] = None, is_active: bool = True
) -> int:
    """
    Đếm số lượng phương thức thanh toán.

    Args:
        db: Database session
        user_id: Lọc theo ID người dùng
        is_active: Chỉ đếm phương thức đang hoạt động

    Returns:
        Số lượng phương thức thanh toán
    """
    try:
        repo = PaymentMethodRepository(db)

        if user_id:
            # Đếm theo người dùng (repository chỉ hỗ trợ đếm theo user_id)
            count = await repo.count_by_user(user_id)

            # Lọc theo is_active sẽ được thực hiện ở repository
            return count
        else:
            # Hiện tại repository không hỗ trợ đếm tất cả phương thức thanh toán
            # Cần triển khai thêm phương thức count_all trong repository
            logger.warning(
                "Counting all payment methods without a user_id filter is not currently supported"
            )
            return 0
    except Exception as e:
        logger.error(f"Error counting payment methods: {str(e)}")
        raise


@cached(ttl=3600, namespace="admin:payment_methods", tags=["payment_methods"])
async def get_payment_method_by_id(
    db: Session, payment_method_id: int, admin_id: Optional[int] = None
) -> PaymentMethod:
    """
    Lấy thông tin phương thức thanh toán theo ID.

    Args:
        db: Database session
        payment_method_id: ID phương thức thanh toán
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin phương thức thanh toán

    Raises:
        NotFoundException: Nếu không tìm thấy phương thức thanh toán
    """
    try:
        payment_method = await PaymentMethodRepository.get_by_id(db, payment_method_id)

        if not payment_method:
            logger.warning(f"Payment method with ID {payment_method_id} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy phương thức thanh toán với ID={payment_method_id}"
            )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="PAYMENT_METHOD",
                        entity_id=payment_method_id,
                        description=f"Viewed payment method details: {payment_method.name}",
                        metadata={
                            "name": payment_method.name,
                            "code": payment_method.code,
                            "description": payment_method.description,
                            "is_active": payment_method.is_active,
                            "config": payment_method.config,
                            "created_at": (
                                payment_method.created_at.isoformat()
                                if payment_method.created_at
                                else None
                            ),
                            "updated_at": (
                                payment_method.updated_at.isoformat()
                                if payment_method.updated_at
                                else None
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return payment_method
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving payment method: {str(e)}")
        raise ServerException(
            detail=f"Lỗi khi lấy thông tin phương thức thanh toán: {str(e)}"
        )


@cached(key_prefix="admin_user_payment_methods", ttl=300)
async def get_user_payment_methods(
    db: Session, user_id: int, skip: int = 0, limit: int = 20
) -> List[PaymentMethod]:
    """
    Lấy danh sách phương thức thanh toán của người dùng.

    Args:
        db: Database session
        user_id: ID của người dùng
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về

    Returns:
        Danh sách phương thức thanh toán

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng
    """
    try:
        # Kiểm tra người dùng tồn tại
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)

        if not user:
            logger.warning(f"User with ID {user_id} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        repo = PaymentMethodRepository(db)
        return await repo.list_by_user(user_id, skip, limit)
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving user payment methods: {str(e)}")
        raise


async def get_default_payment_method(
    db: Session, user_id: int
) -> Optional[PaymentMethod]:
    """
    Lấy phương thức thanh toán mặc định của người dùng.

    Args:
        db: Database session
        user_id: ID của người dùng

    Returns:
        Phương thức thanh toán mặc định hoặc None nếu không có

    Raises:
        NotFoundException: Nếu không tìm thấy người dùng
    """
    try:
        # Kiểm tra người dùng tồn tại
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)

        if not user:
            logger.warning(f"User with ID {user_id} not found")
            raise NotFoundException(
                detail=f"Không tìm thấy người dùng với ID {user_id}"
            )

        repo = PaymentMethodRepository(db)
        return await repo.get_default_method(user_id)
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving default payment method: {str(e)}")
        raise


@invalidate_cache(tags=["payment_methods"])
async def create_payment_method(
    db: Session,
    payment_method_data: PaymentMethodCreate,
    admin_id: Optional[int] = None,
) -> PaymentMethod:
    """
    Tạo phương thức thanh toán mới.

    Args:
        db: Database session
        payment_method_data: Thông tin phương thức thanh toán mới
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin phương thức thanh toán đã tạo

    Raises:
        ConflictException: Nếu phương thức thanh toán đã tồn tại
    """
    try:
        # Kiểm tra xem phương thức thanh toán đã tồn tại chưa
        existing_payment_method = await PaymentMethodRepository.get_by_code(
            db, payment_method_data.code
        )

        if existing_payment_method:
            logger.warning(
                f"Payment method with code {payment_method_data.code} already exists"
            )
            raise ConflictException(
                detail=f"Phương thức thanh toán với mã {payment_method_data.code} đã tồn tại"
            )

        # Chuyển đổi dữ liệu
        payment_method_dict = payment_method_data.model_dump()

        # Tạo phương thức thanh toán mới
        payment_method = await PaymentMethodRepository.create(db, payment_method_dict)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="CREATE",
                        entity_type="PAYMENT_METHOD",
                        entity_id=payment_method.id,
                        description=f"Created new payment method: {payment_method.name}",
                        metadata={
                            "name": payment_method.name,
                            "code": payment_method.code,
                            "description": payment_method.description,
                            "is_active": payment_method.is_active,
                            "config": payment_method.config,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Created new payment method with ID {payment_method.id}")
        return payment_method
    except ConflictException:
        raise
    except Exception as e:
        logger.error(f"Error creating payment method: {str(e)}")
        raise ServerException(detail=f"Không thể tạo phương thức thanh toán: {str(e)}")


@invalidate_cache(tags=["payment_methods"])
async def update_payment_method(
    db: Session,
    payment_method_id: int,
    payment_method_data: PaymentMethodUpdate,
    admin_id: Optional[int] = None,
) -> PaymentMethod:
    """
    Cập nhật thông tin phương thức thanh toán.

    Args:
        db: Database session
        payment_method_id: ID phương thức thanh toán
        payment_method_data: Thông tin cập nhật
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thông tin phương thức thanh toán đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy phương thức thanh toán
        ConflictException: Nếu mã phương thức thanh toán đã tồn tại
    """
    try:
        # Kiểm tra phương thức thanh toán tồn tại
        payment_method = await get_payment_method_by_id(db, payment_method_id)

        # Kiểm tra xem mã mới có trùng với phương thức thanh toán khác không
        if payment_method_data.code and payment_method_data.code != payment_method.code:
            existing_payment_method = await PaymentMethodRepository.get_by_code(
                db, payment_method_data.code
            )

            if existing_payment_method:
                logger.warning(
                    f"Payment method with code {payment_method_data.code} already exists"
                )
                raise ConflictException(
                    detail=f"Phương thức thanh toán với mã {payment_method_data.code} đã tồn tại"
                )

        # Chuyển đổi dữ liệu
        update_data = payment_method_data.model_dump(exclude_unset=True)

        # Cập nhật phương thức thanh toán
        updated_payment_method = await PaymentMethodRepository.update(
            db, payment_method_id, update_data
        )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="PAYMENT_METHOD",
                        entity_id=payment_method_id,
                        description=f"Updated payment method: {updated_payment_method.name}",
                        metadata={
                            "updated_fields": list(update_data.keys()),
                            "old_values": {
                                k: getattr(payment_method, k)
                                for k in update_data.keys()
                            },
                            "new_values": {
                                k: getattr(updated_payment_method, k)
                                for k in update_data.keys()
                            },
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Updated payment method with ID {payment_method_id}")
        return updated_payment_method
    except NotFoundException:
        raise
    except ConflictException:
        raise
    except Exception as e:
        logger.error(f"Error updating payment method: {str(e)}")
        raise ServerException(
            detail=f"Không thể cập nhật phương thức thanh toán với ID={payment_method_id}"
        )


@invalidate_cache(tags=["payment_methods"])
async def delete_payment_method(
    db: Session, payment_method_id: int, admin_id: Optional[int] = None
) -> bool:
    """
    Xóa phương thức thanh toán.

    Args:
        db: Database session
        payment_method_id: ID phương thức thanh toán
        admin_id: ID của admin thực hiện hành động

    Returns:
        True nếu xóa thành công

    Raises:
        NotFoundException: Nếu không tìm thấy phương thức thanh toán
    """
    try:
        # Kiểm tra phương thức thanh toán tồn tại
        payment_method = await get_payment_method_by_id(db, payment_method_id)

        # Xóa phương thức thanh toán
        await PaymentMethodRepository.delete(db, payment_method_id)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="DELETE",
                        entity_type="PAYMENT_METHOD",
                        entity_id=payment_method_id,
                        description=f"Deleted payment method: {payment_method.name}",
                        metadata={
                            "name": payment_method.name,
                            "code": payment_method.code,
                            "description": payment_method.description,
                            "is_active": payment_method.is_active,
                            "config": payment_method.config,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Deleted payment method with ID {payment_method_id}")
        return True
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error deleting payment method: {str(e)}")
        raise ServerException(
            detail=f"Không thể xóa phương thức thanh toán với ID={payment_method_id}"
        )


async def set_default_payment_method(
    db: Session, payment_method_id: int, user_id: int
) -> bool:
    """
    Đặt phương thức thanh toán làm mặc định.

    Args:
        db: Database session
        payment_method_id: ID của phương thức thanh toán
        user_id: ID của người dùng

    Returns:
        True nếu thành công

    Raises:
        NotFoundException: Nếu không tìm thấy phương thức thanh toán
        ForbiddenException: Nếu phương thức thanh toán không thuộc về người dùng
    """
    try:
        # Kiểm tra phương thức thanh toán tồn tại
        payment_method = await get_payment_method_by_id(db, payment_method_id)

        # Kiểm tra phương thức thanh toán thuộc về người dùng
        if payment_method.user_id != user_id:
            logger.warning(
                f"Payment method {payment_method_id} does not belong to user {user_id}"
            )
            raise ForbiddenException(
                detail="Phương thức thanh toán không thuộc về người dùng này"
            )

        # Đặt phương thức thanh toán làm mặc định
        repo = PaymentMethodRepository(db)
        result = await repo.set_default_method(payment_method_id, user_id)

        logger.info(
            f"Set payment method {payment_method_id} as default for user {user_id}"
        )
        return result
    except NotFoundException:
        raise
    except ForbiddenException:
        raise
    except Exception as e:
        logger.error(f"Error setting default payment method: {str(e)}")
        raise


async def deactivate_payment_method(
    db: Session, payment_method_id: int, user_id: int
) -> bool:
    """
    Vô hiệu hóa phương thức thanh toán.

    Args:
        db: Database session
        payment_method_id: ID của phương thức thanh toán
        user_id: ID của người dùng

    Returns:
        True nếu thành công

    Raises:
        NotFoundException: Nếu không tìm thấy phương thức thanh toán
        ForbiddenException: Nếu phương thức thanh toán không thuộc về người dùng
    """
    try:
        # Kiểm tra phương thức thanh toán tồn tại
        payment_method = await get_payment_method_by_id(db, payment_method_id)

        # Kiểm tra phương thức thanh toán thuộc về người dùng
        if payment_method.user_id != user_id:
            logger.warning(
                f"Payment method {payment_method_id} does not belong to user {user_id}"
            )
            raise ForbiddenException(
                detail="Phương thức thanh toán không thuộc về người dùng này"
            )

        # Vô hiệu hóa phương thức thanh toán
        repo = PaymentMethodRepository(db)
        result = await repo.deactivate_method(payment_method_id, user_id)

        logger.info(
            f"Deactivated payment method {payment_method_id} for user {user_id}"
        )
        return result
    except NotFoundException:
        raise
    except ForbiddenException:
        raise
    except Exception as e:
        logger.error(f"Error deactivating payment method: {str(e)}")
        raise


async def verify_payment_method(
    db: Session, payment_method_id: int, user_id: int
) -> bool:
    """
    Xác minh phương thức thanh toán.

    Args:
        db: Database session
        payment_method_id: ID của phương thức thanh toán
        user_id: ID của người dùng

    Returns:
        True nếu thành công

    Raises:
        NotFoundException: Nếu không tìm thấy phương thức thanh toán
        ForbiddenException: Nếu phương thức thanh toán không thuộc về người dùng
    """
    try:
        # Kiểm tra phương thức thanh toán tồn tại
        payment_method = await get_payment_method_by_id(db, payment_method_id)

        # Kiểm tra phương thức thanh toán thuộc về người dùng
        if payment_method.user_id != user_id:
            logger.warning(
                f"Payment method {payment_method_id} does not belong to user {user_id}"
            )
            raise ForbiddenException(
                detail="Phương thức thanh toán không thuộc về người dùng này"
            )

        # Xác minh phương thức thanh toán
        repo = PaymentMethodRepository(db)
        result = await repo.verify_method(payment_method_id, user_id)

        logger.info(f"Verified payment method {payment_method_id} for user {user_id}")
        return result
    except NotFoundException:
        raise
    except ForbiddenException:
        raise
    except Exception as e:
        logger.error(f"Error verifying payment method: {str(e)}")
        raise


@cached(key_prefix="admin_payment_method_statistics", ttl=3600)
async def get_payment_method_statistics(
    db: Session, admin_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Lấy thống kê phương thức thanh toán.

    Args:
        db: Database session
        admin_id: ID của admin thực hiện hành động

    Returns:
        Thống kê phương thức thanh toán
    """
    try:
        repo = PaymentMethodRepository(db)

        total = await repo.count_payment_methods()

        # Thống kê theo trạng thái
        by_status = await repo.count_payment_methods_by_status()

        # Thống kê theo loại
        by_type = await repo.count_payment_methods_by_type()

        # Thống kê theo thời gian
        by_time = await repo.count_payment_methods_by_time()

        stats = {
            "total": total,
            "by_status": by_status,
            "by_type": by_type,
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
                        entity_type="PAYMENT_METHOD_STATISTICS",
                        entity_id=0,
                        description="Viewed payment method statistics",
                        metadata=stats,
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return stats
    except Exception as e:
        logger.error(f"Error retrieving payment method statistics: {str(e)}")
        raise
