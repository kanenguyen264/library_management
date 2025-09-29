from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import json

from app.admin_site.models import Permission, RolePermission
from app.admin_site.schemas.permission import PermissionCreate, PermissionUpdate
from app.admin_site.repositories.permission_repo import PermissionRepository
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


@cached(ttl=3600, namespace="admin:permissions", tags=["permissions"])
def get_all_permissions(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    resource: Optional[str] = None,
    order_by: str = "name",
    order_desc: bool = False,
    admin_id: Optional[int] = None,
) -> List[Permission]:
    """
    Lấy danh sách quyền.

    Args:
        db: Database session
        skip: Số lượng bản ghi bỏ qua
        limit: Số lượng bản ghi tối đa
        search: Tìm kiếm theo tên
        resource: Lọc theo resource
        order_by: Trường sắp xếp
        order_desc: Sắp xếp giảm dần
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách quyền
    """
    try:
        permissions = PermissionRepository.get_all(
            db, skip, limit, search, resource, order_by, order_desc
        )

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="PERMISSIONS",
                        entity_id=0,
                        description="Viewed permissions list",
                        metadata={
                            "skip": skip,
                            "limit": limit,
                            "search": search,
                            "resource": resource,
                            "order_by": order_by,
                            "order_desc": order_desc,
                            "results_count": len(permissions),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return permissions
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách quyền: {str(e)}")
        raise ServerException(detail=f"Lỗi khi lấy danh sách quyền: {str(e)}")


def count_permissions(
    db: Session,
    search: Optional[str] = None,
    resource: Optional[str] = None,
    action: Optional[str] = None,
) -> int:
    """
    Đếm số lượng quyền.

    Args:
        db: Database session
        search: Tìm kiếm theo tên
        resource: Lọc theo resource
        action: Lọc theo action

    Returns:
        Tổng số quyền
    """
    try:
        return PermissionRepository.count(db, search, resource, action)
    except Exception as e:
        logger.error(f"Lỗi khi đếm quyền: {str(e)}")
        raise ServerException(detail=f"Lỗi khi đếm quyền: {str(e)}")


@cached(ttl=3600, namespace="admin:permissions", tags=["permissions"])
def get_permission_by_id(
    db: Session, permission_id: int, admin_id: Optional[int] = None
) -> Permission:
    """
    Lấy thông tin quyền theo ID.

    Args:
        db: Database session
        permission_id: ID quyền
        admin_id: ID của admin thực hiện hành động

    Returns:
        Permission object

    Raises:
        NotFoundException: Nếu không tìm thấy quyền
    """
    permission = PermissionRepository.get_by_id(db, permission_id)
    if not permission:
        logger.warning(f"Không tìm thấy quyền với ID={permission_id}")
        raise NotFoundException(detail=f"Không tìm thấy quyền với ID={permission_id}")

    # Log admin activity
    if admin_id:
        try:
            create_admin_activity_log(
                db,
                AdminActivityLogCreate(
                    admin_id=admin_id,
                    activity_type="VIEW",
                    entity_type="PERMISSION",
                    entity_id=permission_id,
                    description=f"Viewed permission details: {permission.name}",
                    metadata={
                        "name": permission.name,
                        "description": permission.description,
                        "resource": permission.resource,
                        "action": permission.action,
                    },
                ),
            )
        except Exception as e:
            logger.error(f"Failed to log admin activity: {str(e)}")

    return permission


@cached(ttl=3600, namespace="admin:permissions:resources", tags=["permissions"])
def get_permission_resources(db: Session, admin_id: Optional[int] = None) -> List[str]:
    """
    Lấy danh sách các resource.

    Args:
        db: Database session
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách các resource
    """
    try:
        resources = PermissionRepository.get_resources(db)

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="PERMISSION_RESOURCES",
                        entity_id=0,
                        description="Viewed permission resources list",
                        metadata={"resources_count": len(resources)},
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return resources
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách resource: {str(e)}")
        raise ServerException(detail=f"Lỗi khi lấy danh sách resource: {str(e)}")


@cached(ttl=3600, namespace="admin:permissions:actions", tags=["permissions"])
def get_permission_actions(db: Session, resource: Optional[str] = None) -> List[str]:
    """
    Lấy danh sách các action có quyền.

    Args:
        db: Database session
        resource: Lọc theo resource

    Returns:
        Danh sách các action
    """
    try:
        return PermissionRepository.get_actions(db, resource)
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách action: {str(e)}")
        raise ServerException(detail=f"Lỗi khi lấy danh sách action: {str(e)}")


@invalidate_cache(tags=["permissions"])
def create_permission(
    db: Session, permission_data: PermissionCreate, admin_id: Optional[int] = None
) -> Permission:
    """
    Tạo quyền mới.

    Args:
        db: Database session
        permission_data: Thông tin quyền mới
        admin_id: ID của admin thực hiện hành động

    Returns:
        Permission object đã tạo

    Raises:
        ConflictException: Nếu tên quyền hoặc resource+action đã tồn tại
        ServerException: Nếu có lỗi khác
    """
    # Kiểm tra tên đã tồn tại chưa
    existing_permission = PermissionRepository.get_by_name(db, permission_data.name)
    if existing_permission:
        logger.warning(f"Tên quyền đã tồn tại: {permission_data.name}")
        raise ConflictException(detail="Tên quyền đã tồn tại", field="name")

    # Kiểm tra resource+action đã tồn tại chưa
    conditions = {
        "resource": permission_data.resource,
        "action": permission_data.action,
    }

    existing_permissions = PermissionRepository.get_by_conditions(db, conditions)
    if existing_permissions:
        logger.warning(
            f"Quyền với resource='{permission_data.resource}' và action='{permission_data.action}' đã tồn tại"
        )
        raise ConflictException(
            detail=f"Quyền với resource='{permission_data.resource}' và action='{permission_data.action}' đã tồn tại",
            field="resource,action",
        )

    # Chuẩn bị dữ liệu
    permission_dict = permission_data.model_dump()
    permission_dict.update(
        {"created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)}
    )

    # Tạo quyền mới
    try:
        created_permission = PermissionRepository.create(db, permission_dict)

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="CREATE",
                        entity_type="PERMISSION",
                        entity_id=created_permission.id,
                        description=f"Created new permission: {created_permission.name}",
                        metadata={
                            "name": created_permission.name,
                            "description": created_permission.description,
                            "resource": created_permission.resource,
                            "action": created_permission.action,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return created_permission
    except Exception as e:
        logger.error(f"Lỗi khi tạo quyền: {str(e)}")
        raise ServerException(detail=f"Không thể tạo quyền: {str(e)}")


@invalidate_cache(tags=["permissions"])
def update_permission(
    db: Session,
    permission_id: int,
    permission_data: PermissionUpdate,
    admin_id: Optional[int] = None,
) -> Permission:
    """
    Cập nhật thông tin quyền.

    Args:
        db: Database session
        permission_id: ID quyền
        permission_data: Thông tin cập nhật
        admin_id: ID của admin thực hiện hành động

    Returns:
        Permission object đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy quyền
        ConflictException: Nếu tên quyền hoặc resource+action đã tồn tại
        ServerException: Nếu có lỗi khác
    """
    # Kiểm tra quyền tồn tại
    permission = PermissionRepository.get_by_id(db, permission_id)
    if not permission:
        logger.warning(f"Không tìm thấy quyền với ID={permission_id}")
        raise NotFoundException(detail=f"Không tìm thấy quyền với ID={permission_id}")

    # Kiểm tra tên đã tồn tại chưa nếu có thay đổi tên
    if permission_data.name and permission_data.name != permission.name:
        existing_permission = PermissionRepository.get_by_name(db, permission_data.name)
        if existing_permission and existing_permission.id != permission_id:
            logger.warning(f"Tên quyền đã tồn tại: {permission_data.name}")
            raise ConflictException(detail="Tên quyền đã tồn tại", field="name")

    # Kiểm tra resource+action đã tồn tại chưa nếu có thay đổi
    if (
        permission_data.resource and permission_data.resource != permission.resource
    ) or (permission_data.action and permission_data.action != permission.action):

        resource = permission_data.resource or permission.resource
        action = permission_data.action or permission.action

        conditions = {"resource": resource, "action": action}

        existing_permissions = PermissionRepository.get_by_conditions(db, conditions)
        if existing_permissions:
            for existing in existing_permissions:
                if existing.id != permission_id:
                    logger.warning(
                        f"Quyền với resource='{resource}' và action='{action}' đã tồn tại"
                    )
                    raise ConflictException(
                        detail=f"Quyền với resource='{resource}' và action='{action}' đã tồn tại",
                        field="resource,action",
                    )

    # Chuẩn bị dữ liệu cập nhật
    update_data = permission_data.model_dump(exclude_unset=True)
    update_data["updated_at"] = datetime.now(timezone.utc)

    # Lưu thông tin trước khi cập nhật cho việc ghi log
    previous_data = {
        "name": permission.name,
        "description": permission.description,
        "resource": permission.resource,
        "action": permission.action,
    }

    # Cập nhật quyền
    try:
        updated_permission = PermissionRepository.update(db, permission_id, update_data)
        if not updated_permission:
            raise ServerException(
                detail=f"Không thể cập nhật quyền với ID={permission_id}"
            )

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="PERMISSION",
                        entity_id=permission_id,
                        description=f"Updated permission: {permission.name}",
                        metadata={
                            "previous": previous_data,
                            "updated": {
                                k: v
                                for k, v in update_data.items()
                                if k != "updated_at"
                            },
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return updated_permission
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

        logger.error(f"Lỗi khi cập nhật quyền: {str(e)}")
        raise ServerException(detail=f"Không thể cập nhật quyền: {str(e)}")


@invalidate_cache(tags=["permissions"])
def delete_permission(
    db: Session, permission_id: int, admin_id: Optional[int] = None
) -> bool:
    """
    Xóa quyền.

    Args:
        db: Database session
        permission_id: ID quyền
        admin_id: ID của admin thực hiện hành động

    Returns:
        True nếu xóa thành công

    Raises:
        NotFoundException: Nếu không tìm thấy quyền
        BadRequestException: Nếu quyền đang được sử dụng
        ServerException: Nếu có lỗi khác
    """
    # Kiểm tra quyền tồn tại
    permission = PermissionRepository.get_by_id(db, permission_id)
    if not permission:
        logger.warning(f"Không tìm thấy quyền với ID={permission_id}")
        raise NotFoundException(detail=f"Không tìm thấy quyền với ID={permission_id}")

    # Kiểm tra xem quyền có đang được sử dụng không
    # Đây là kiểm tra đơn giản, có thể cần kiểm tra nhiều hơn
    roles_with_permission = (
        db.query(RolePermission)
        .filter(RolePermission.permission_id == permission_id)
        .count()
    )

    if roles_with_permission > 0:
        logger.warning(
            f"Quyền với ID={permission_id} đang được gán cho {roles_with_permission} role"
        )
        raise BadRequestException(
            detail=f"Không thể xóa quyền vì đang được gán cho {roles_with_permission} role"
        )

    # Log admin activity before deletion
    if admin_id:
        try:
            create_admin_activity_log(
                db,
                AdminActivityLogCreate(
                    admin_id=admin_id,
                    activity_type="DELETE",
                    entity_type="PERMISSION",
                    entity_id=permission_id,
                    description=f"Deleted permission: {permission.name}",
                    metadata={
                        "name": permission.name,
                        "description": permission.description,
                        "resource": permission.resource,
                        "action": permission.action,
                    },
                ),
            )
        except Exception as e:
            logger.error(f"Failed to log admin activity: {str(e)}")

    # Xóa quyền
    try:
        success = PermissionRepository.delete(db, permission_id)
        if not success:
            raise ServerException(detail=f"Không thể xóa quyền với ID={permission_id}")

        return True
    except Exception as e:
        if isinstance(e, (NotFoundException, BadRequestException, ServerException)):
            raise e

        logger.error(f"Lỗi khi xóa quyền: {str(e)}")
        raise ServerException(detail=f"Không thể xóa quyền: {str(e)}")
