from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import json

from app.admin_site.models import SystemSetting
from app.admin_site.schemas.system_setting import (
    SystemSettingCreate,
    SystemSettingUpdate,
)
from app.admin_site.repositories.system_setting_repo import SystemSettingRepository
from app.cache.decorators import cached, invalidate_cache
from app.core.exceptions import (
    NotFoundException,
    ConflictException,
    ServerException,
    BadRequestException,
)
from app.logging.setup import get_logger
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate

logger = get_logger(__name__)


@cached(ttl=3600, namespace="admin:system_settings", tags=["system_settings"])
def get_all_system_settings(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    group: Optional[str] = None,
    is_public: Optional[bool] = None,
    order_by: str = "key",
    order_desc: bool = False,
    admin_id: Optional[int] = None,
) -> List[SystemSetting]:
    """
    Lấy danh sách cài đặt hệ thống.

    Args:
        db: Database session
        skip: Số lượng bản ghi bỏ qua
        limit: Số lượng bản ghi tối đa
        search: Tìm kiếm theo key hoặc description
        group: Lọc theo nhóm
        is_public: Lọc theo trạng thái public
        order_by: Trường sắp xếp
        order_desc: Sắp xếp giảm dần
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách cài đặt hệ thống
    """
    try:
        results = SystemSettingRepository.get_all(
            db, skip, limit, search, group, is_public, order_by, order_desc
        )

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="SYSTEM_SETTINGS",
                        entity_id=0,
                        description="Viewed system settings list",
                        metadata={
                            "skip": skip,
                            "limit": limit,
                            "search": search,
                            "group": group,
                            "is_public": is_public,
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
        logger.error(f"Lỗi khi lấy danh sách cài đặt hệ thống: {str(e)}")
        raise ServerException(
            detail=f"Lỗi khi lấy danh sách cài đặt hệ thống: {str(e)}"
        )


def count_system_settings(
    db: Session,
    search: Optional[str] = None,
    group: Optional[str] = None,
    is_public: Optional[bool] = None,
) -> int:
    """
    Đếm số lượng cài đặt hệ thống.

    Args:
        db: Database session
        search: Tìm kiếm theo key hoặc description
        group: Lọc theo nhóm
        is_public: Lọc theo trạng thái public

    Returns:
        Tổng số cài đặt hệ thống
    """
    try:
        return SystemSettingRepository.count(db, search, group, is_public)
    except Exception as e:
        logger.error(f"Lỗi khi đếm cài đặt hệ thống: {str(e)}")
        raise ServerException(detail=f"Lỗi khi đếm cài đặt hệ thống: {str(e)}")


@cached(ttl=3600, namespace="admin:system_settings", tags=["system_settings"])
def get_system_setting_by_id(
    db: Session, setting_id: int, admin_id: Optional[int] = None
) -> SystemSetting:
    """
    Lấy thông tin cài đặt hệ thống theo ID.

    Args:
        db: Database session
        setting_id: ID cài đặt
        admin_id: ID của admin thực hiện hành động

    Returns:
        SystemSetting object

    Raises:
        NotFoundException: Nếu không tìm thấy cài đặt
    """
    setting = SystemSettingRepository.get_by_id(db, setting_id)
    if not setting:
        logger.warning(f"Không tìm thấy cài đặt hệ thống với ID={setting_id}")
        raise NotFoundException(
            detail=f"Không tìm thấy cài đặt hệ thống với ID={setting_id}"
        )

    # Log admin activity
    if admin_id:
        try:
            create_admin_activity_log(
                db,
                AdminActivityLogCreate(
                    admin_id=admin_id,
                    activity_type="VIEW",
                    entity_type="SYSTEM_SETTING",
                    entity_id=setting_id,
                    description=f"Viewed system setting: {setting.key}",
                    metadata={
                        "key": setting.key,
                        "group": setting.group,
                        "is_public": setting.is_public,
                        "data_type": setting.data_type,
                    },
                ),
            )
        except Exception as e:
            logger.error(f"Failed to log admin activity: {str(e)}")

    return setting


@cached(ttl=3600, namespace="admin:system_settings", tags=["system_settings"])
def get_system_setting_by_key(
    db: Session, key: str, admin_id: Optional[int] = None
) -> SystemSetting:
    """
    Lấy thông tin cài đặt hệ thống theo key.

    Args:
        db: Database session
        key: Key cài đặt
        admin_id: ID của admin thực hiện hành động

    Returns:
        SystemSetting object

    Raises:
        NotFoundException: Nếu không tìm thấy cài đặt
    """
    setting = SystemSettingRepository.get_by_key(db, key)
    if not setting:
        logger.warning(f"Không tìm thấy cài đặt hệ thống với key={key}")
        raise NotFoundException(detail=f"Không tìm thấy cài đặt hệ thống với key={key}")

    # Log admin activity
    if admin_id:
        try:
            create_admin_activity_log(
                db,
                AdminActivityLogCreate(
                    admin_id=admin_id,
                    activity_type="VIEW",
                    entity_type="SYSTEM_SETTING",
                    entity_id=setting.id,
                    description=f"Viewed system setting by key: {key}",
                    metadata={
                        "key": setting.key,
                        "group": setting.group,
                        "is_public": setting.is_public,
                        "data_type": setting.data_type,
                    },
                ),
            )
        except Exception as e:
            logger.error(f"Failed to log admin activity: {str(e)}")

    return setting


@cached(ttl=3600, namespace="admin:system_settings:groups", tags=["system_settings"])
def get_setting_groups(db: Session, admin_id: Optional[int] = None) -> List[str]:
    """
    Lấy danh sách các nhóm cài đặt.

    Args:
        db: Database session
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách các nhóm cài đặt
    """
    try:
        groups = SystemSettingRepository.get_groups(db)

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="SYSTEM_SETTING_GROUPS",
                        entity_id=0,
                        description="Viewed system setting groups",
                        metadata={"group_count": len(groups)},
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return groups
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách nhóm cài đặt: {str(e)}")
        raise ServerException(detail=f"Lỗi khi lấy danh sách nhóm cài đặt: {str(e)}")


@cached(ttl=3600, namespace="admin:system_settings:group", tags=["system_settings"])
def get_settings_by_group(
    db: Session, group: str, admin_id: Optional[int] = None
) -> List[SystemSetting]:
    """
    Lấy danh sách cài đặt theo nhóm.

    Args:
        db: Database session
        group: Tên nhóm
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách cài đặt hệ thống
    """
    try:
        settings = SystemSettingRepository.get_by_group(db, group)

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="SYSTEM_SETTINGS_BY_GROUP",
                        entity_id=0,
                        description=f"Viewed system settings for group: {group}",
                        metadata={"group": group, "settings_count": len(settings)},
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return settings
    except Exception as e:
        logger.error(f"Lỗi khi lấy cài đặt theo nhóm: {str(e)}")
        raise ServerException(detail=f"Lỗi khi lấy cài đặt theo nhóm: {str(e)}")


@invalidate_cache(tags=["system_settings"])
def create_system_setting(
    db: Session, setting_data: SystemSettingCreate, admin_id: Optional[int] = None
) -> SystemSetting:
    """
    Tạo cài đặt hệ thống mới.

    Args:
        db: Database session
        setting_data: Thông tin cài đặt mới
        admin_id: ID của admin thực hiện hành động

    Returns:
        SystemSetting object đã tạo

    Raises:
        ConflictException: Nếu key đã tồn tại
        BadRequestException: Nếu dữ liệu không hợp lệ
        ServerException: Nếu có lỗi khác
    """
    # Kiểm tra key đã tồn tại chưa
    existing_setting = SystemSettingRepository.get_by_key(db, setting_data.key)
    if existing_setting:
        logger.warning(f"Key cài đặt đã tồn tại: {setting_data.key}")
        raise ConflictException(detail="Key cài đặt đã tồn tại", field="key")

    # Kiểm tra data_type và value phù hợp
    try:
        validate_setting_value(setting_data.value, setting_data.data_type)
    except ValueError as e:
        raise BadRequestException(detail=str(e))

    # Chuẩn bị dữ liệu
    setting_dict = setting_data.model_dump()
    setting_dict.update(
        {"created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)}
    )

    # Tạo cài đặt mới
    try:
        created_setting = SystemSettingRepository.create(db, setting_dict)

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="CREATE",
                        entity_type="SYSTEM_SETTING",
                        entity_id=created_setting.id,
                        description=f"Created new system setting: {created_setting.key}",
                        metadata={
                            "key": created_setting.key,
                            "group": created_setting.group,
                            "is_public": created_setting.is_public,
                            "data_type": created_setting.data_type,
                            "description": created_setting.description,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return created_setting
    except Exception as e:
        logger.error(f"Lỗi khi tạo cài đặt hệ thống: {str(e)}")
        raise ServerException(detail=f"Không thể tạo cài đặt hệ thống: {str(e)}")


@invalidate_cache(tags=["system_settings"])
def update_system_setting(
    db: Session,
    setting_id: int,
    setting_data: SystemSettingUpdate,
    admin_id: Optional[int] = None,
) -> SystemSetting:
    """
    Cập nhật thông tin cài đặt hệ thống.

    Args:
        db: Database session
        setting_id: ID cài đặt
        setting_data: Thông tin cập nhật
        admin_id: ID của admin thực hiện hành động

    Returns:
        SystemSetting object đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy cài đặt
        BadRequestException: Nếu dữ liệu không hợp lệ
        ServerException: Nếu có lỗi khác
    """
    # Kiểm tra cài đặt tồn tại
    setting = SystemSettingRepository.get_by_id(db, setting_id)
    if not setting:
        logger.warning(f"Không tìm thấy cài đặt hệ thống với ID={setting_id}")
        raise NotFoundException(
            detail=f"Không tìm thấy cài đặt hệ thống với ID={setting_id}"
        )

    # Kiểm tra data_type và value phù hợp nếu có
    data_type = setting_data.data_type or setting.data_type
    value = setting_data.value

    if value is not None:
        try:
            validate_setting_value(value, data_type)
        except ValueError as e:
            raise BadRequestException(detail=str(e))

    # Chuẩn bị dữ liệu cập nhật
    update_data = setting_data.model_dump(exclude_unset=True)
    update_data["updated_at"] = datetime.now(timezone.utc)

    # Cập nhật cài đặt
    try:
        updated_setting = SystemSettingRepository.update(db, setting_id, update_data)
        if not updated_setting:
            raise ServerException(
                detail=f"Không thể cập nhật cài đặt hệ thống với ID={setting_id}"
            )

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="SYSTEM_SETTING",
                        entity_id=setting_id,
                        description=f"Updated system setting: {setting.key}",
                        metadata={
                            "key": setting.key,
                            "previous_value": setting.value,
                            "new_value": (
                                updated_setting.value
                                if hasattr(updated_setting, "value")
                                and updated_setting.value != setting.value
                                else None
                            ),
                            "updates": {
                                k: v
                                for k, v in update_data.items()
                                if k not in ["updated_at"]
                            },
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return updated_setting
    except Exception as e:
        if isinstance(e, (NotFoundException, BadRequestException, ServerException)):
            raise e

        logger.error(f"Lỗi khi cập nhật cài đặt hệ thống: {str(e)}")
        raise ServerException(detail=f"Không thể cập nhật cài đặt hệ thống: {str(e)}")


@invalidate_cache(tags=["system_settings"])
def update_setting_by_key(
    db: Session, key: str, value: str, admin_id: Optional[int] = None
) -> SystemSetting:
    """
    Cập nhật giá trị cài đặt hệ thống theo key.

    Args:
        db: Database session
        key: Key cài đặt
        value: Giá trị mới
        admin_id: ID của admin thực hiện hành động

    Returns:
        SystemSetting object đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy cài đặt
        BadRequestException: Nếu dữ liệu không hợp lệ
        ServerException: Nếu có lỗi khác
    """
    # Kiểm tra cài đặt tồn tại
    setting = SystemSettingRepository.get_by_key(db, key)
    if not setting:
        logger.warning(f"Không tìm thấy cài đặt hệ thống với key={key}")
        raise NotFoundException(detail=f"Không tìm thấy cài đặt hệ thống với key={key}")

    # Kiểm tra value phù hợp với data_type
    try:
        validate_setting_value(value, setting.data_type)
    except ValueError as e:
        raise BadRequestException(detail=str(e))

    # Cập nhật cài đặt
    try:
        updated_setting = SystemSettingRepository.update_by_key(db, key, value)
        if not updated_setting:
            raise ServerException(
                detail=f"Không thể cập nhật cài đặt hệ thống với key={key}"
            )

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="SYSTEM_SETTING",
                        entity_id=setting.id,
                        description=f"Updated system setting by key: {key}",
                        metadata={
                            "key": key,
                            "previous_value": setting.value,
                            "new_value": value,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return updated_setting
    except Exception as e:
        if isinstance(e, (NotFoundException, BadRequestException, ServerException)):
            raise e

        logger.error(f"Lỗi khi cập nhật cài đặt hệ thống: {str(e)}")
        raise ServerException(detail=f"Không thể cập nhật cài đặt hệ thống: {str(e)}")


@invalidate_cache(tags=["system_settings"])
def delete_system_setting(
    db: Session, setting_id: int, admin_id: Optional[int] = None
) -> bool:
    """
    Xóa cài đặt hệ thống.

    Args:
        db: Database session
        setting_id: ID cài đặt
        admin_id: ID của admin thực hiện hành động

    Returns:
        True nếu xóa thành công

    Raises:
        NotFoundException: Nếu không tìm thấy cài đặt
        ServerException: Nếu có lỗi khác
    """
    # Kiểm tra cài đặt tồn tại
    setting = SystemSettingRepository.get_by_id(db, setting_id)
    if not setting:
        logger.warning(f"Không tìm thấy cài đặt hệ thống với ID={setting_id}")
        raise NotFoundException(
            detail=f"Không tìm thấy cài đặt hệ thống với ID={setting_id}"
        )

    # Log admin activity before deletion
    if admin_id:
        try:
            create_admin_activity_log(
                db,
                AdminActivityLogCreate(
                    admin_id=admin_id,
                    activity_type="DELETE",
                    entity_type="SYSTEM_SETTING",
                    entity_id=setting_id,
                    description=f"Deleted system setting: {setting.key}",
                    metadata={
                        "key": setting.key,
                        "group": setting.group,
                        "data_type": setting.data_type,
                        "value": setting.value,
                    },
                ),
            )
        except Exception as e:
            logger.error(f"Failed to log admin activity: {str(e)}")

    # Xóa cài đặt
    try:
        success = SystemSettingRepository.delete(db, setting_id)
        if not success:
            raise ServerException(
                detail=f"Không thể xóa cài đặt hệ thống với ID={setting_id}"
            )

        return True
    except Exception as e:
        if isinstance(e, (NotFoundException, ServerException)):
            raise e

        logger.error(f"Lỗi khi xóa cài đặt hệ thống: {str(e)}")
        raise ServerException(detail=f"Không thể xóa cài đặt hệ thống: {str(e)}")


def validate_setting_value(value: str, data_type: str) -> None:
    """
    Kiểm tra value phù hợp với data_type.

    Args:
        value: Giá trị cần kiểm tra
        data_type: Kiểu dữ liệu

    Raises:
        ValueError: Nếu value không phù hợp với data_type
    """
    if data_type == "string":
        # String luôn hợp lệ
        pass
    elif data_type == "integer":
        try:
            int(value)
        except ValueError:
            raise ValueError(f"Giá trị '{value}' không phải là kiểu integer")
    elif data_type == "float":
        try:
            float(value)
        except ValueError:
            raise ValueError(f"Giá trị '{value}' không phải là kiểu float")
    elif data_type == "boolean":
        if value.lower() not in ["true", "false", "1", "0"]:
            raise ValueError(f"Giá trị '{value}' không phải là kiểu boolean")
    elif data_type == "json":
        try:
            json.loads(value)
        except json.JSONDecodeError:
            raise ValueError(f"Giá trị '{value}' không phải là JSON hợp lệ")
    else:
        raise ValueError(f"Kiểu dữ liệu '{data_type}' không được hỗ trợ")
