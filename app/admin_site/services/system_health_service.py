from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, date, timedelta
import json

from app.admin_site.models import SystemHealth
from app.admin_site.schemas.system_health import SystemHealthCreate, SystemHealthUpdate
from app.admin_site.repositories.system_health_repo import SystemHealthRepository
from app.cache.decorators import cached, invalidate_cache
from app.core.exceptions import NotFoundException, ServerException, BadRequestException
from app.logging.setup import get_logger
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate

logger = get_logger(__name__)


@cached(ttl=300, namespace="admin:system_health", tags=["system_health"])
def get_all_system_health(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    component: Optional[str] = None,
    status: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    order_by: str = "checked_at",
    order_desc: bool = True,
    admin_id: Optional[int] = None,
) -> List[SystemHealth]:
    """
    Lấy danh sách trạng thái sức khỏe hệ thống.

    Args:
        db: Database session
        skip: Số lượng bản ghi bỏ qua
        limit: Số lượng bản ghi tối đa
        component: Lọc theo thành phần
        status: Lọc theo trạng thái
        start_date: Ngày bắt đầu
        end_date: Ngày kết thúc
        order_by: Sắp xếp theo trường
        order_desc: Sắp xếp giảm dần
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách trạng thái sức khỏe hệ thống
    """
    try:
        # Chuyển đổi date thành datetime
        start_datetime = None
        end_datetime = None

        if start_date:
            start_datetime = datetime.combine(start_date, datetime.min.time())

        if end_date:
            end_datetime = datetime.combine(end_date, datetime.max.time())

        results = SystemHealthRepository.get_all(
            db,
            skip,
            limit,
            component,
            status,
            start_datetime,
            end_datetime,
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
                        entity_type="SYSTEM_HEALTH_LIST",
                        entity_id=0,
                        description="Viewed system health list",
                        metadata={
                            "skip": skip,
                            "limit": limit,
                            "component": component,
                            "status": status,
                            "start_date": (
                                start_date.isoformat() if start_date else None
                            ),
                            "end_date": end_date.isoformat() if end_date else None,
                            "order_by": order_by,
                            "order_desc": order_desc,
                            "results_count": len(results),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return results
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách trạng thái sức khỏe hệ thống: {str(e)}")
        raise ServerException(
            detail=f"Lỗi khi lấy danh sách trạng thái sức khỏe hệ thống: {str(e)}"
        )


def count_system_health(
    db: Session,
    component: Optional[str] = None,
    status: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> int:
    """
    Đếm số lượng trạng thái sức khỏe hệ thống.

    Args:
        db: Database session
        component: Lọc theo thành phần
        status: Lọc theo trạng thái
        start_date: Ngày bắt đầu
        end_date: Ngày kết thúc

    Returns:
        Tổng số trạng thái sức khỏe hệ thống
    """
    try:
        # Chuyển đổi date thành datetime
        start_datetime = None
        end_datetime = None

        if start_date:
            start_datetime = datetime.combine(start_date, datetime.min.time())

        if end_date:
            end_datetime = datetime.combine(end_date, datetime.max.time())

        return SystemHealthRepository.count(
            db, component, status, start_datetime, end_datetime
        )
    except Exception as e:
        logger.error(f"Lỗi khi đếm trạng thái sức khỏe hệ thống: {str(e)}")
        raise ServerException(
            detail=f"Lỗi khi đếm trạng thái sức khỏe hệ thống: {str(e)}"
        )


@cached(ttl=300, namespace="admin:system_health", tags=["system_health"])
def get_system_health_by_id(
    db: Session, health_id: int, admin_id: Optional[int] = None
) -> SystemHealth:
    """
    Lấy thông tin trạng thái sức khỏe hệ thống theo ID.

    Args:
        db: Database session
        health_id: ID trạng thái
        admin_id: ID của admin thực hiện hành động

    Returns:
        SystemHealth object

    Raises:
        NotFoundException: Nếu không tìm thấy trạng thái
    """
    health = SystemHealthRepository.get_by_id(db, health_id)
    if not health:
        logger.warning(
            f"Không tìm thấy trạng thái sức khỏe hệ thống với ID={health_id}"
        )
        raise NotFoundException(
            detail=f"Không tìm thấy trạng thái sức khỏe hệ thống với ID={health_id}"
        )

    # Log admin activity
    if admin_id:
        try:
            create_admin_activity_log(
                db,
                AdminActivityLogCreate(
                    admin_id=admin_id,
                    activity_type="VIEW",
                    entity_type="SYSTEM_HEALTH",
                    entity_id=health_id,
                    description=f"Viewed system health record for component {health.component}",
                    metadata={
                        "component": health.component,
                        "status": health.status,
                        "checked_at": (
                            health.checked_at.isoformat() if health.checked_at else None
                        ),
                    },
                ),
            )
        except Exception as e:
            logger.error(f"Failed to log admin activity: {str(e)}")

    return health


@cached(ttl=300, namespace="admin:system_health", tags=["system_health"])
def get_latest_system_health(
    db: Session, component: Optional[str] = None, admin_id: Optional[int] = None
) -> List[SystemHealth]:
    """
    Lấy trạng thái sức khỏe hệ thống mới nhất.

    Args:
        db: Database session
        component: Lọc theo thành phần
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách trạng thái sức khỏe hệ thống mới nhất
    """
    try:
        results = SystemHealthRepository.get_latest(db, component)

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="SYSTEM_HEALTH_LATEST",
                        entity_id=0,
                        description="Viewed latest system health records",
                        metadata={
                            "component": component,
                            "results_count": len(results),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return results
    except Exception as e:
        logger.error(f"Lỗi khi lấy trạng thái sức khỏe hệ thống mới nhất: {str(e)}")
        raise ServerException(
            detail=f"Lỗi khi lấy trạng thái sức khỏe hệ thống mới nhất: {str(e)}"
        )


@invalidate_cache(tags=["system_health"])
def create_system_health(
    db: Session, health_data: SystemHealthCreate, admin_id: Optional[int] = None
) -> SystemHealth:
    """
    Tạo trạng thái sức khỏe hệ thống mới.

    Args:
        db: Database session
        health_data: Thông tin trạng thái mới
        admin_id: ID của admin thực hiện hành động

    Returns:
        SystemHealth object đã tạo

    Raises:
        BadRequestException: Nếu dữ liệu không hợp lệ
        ServerException: Nếu có lỗi khác
    """
    # Chuẩn bị dữ liệu details
    details_json = None
    if health_data.details:
        try:
            # Kiểm tra nếu là chuỗi JSON
            if isinstance(health_data.details, str):
                json.loads(health_data.details)  # Chỉ để kiểm tra
                details_json = health_data.details
            else:
                # Chuyển đổi đối tượng thành chuỗi JSON
                details_json = json.dumps(health_data.details)
        except json.JSONDecodeError:
            logger.error(f"Chi tiết không phải là JSON hợp lệ")
            raise BadRequestException(detail="Chi tiết không phải là JSON hợp lệ")

    # Kiểm tra trạng thái hợp lệ
    valid_statuses = ["healthy", "warning", "critical"]
    if health_data.status not in valid_statuses:
        raise BadRequestException(
            detail=f"Trạng thái không hợp lệ. Chọn một trong: {', '.join(valid_statuses)}"
        )

    # Chuẩn bị dữ liệu
    health_dict = health_data.model_dump()
    health_dict.update({"details": details_json, "created_at": datetime.now(timezone.utc)})

    # Đảm bảo checked_at luôn có giá trị
    if not health_dict.get("checked_at"):
        health_dict["checked_at"] = datetime.now(timezone.utc)

    # Tạo trạng thái mới
    try:
        created_health = SystemHealthRepository.create(db, health_dict)

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="CREATE",
                        entity_type="SYSTEM_HEALTH",
                        entity_id=created_health.id,
                        description=f"Created new system health record for component {created_health.component}",
                        metadata={
                            "component": created_health.component,
                            "status": created_health.status,
                            "checked_at": (
                                created_health.checked_at.isoformat()
                                if created_health.checked_at
                                else None
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return created_health
    except Exception as e:
        logger.error(f"Lỗi khi tạo trạng thái sức khỏe hệ thống: {str(e)}")
        raise ServerException(
            detail=f"Không thể tạo trạng thái sức khỏe hệ thống: {str(e)}"
        )


@invalidate_cache(tags=["system_health"])
def update_system_health(
    db: Session,
    health_id: int,
    health_data: SystemHealthUpdate,
    admin_id: Optional[int] = None,
) -> SystemHealth:
    """
    Cập nhật thông tin trạng thái sức khỏe hệ thống.

    Args:
        db: Database session
        health_id: ID trạng thái
        health_data: Thông tin cập nhật
        admin_id: ID của admin thực hiện hành động

    Returns:
        SystemHealth object đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy trạng thái
        BadRequestException: Nếu dữ liệu không hợp lệ
        ServerException: Nếu có lỗi khác
    """
    # Kiểm tra trạng thái tồn tại
    health = SystemHealthRepository.get_by_id(db, health_id)
    if not health:
        logger.warning(
            f"Không tìm thấy trạng thái sức khỏe hệ thống với ID={health_id}"
        )
        raise NotFoundException(
            detail=f"Không tìm thấy trạng thái sức khỏe hệ thống với ID={health_id}"
        )

    # Xử lý details nếu có
    if health_data.details is not None:
        try:
            # Kiểm tra nếu là chuỗi JSON
            if isinstance(health_data.details, str):
                json.loads(health_data.details)  # Chỉ để kiểm tra
            else:
                # Chuyển đổi đối tượng thành chuỗi JSON
                health_data.details = json.dumps(health_data.details)
        except json.JSONDecodeError:
            logger.error(f"Chi tiết không phải là JSON hợp lệ")
            raise BadRequestException(detail="Chi tiết không phải là JSON hợp lệ")

    # Kiểm tra trạng thái hợp lệ nếu có
    if health_data.status:
        valid_statuses = ["healthy", "warning", "critical"]
        if health_data.status not in valid_statuses:
            raise BadRequestException(
                detail=f"Trạng thái không hợp lệ. Chọn một trong: {', '.join(valid_statuses)}"
            )

    # Chuẩn bị dữ liệu cập nhật
    update_data = health_data.model_dump(exclude_unset=True)

    # Cập nhật trạng thái
    try:
        updated_health = SystemHealthRepository.update(db, health_id, update_data)
        if not updated_health:
            raise ServerException(
                detail=f"Không thể cập nhật trạng thái sức khỏe hệ thống với ID={health_id}"
            )

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="SYSTEM_HEALTH",
                        entity_id=health_id,
                        description=f"Updated system health record for component {updated_health.component}",
                        metadata={
                            "component": updated_health.component,
                            "previous_status": health.status,
                            "new_status": updated_health.status,
                            "checked_at": (
                                updated_health.checked_at.isoformat()
                                if updated_health.checked_at
                                else None
                            ),
                            "updates": {
                                k: v for k, v in update_data.items() if k != "details"
                            },
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return updated_health
    except Exception as e:
        if isinstance(e, (NotFoundException, BadRequestException, ServerException)):
            raise e

        logger.error(f"Lỗi khi cập nhật trạng thái sức khỏe hệ thống: {str(e)}")
        raise ServerException(
            detail=f"Không thể cập nhật trạng thái sức khỏe hệ thống: {str(e)}"
        )


@invalidate_cache(tags=["system_health"])
def delete_system_health(
    db: Session, health_id: int, admin_id: Optional[int] = None
) -> bool:
    """
    Xóa trạng thái sức khỏe hệ thống.

    Args:
        db: Database session
        health_id: ID trạng thái
        admin_id: ID của admin thực hiện hành động

    Returns:
        True nếu xóa thành công

    Raises:
        NotFoundException: Nếu không tìm thấy trạng thái
        ServerException: Nếu có lỗi khác
    """
    # Kiểm tra trạng thái tồn tại
    health = SystemHealthRepository.get_by_id(db, health_id)
    if not health:
        logger.warning(
            f"Không tìm thấy trạng thái sức khỏe hệ thống với ID={health_id}"
        )
        raise NotFoundException(
            detail=f"Không tìm thấy trạng thái sức khỏe hệ thống với ID={health_id}"
        )

    # Log admin activity before deletion
    if admin_id:
        try:
            create_admin_activity_log(
                db,
                AdminActivityLogCreate(
                    admin_id=admin_id,
                    activity_type="DELETE",
                    entity_type="SYSTEM_HEALTH",
                    entity_id=health_id,
                    description=f"Deleted system health record for component {health.component}",
                    metadata={
                        "component": health.component,
                        "status": health.status,
                        "checked_at": (
                            health.checked_at.isoformat() if health.checked_at else None
                        ),
                    },
                ),
            )
        except Exception as e:
            logger.error(f"Failed to log admin activity: {str(e)}")

    # Xóa trạng thái
    try:
        success = SystemHealthRepository.delete(db, health_id)
        if not success:
            raise ServerException(
                detail=f"Không thể xóa trạng thái sức khỏe hệ thống với ID={health_id}"
            )

        return True
    except Exception as e:
        if isinstance(e, (NotFoundException, ServerException)):
            raise e

        logger.error(f"Lỗi khi xóa trạng thái sức khỏe hệ thống: {str(e)}")
        raise ServerException(
            detail=f"Không thể xóa trạng thái sức khỏe hệ thống: {str(e)}"
        )
