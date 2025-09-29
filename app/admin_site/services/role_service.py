from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import json

from app.admin_site.models import Role, Permission, RolePermission
from app.admin_site.schemas.role import RoleCreate, RoleUpdate
from app.admin_site.repositories.role_repo import RoleRepository
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


@cached(ttl=3600, namespace="admin:roles", tags=["roles"])
def get_all_roles(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    order_by: str = "name",
    order_desc: bool = False,
    admin_id: Optional[int] = None,
) -> List[Role]:
    """
    Lấy danh sách role.

    Args:
        db: Database session
        skip: Số lượng bản ghi bỏ qua
        limit: Số lượng bản ghi tối đa
        search: Tìm kiếm theo tên
        order_by: Sắp xếp theo trường
        order_desc: Sắp xếp giảm dần
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách role
    """
    try:
        roles = RoleRepository.get_all(db, skip, limit, search, order_by, order_desc)

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="ROLES",
                        entity_id=0,
                        description="Viewed roles list",
                        metadata={
                            "skip": skip,
                            "limit": limit,
                            "search": search,
                            "order_by": order_by,
                            "order_desc": order_desc,
                            "results_count": len(roles),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return roles
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách role: {str(e)}")
        raise ServerException(detail=f"Lỗi khi lấy danh sách role: {str(e)}")


def count_roles(db: Session, search: Optional[str] = None) -> int:
    """
    Đếm số lượng role.

    Args:
        db: Database session
        search: Tìm kiếm theo tên

    Returns:
        Tổng số role
    """
    try:
        return RoleRepository.count(db, search)
    except Exception as e:
        logger.error(f"Lỗi khi đếm role: {str(e)}")
        raise ServerException(detail=f"Lỗi khi đếm role: {str(e)}")


@cached(ttl=3600, namespace="admin:roles", tags=["roles"])
def get_role_by_id(db: Session, role_id: int, admin_id: Optional[int] = None) -> Role:
    """
    Lấy thông tin role theo ID.

    Args:
        db: Database session
        role_id: ID role
        admin_id: ID của admin thực hiện hành động

    Returns:
        Role object

    Raises:
        NotFoundException: Nếu không tìm thấy role
    """
    role = RoleRepository.get_by_id(db, role_id)
    if not role:
        logger.warning(f"Không tìm thấy role với ID={role_id}")
        raise NotFoundException(detail=f"Không tìm thấy role với ID={role_id}")

    # Log admin activity
    if admin_id:
        try:
            permissions_count = (
                len(role.permissions) if hasattr(role, "permissions") else 0
            )

            create_admin_activity_log(
                db,
                AdminActivityLogCreate(
                    admin_id=admin_id,
                    activity_type="VIEW",
                    entity_type="ROLE",
                    entity_id=role_id,
                    description=f"Viewed role details: {role.name}",
                    metadata={
                        "name": role.name,
                        "description": role.description,
                        "permissions_count": permissions_count,
                    },
                ),
            )
        except Exception as e:
            logger.error(f"Failed to log admin activity: {str(e)}")

    return role


@cached(ttl=3600, namespace="admin:roles", tags=["roles"])
def get_role_by_name(db: Session, name: str) -> Optional[Role]:
    """
    Lấy thông tin role theo tên.

    Args:
        db: Database session
        name: Tên role

    Returns:
        Role object hoặc None nếu không tìm thấy
    """
    return RoleRepository.get_by_name(db, name)


@invalidate_cache(tags=["roles"])
def create_role(
    db: Session, role_data: RoleCreate, admin_id: Optional[int] = None
) -> Role:
    """
    Tạo role mới.

    Args:
        db: Database session
        role_data: Thông tin role mới
        admin_id: ID của admin thực hiện hành động

    Returns:
        Role object đã tạo

    Raises:
        ConflictException: Nếu tên role đã tồn tại
        BadRequestException: Nếu dữ liệu không hợp lệ
        ServerException: Nếu có lỗi khác
    """
    # Kiểm tra tên role đã tồn tại chưa
    existing_role = RoleRepository.get_by_name(db, role_data.name)
    if existing_role:
        logger.warning(f"Tên role đã tồn tại: {role_data.name}")
        raise ConflictException(detail="Tên role đã tồn tại", field="name")

    # Kiểm tra permissions tồn tại
    if role_data.permission_ids:
        for permission_id in role_data.permission_ids:
            permission = PermissionRepository.get_by_id(db, permission_id)
            if not permission:
                raise BadRequestException(
                    detail=f"Không tìm thấy quyền với ID={permission_id}",
                    field="permission_ids",
                )

    # Chuẩn bị dữ liệu
    role_dict = role_data.model_dump(exclude={"permission_ids"})
    role_dict.update({"created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)})

    # Tạo role mới
    try:
        created_role = RoleRepository.create(db, role_dict)

        # Gán quyền cho role
        if role_data.permission_ids:
            for permission_id in role_data.permission_ids:
                RoleRepository.add_permission(db, created_role.id, permission_id)

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="CREATE",
                        entity_type="ROLE",
                        entity_id=created_role.id,
                        description=f"Created new role: {created_role.name}",
                        metadata={
                            "name": created_role.name,
                            "description": created_role.description,
                            "permission_ids": (
                                role_data.permission_ids
                                if role_data.permission_ids
                                else []
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return created_role
    except Exception as e:
        logger.error(f"Lỗi khi tạo role: {str(e)}")
        raise ServerException(detail=f"Không thể tạo role: {str(e)}")


@invalidate_cache(tags=["roles"])
def update_role(
    db: Session, role_id: int, role_data: RoleUpdate, admin_id: Optional[int] = None
) -> Role:
    """
    Cập nhật thông tin role.

    Args:
        db: Database session
        role_id: ID role
        role_data: Thông tin cập nhật
        admin_id: ID của admin thực hiện hành động

    Returns:
        Role object đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy role
        ConflictException: Nếu tên role đã tồn tại
        BadRequestException: Nếu dữ liệu không hợp lệ
        ServerException: Nếu có lỗi khác
    """
    # Kiểm tra role tồn tại
    role = RoleRepository.get_by_id(db, role_id)
    if not role:
        logger.warning(f"Không tìm thấy role với ID={role_id}")
        raise NotFoundException(detail=f"Không tìm thấy role với ID={role_id}")

    # Kiểm tra tên role đã tồn tại chưa nếu cập nhật tên
    if role_data.name and role_data.name != role.name:
        existing_role = RoleRepository.get_by_name(db, role_data.name)
        if existing_role:
            logger.warning(f"Tên role đã tồn tại: {role_data.name}")
            raise ConflictException(detail="Tên role đã tồn tại", field="name")

    # Kiểm tra permissions tồn tại nếu cập nhật permissions
    if role_data.permission_ids is not None:
        current_permissions = RoleRepository.get_permissions(db, role_id)
        current_permission_ids = [p.id for p in current_permissions]

        for permission_id in role_data.permission_ids:
            permission = PermissionRepository.get_by_id(db, permission_id)
            if not permission:
                raise BadRequestException(
                    detail=f"Không tìm thấy quyền với ID={permission_id}",
                    field="permission_ids",
                )

    # Chuẩn bị dữ liệu cập nhật
    update_data = role_data.model_dump(exclude={"permission_ids"}, exclude_unset=True)
    update_data["updated_at"] = datetime.now(timezone.utc)

    # Lưu thông tin trước khi cập nhật cho việc ghi log
    previous_data = {"name": role.name, "description": role.description}

    # Cập nhật role
    try:
        updated_role = RoleRepository.update(db, role_id, update_data)
        if not updated_role:
            raise ServerException(detail=f"Không thể cập nhật role với ID={role_id}")

        # Cập nhật permissions nếu có
        if role_data.permission_ids is not None:
            # Xóa các permissions hiện tại
            RoleRepository.clear_permissions(db, role_id)

            # Thêm permissions mới
            for permission_id in role_data.permission_ids:
                RoleRepository.add_permission(db, role_id, permission_id)

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="ROLE",
                        entity_id=role_id,
                        description=f"Updated role: {updated_role.name}",
                        metadata={
                            "previous": previous_data,
                            "updated": {
                                k: v
                                for k, v in update_data.items()
                                if k != "updated_at"
                            },
                            "permission_ids": (
                                role_data.permission_ids
                                if role_data.permission_ids is not None
                                else "unchanged"
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return updated_role
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

        logger.error(f"Lỗi khi cập nhật role: {str(e)}")
        raise ServerException(detail=f"Không thể cập nhật role: {str(e)}")


@invalidate_cache(tags=["roles"])
def delete_role(db: Session, role_id: int, admin_id: Optional[int] = None) -> bool:
    """
    Xóa role.

    Args:
        db: Database session
        role_id: ID role
        admin_id: ID của admin thực hiện hành động

    Returns:
        True nếu xóa thành công

    Raises:
        NotFoundException: Nếu không tìm thấy role
        BadRequestException: Nếu role đang được sử dụng
        ServerException: Nếu có lỗi khác
    """
    # Kiểm tra role tồn tại
    role = RoleRepository.get_by_id(db, role_id)
    if not role:
        logger.warning(f"Không tìm thấy role với ID={role_id}")
        raise NotFoundException(detail=f"Không tìm thấy role với ID={role_id}")

    # Kiểm tra role có đang được sử dụng không
    # TODO: Kiểm tra role có đang được gán cho admin nào không

    # Log admin activity before deletion
    if admin_id:
        try:
            permissions = RoleRepository.get_permissions(db, role_id)
            permission_ids = [p.id for p in permissions]

            create_admin_activity_log(
                db,
                AdminActivityLogCreate(
                    admin_id=admin_id,
                    activity_type="DELETE",
                    entity_type="ROLE",
                    entity_id=role_id,
                    description=f"Deleted role: {role.name}",
                    metadata={
                        "name": role.name,
                        "description": role.description,
                        "permission_ids": permission_ids,
                    },
                ),
            )
        except Exception as e:
            logger.error(f"Failed to log admin activity: {str(e)}")

    # Xóa role
    try:
        # Xóa các relationships trước
        RoleRepository.clear_permissions(db, role_id)

        # Xóa role
        success = RoleRepository.delete(db, role_id)
        if not success:
            raise ServerException(detail=f"Không thể xóa role với ID={role_id}")

        return True
    except Exception as e:
        if isinstance(e, (NotFoundException, BadRequestException, ServerException)):
            raise e

        logger.error(f"Lỗi khi xóa role: {str(e)}")
        raise ServerException(detail=f"Không thể xóa role: {str(e)}")


@invalidate_cache(tags=["roles", "permissions"])
def set_role_permissions(db: Session, role_id: int, permission_ids: List[int]) -> Role:
    """
    Gán permissions cho role.

    Args:
        db: Database session
        role_id: ID role
        permission_ids: Danh sách ID permission

    Returns:
        Role object đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy role hoặc permission
        ServerException: Nếu có lỗi khác
    """
    # Kiểm tra role tồn tại
    role = RoleRepository.get_by_id(db, role_id)
    if not role:
        logger.warning(f"Không tìm thấy role với ID={role_id}")
        raise NotFoundException(detail=f"Không tìm thấy role với ID={role_id}")

    # Kiểm tra permission tồn tại
    if permission_ids:
        for permission_id in permission_ids:
            permission = PermissionRepository.get_by_id(db, permission_id)
            if not permission:
                logger.warning(f"Không tìm thấy permission với ID={permission_id}")
                raise NotFoundException(
                    detail=f"Không tìm thấy permission với ID={permission_id}"
                )

    # Gán permissions
    try:
        for permission_id in permission_ids:
            # Thêm permission cho role
            success = PermissionRepository.add_permission_to_role(
                db, role_id, permission_id
            )
            if not success:
                logger.warning(
                    f"Không thể gán permission ID={permission_id} cho role ID={role_id}"
                )

        # Lấy role đã cập nhật
        updated_role = RoleRepository.get_by_id(db, role_id)
        if not updated_role:
            raise ServerException(
                detail=f"Không thể lấy thông tin role sau khi cập nhật"
            )

        return updated_role
    except Exception as e:
        if isinstance(e, (NotFoundException, ServerException)):
            raise e

        logger.error(f"Lỗi khi gán permissions cho role: {str(e)}")
        raise ServerException(detail=f"Không thể gán permissions cho role: {str(e)}")


@cached(ttl=3600, namespace="admin:roles:permissions", tags=["roles", "permissions"])
def get_role_permissions(
    db: Session, role_id: int, admin_id: Optional[int] = None
) -> List[Permission]:
    """
    Lấy danh sách permission của role.

    Args:
        db: Database session
        role_id: ID role
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách permission

    Raises:
        NotFoundException: Nếu không tìm thấy role
    """
    # Kiểm tra role tồn tại
    role = RoleRepository.get_by_id(db, role_id)
    if not role:
        logger.warning(f"Không tìm thấy role với ID={role_id}")
        raise NotFoundException(detail=f"Không tìm thấy role với ID={role_id}")

    try:
        permissions = RoleRepository.get_permissions(db, role_id)

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="ROLE_PERMISSIONS",
                        entity_id=role_id,
                        description=f"Viewed permissions for role: {role.name}",
                        metadata={
                            "role_name": role.name,
                            "permissions_count": len(permissions),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return permissions
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách permission của role: {str(e)}")
        raise ServerException(
            detail=f"Lỗi khi lấy danh sách permission của role: {str(e)}"
        )


@invalidate_cache(tags=["roles"])
def add_permission_to_role(
    db: Session, role_id: int, permission_id: int, admin_id: Optional[int] = None
) -> bool:
    """
    Thêm quyền vào role.

    Args:
        db: Database session
        role_id: ID role
        permission_id: ID quyền
        admin_id: ID của admin thực hiện hành động

    Returns:
        True nếu thêm thành công

    Raises:
        NotFoundException: Nếu không tìm thấy role hoặc quyền
        ConflictException: Nếu quyền đã được gán cho role
        ServerException: Nếu có lỗi khác
    """
    # Kiểm tra role tồn tại
    role = RoleRepository.get_by_id(db, role_id)
    if not role:
        logger.warning(f"Không tìm thấy role với ID={role_id}")
        raise NotFoundException(detail=f"Không tìm thấy role với ID={role_id}")

    # Kiểm tra quyền tồn tại
    permission = PermissionRepository.get_by_id(db, permission_id)
    if not permission:
        logger.warning(f"Không tìm thấy quyền với ID={permission_id}")
        raise NotFoundException(detail=f"Không tìm thấy quyền với ID={permission_id}")

    # Kiểm tra quyền đã được gán chưa
    if RoleRepository.has_permission(db, role_id, permission_id):
        logger.warning(
            f"Quyền với ID={permission_id} đã được gán cho role với ID={role_id}"
        )
        raise ConflictException(
            detail=f"Quyền đã được gán cho role", field="permission_id"
        )

    # Thêm quyền vào role
    try:
        success = RoleRepository.add_permission(db, role_id, permission_id)
        if not success:
            raise ServerException(detail=f"Không thể thêm quyền vào role")

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="ROLE_PERMISSION",
                        entity_id=role_id,
                        description=f"Added permission to role: {role.name}",
                        metadata={
                            "role_name": role.name,
                            "permission_id": permission_id,
                            "permission_name": permission.name,
                            "permission_resource": permission.resource,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return True
    except Exception as e:
        if isinstance(e, (NotFoundException, ConflictException, ServerException)):
            raise e

        logger.error(f"Lỗi khi thêm quyền vào role: {str(e)}")
        raise ServerException(detail=f"Không thể thêm quyền vào role: {str(e)}")


@invalidate_cache(tags=["roles"])
def remove_permission_from_role(
    db: Session, role_id: int, permission_id: int, admin_id: Optional[int] = None
) -> bool:
    """
    Xóa quyền khỏi role.

    Args:
        db: Database session
        role_id: ID role
        permission_id: ID quyền
        admin_id: ID của admin thực hiện hành động

    Returns:
        True nếu xóa thành công

    Raises:
        NotFoundException: Nếu không tìm thấy role hoặc quyền
        BadRequestException: Nếu quyền chưa được gán cho role
        ServerException: Nếu có lỗi khác
    """
    # Kiểm tra role tồn tại
    role = RoleRepository.get_by_id(db, role_id)
    if not role:
        logger.warning(f"Không tìm thấy role với ID={role_id}")
        raise NotFoundException(detail=f"Không tìm thấy role với ID={role_id}")

    # Kiểm tra quyền tồn tại
    permission = PermissionRepository.get_by_id(db, permission_id)
    if not permission:
        logger.warning(f"Không tìm thấy quyền với ID={permission_id}")
        raise NotFoundException(detail=f"Không tìm thấy quyền với ID={permission_id}")

    # Kiểm tra quyền đã được gán chưa
    if not RoleRepository.has_permission(db, role_id, permission_id):
        logger.warning(
            f"Quyền với ID={permission_id} chưa được gán cho role với ID={role_id}"
        )
        raise BadRequestException(
            detail=f"Quyền chưa được gán cho role", field="permission_id"
        )

    # Log admin activity before removal
    if admin_id:
        try:
            create_admin_activity_log(
                db,
                AdminActivityLogCreate(
                    admin_id=admin_id,
                    activity_type="UPDATE",
                    entity_type="ROLE_PERMISSION",
                    entity_id=role_id,
                    description=f"Removed permission from role: {role.name}",
                    metadata={
                        "role_name": role.name,
                        "permission_id": permission_id,
                        "permission_name": permission.name,
                        "permission_resource": permission.resource,
                    },
                ),
            )
        except Exception as e:
            logger.error(f"Failed to log admin activity: {str(e)}")

    # Xóa quyền khỏi role
    try:
        success = RoleRepository.remove_permission(db, role_id, permission_id)
        if not success:
            raise ServerException(detail=f"Không thể xóa quyền khỏi role")

        return True
    except Exception as e:
        if isinstance(e, (NotFoundException, BadRequestException, ServerException)):
            raise e

        logger.error(f"Lỗi khi xóa quyền khỏi role: {str(e)}")
        raise ServerException(detail=f"Không thể xóa quyền khỏi role: {str(e)}")


@invalidate_cache(tags=["roles", "permissions"])
def assign_permissions_to_role(
    db: Session, role_id: int, permission_ids: List[int], admin_id: Optional[int] = None
) -> bool:
    """
    Gán nhiều quyền cho role.

    Args:
        db: Database session
        role_id: ID của role
        permission_ids: Danh sách ID của các quyền
        admin_id: ID của admin thực hiện hành động

    Returns:
        True nếu gán quyền thành công

    Raises:
        NotFoundException: Nếu không tìm thấy role hoặc quyền
        ServerException: Nếu có lỗi khác
    """
    # Kiểm tra role tồn tại
    role = RoleRepository.get_by_id(db, role_id)
    if not role:
        logger.warning(f"Không tìm thấy role với ID={role_id}")
        raise NotFoundException(detail=f"Không tìm thấy role với ID={role_id}")

    # Xóa tất cả quyền hiện tại
    try:
        RoleRepository.clear_permissions(db, role_id)
    except Exception as e:
        logger.error(f"Lỗi khi xóa quyền hiện tại: {str(e)}")
        raise ServerException(detail=f"Không thể xóa quyền hiện tại: {str(e)}")

    # Kiểm tra và thêm từng quyền mới
    for permission_id in permission_ids:
        permission = PermissionRepository.get_by_id(db, permission_id)
        if not permission:
            logger.warning(f"Không tìm thấy quyền với ID={permission_id}")
            raise NotFoundException(
                detail=f"Không tìm thấy quyền với ID={permission_id}"
            )

        try:
            RoleRepository.add_permission(db, role_id, permission_id)
        except Exception as e:
            logger.error(
                f"Lỗi khi thêm quyền {permission_id} cho role {role_id}: {str(e)}"
            )
            raise ServerException(detail=f"Không thể thêm quyền: {str(e)}")

    # Log admin activity
    if admin_id:
        try:
            create_admin_activity_log(
                db,
                AdminActivityLogCreate(
                    admin_id=admin_id,
                    activity_type="UPDATE",
                    entity_type="ROLE_PERMISSIONS",
                    entity_id=role_id,
                    description=f"Assigned permissions to role: {role.name}",
                    metadata={
                        "role_id": role_id,
                        "role_name": role.name,
                        "permission_ids": permission_ids,
                    },
                ),
            )
        except Exception as e:
            logger.error(f"Failed to log admin activity: {str(e)}")

    logger.info(f"Đã gán {len(permission_ids)} quyền cho role {role.name}")
    return True
