from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timezone

from app.admin_site.models import Admin, Role, AdminRole
from app.admin_site.schemas.admin import AdminCreate, AdminUpdate
from app.admin_site.repositories.admin_repo import AdminRepository
from app.admin_site.repositories.role_repo import RoleRepository
from app.admin_site.services.auth_service import get_password_hash
from app.cache.decorators import cached, invalidate_cache
from app.core.exceptions import (
    NotFoundException,
    ConflictException,
    ServerException,
    ValidationException,
    BadRequestException,
)
from app.logging.setup import get_logger
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate

logger = get_logger(__name__)


@cached(ttl=300, namespace="admin:admins", tags=["admins"])
def get_all_admins(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
    is_super_admin: Optional[bool] = None,
    order_by: str = "id",
    order_desc: bool = False,
    admin_id: Optional[int] = None,
) -> List[Admin]:
    """
    Lấy danh sách admin với các tùy chọn lọc.

    Args:
        db: Database session
        skip: Số lượng bản ghi bỏ qua
        limit: Số lượng bản ghi tối đa
        search: Tìm kiếm theo username hoặc email
        is_active: Lọc theo trạng thái kích hoạt
        is_super_admin: Lọc theo quyền super admin
        order_by: Trường sắp xếp
        order_desc: Sắp xếp giảm dần nếu True
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách admin
    """
    try:
        admins = AdminRepository.get_all(
            db=db,
            skip=skip,
            limit=limit,
            search=search,
            is_active=is_active,
            is_super_admin=is_super_admin,
            order_by=order_by,
            order_desc=order_desc,
        )

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="ADMIN",
                        entity_id=0,
                        description="Viewed admin list",
                        metadata={
                            "skip": skip,
                            "limit": limit,
                            "search": search,
                            "is_active": is_active,
                            "is_super_admin": is_super_admin,
                            "order_by": order_by,
                            "order_desc": order_desc,
                            "results_count": len(admins),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return admins
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách admin: {str(e)}")
        raise ServerException(detail=f"Lỗi khi lấy danh sách admin: {str(e)}")


def count_admins(
    db: Session,
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
    is_super_admin: Optional[bool] = None,
    admin_id: Optional[int] = None,
) -> int:
    """
    Đếm số lượng admin theo điều kiện lọc.

    Args:
        db: Database session
        search: Tìm kiếm theo username hoặc email
        is_active: Lọc theo trạng thái kích hoạt
        is_super_admin: Lọc theo quyền super admin
        admin_id: ID của admin thực hiện hành động

    Returns:
        Tổng số admin thỏa mãn điều kiện
    """
    try:
        count = AdminRepository.count(
            db=db, search=search, is_active=is_active, is_super_admin=is_super_admin
        )

        # Log admin activity
        if admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="ADMIN",
                        entity_id=0,
                        description="Counted admins",
                        metadata={
                            "search": search,
                            "is_active": is_active,
                            "is_super_admin": is_super_admin,
                            "count": count,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return count
    except Exception as e:
        logger.error(f"Lỗi khi đếm số lượng admin: {str(e)}")
        raise ServerException(detail=f"Lỗi khi đếm số lượng admin: {str(e)}")


@cached(ttl=3600, namespace="admin:admins", tags=["admins"])
def get_admin_by_id(
    db: Session, admin_id: int, viewer_admin_id: Optional[int] = None
) -> Admin:
    """
    Lấy thông tin admin theo ID.

    Args:
        db: Database session
        admin_id: ID admin
        viewer_admin_id: ID của admin thực hiện hành động xem

    Returns:
        Admin object

    Raises:
        NotFoundException: Nếu không tìm thấy admin
    """
    try:
        admin = AdminRepository.get_by_id(db, admin_id)
        if not admin:
            logger.warning(f"Không tìm thấy admin với ID={admin_id}")
            raise NotFoundException(detail=f"Không tìm thấy admin với ID={admin_id}")

        # Log admin activity
        if viewer_admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=viewer_admin_id,
                        activity_type="VIEW",
                        entity_type="ADMIN",
                        entity_id=admin_id,
                        description=f"Viewed admin details - ID: {admin_id}",
                        metadata={
                            "viewed_admin_id": admin_id,
                            "viewed_admin_username": admin.username,
                            "viewed_admin_email": admin.email,
                            "viewed_admin_is_active": admin.is_active,
                            "viewed_admin_is_super_admin": admin.is_super_admin,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return admin
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin admin theo ID: {str(e)}")
        raise ServerException(detail=f"Lỗi khi lấy thông tin admin theo ID: {str(e)}")


@cached(ttl=3600, namespace="admin:admins", tags=["admins"])
def get_admin_by_username(
    db: Session, username: str, admin_id: Optional[int] = None
) -> Optional[Admin]:
    """
    Lấy thông tin admin theo username.

    Args:
        db: Database session
        username: Tên đăng nhập
        admin_id: ID của admin thực hiện hành động

    Returns:
        Admin object hoặc None nếu không tìm thấy
    """
    try:
        admin = AdminRepository.get_by_username(db, username)

        # Log admin activity
        if admin_id and admin:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="ADMIN",
                        entity_id=admin.id,
                        description=f"Searched admin by username: {username}",
                        metadata={
                            "search_username": username,
                            "found": admin is not None,
                            "found_admin_id": admin.id if admin else None,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return admin
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin admin theo username: {str(e)}")
        return None


@cached(ttl=3600, namespace="admin:admins", tags=["admins"])
def get_admin_by_email(
    db: Session, email: str, admin_id: Optional[int] = None
) -> Optional[Admin]:
    """
    Lấy thông tin admin theo email.

    Args:
        db: Database session
        email: Email của admin
        admin_id: ID của admin thực hiện hành động

    Returns:
        Admin object hoặc None nếu không tìm thấy
    """
    try:
        admin = AdminRepository.get_by_email(db, email)

        # Log admin activity
        if admin_id and admin:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="ADMIN",
                        entity_id=admin.id,
                        description=f"Searched admin by email: {email}",
                        metadata={
                            "search_email": email,
                            "found": admin is not None,
                            "found_admin_id": admin.id if admin else None,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return admin
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin admin theo email: {str(e)}")
        return None


@invalidate_cache(tags=["admins"])
def create_new_admin(
    db: Session, admin_data: AdminCreate, creator_admin_id: Optional[int] = None
) -> Admin:
    """
    Tạo admin mới.

    Args:
        db: Database session
        admin_data: Thông tin admin mới
        creator_admin_id: ID của admin thực hiện hành động tạo

    Returns:
        Admin object đã tạo

    Raises:
        ConflictException: Nếu username hoặc email đã tồn tại
        ServerException: Nếu có lỗi khác xảy ra
    """
    # Kiểm tra username đã tồn tại chưa
    existing_username = AdminRepository.get_by_username(db, admin_data.username)
    if existing_username:
        logger.warning(f"Username đã tồn tại: {admin_data.username}")
        raise ConflictException(detail="Username đã tồn tại", field="username")

    # Kiểm tra email đã tồn tại chưa
    existing_email = AdminRepository.get_by_email(db, admin_data.email)
    if existing_email:
        logger.warning(f"Email đã tồn tại: {admin_data.email}")
        raise ConflictException(detail="Email đã tồn tại", field="email")

    try:
        # Tạo hash mật khẩu
        hashed_password = get_password_hash(admin_data.password)

        # Chuẩn bị dữ liệu
        admin_dict = admin_data.model_dump(exclude={"password"})
        admin_dict.update(
            {
                "password_hash": hashed_password,
                "is_active": True,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
        )

        # Tạo admin mới
        new_admin = AdminRepository.create(db, admin_dict)

        # Log admin activity
        if creator_admin_id:
            try:
                # Loại bỏ password từ metadata vì lý do bảo mật
                log_data = admin_data.model_dump(exclude={"password"})
                log_data["is_active"] = True

                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=creator_admin_id,
                        activity_type="CREATE",
                        entity_type="ADMIN",
                        entity_id=new_admin.id,
                        description=f"Created new admin: {new_admin.username}",
                        metadata={
                            "new_admin_id": new_admin.id,
                            "new_admin_data": log_data,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return new_admin
    except Exception as e:
        if isinstance(e, ConflictException):
            raise e
        logger.error(f"Lỗi khi tạo admin: {str(e)}")
        raise ServerException(detail=f"Không thể tạo admin: {str(e)}")


@invalidate_cache(tags=["admins"])
def update_admin(
    db: Session,
    admin_id: int,
    admin_data: AdminUpdate,
    updater_admin_id: Optional[int] = None,
) -> Admin:
    """
    Cập nhật thông tin admin.

    Args:
        db: Database session
        admin_id: ID admin cần cập nhật
        admin_data: Thông tin cần cập nhật
        updater_admin_id: ID của admin thực hiện hành động cập nhật

    Returns:
        Admin object đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy admin
        ConflictException: Nếu email đã tồn tại
        ServerException: Nếu có lỗi khác xảy ra
    """
    try:
        # Kiểm tra admin tồn tại
        admin = AdminRepository.get_by_id(db, admin_id)
        if not admin:
            logger.warning(f"Không tìm thấy admin với ID={admin_id}")
            raise NotFoundException(detail=f"Không tìm thấy admin với ID={admin_id}")

        # Lưu dữ liệu cũ để log
        old_data = {
            "username": admin.username,
            "email": admin.email,
            "full_name": admin.full_name,
            "is_active": admin.is_active,
            "is_super_admin": admin.is_super_admin,
        }

        # Kiểm tra email đã tồn tại chưa nếu có thay đổi email
        if admin_data.email and admin_data.email != admin.email:
            existing_email = AdminRepository.get_by_email(db, admin_data.email)
            if existing_email and existing_email.id != admin_id:
                logger.warning(f"Email đã tồn tại: {admin_data.email}")
                raise ConflictException(detail="Email đã tồn tại", field="email")

        # Chuẩn bị dữ liệu cập nhật
        update_data = admin_data.model_dump(exclude_unset=True)
        update_data["updated_at"] = datetime.now(timezone.utc)

        # Cập nhật admin
        updated_admin = AdminRepository.update(db, admin_id, update_data)
        if not updated_admin:
            raise NotFoundException(detail=f"Không tìm thấy admin với ID={admin_id}")

        # Log admin activity
        if updater_admin_id:
            try:
                # Chuẩn bị dữ liệu mới
                new_data = {
                    "username": updated_admin.username,
                    "email": updated_admin.email,
                    "full_name": updated_admin.full_name,
                    "is_active": updated_admin.is_active,
                    "is_super_admin": updated_admin.is_super_admin,
                }

                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=updater_admin_id,
                        activity_type="UPDATE",
                        entity_type="ADMIN",
                        entity_id=admin_id,
                        description=f"Updated admin - ID: {admin_id}, Username: {updated_admin.username}",
                        metadata={
                            "updated_admin_id": admin_id,
                            "old_data": old_data,
                            "new_data": new_data,
                            "changes": {
                                k: new_data[k]
                                for k in new_data
                                if old_data.get(k) != new_data.get(k)
                            },
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return updated_admin
    except Exception as e:
        if isinstance(e, (NotFoundException, ConflictException)):
            raise e
        logger.error(f"Lỗi khi cập nhật admin: {str(e)}")
        raise ServerException(detail=f"Không thể cập nhật admin: {str(e)}")


@invalidate_cache(tags=["admins"])
def delete_admin(
    db: Session, admin_id: int, deleter_admin_id: Optional[int] = None
) -> bool:
    """
    Xóa admin.

    Args:
        db: Database session
        admin_id: ID admin cần xóa
        deleter_admin_id: ID của admin thực hiện hành động xóa

    Returns:
        True nếu xóa thành công

    Raises:
        NotFoundException: Nếu không tìm thấy admin
        ServerException: Nếu có lỗi khác xảy ra
    """
    try:
        # Kiểm tra admin tồn tại
        admin = AdminRepository.get_by_id(db, admin_id)
        if not admin:
            logger.warning(f"Không tìm thấy admin với ID={admin_id}")
            raise NotFoundException(detail=f"Không tìm thấy admin với ID={admin_id}")

        # Lưu thông tin admin sẽ bị xóa để log
        admin_info = {
            "id": admin.id,
            "username": admin.username,
            "email": admin.email,
            "full_name": admin.full_name,
            "is_active": admin.is_active,
            "is_super_admin": admin.is_super_admin,
        }

        # Xóa admin
        success = AdminRepository.delete(db, admin_id)
        if not success:
            raise ServerException(detail=f"Không thể xóa admin với ID={admin_id}")

        # Log admin activity
        if deleter_admin_id:
            try:
                create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=deleter_admin_id,
                        activity_type="DELETE",
                        entity_type="ADMIN",
                        entity_id=admin_id,
                        description=f"Deleted admin - ID: {admin_id}, Username: {admin.username}",
                        metadata={"deleted_admin_info": admin_info},
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return True
    except Exception as e:
        if isinstance(e, (NotFoundException, ServerException)):
            raise e
        logger.error(f"Lỗi khi xóa admin: {str(e)}")
        raise ServerException(detail=f"Không thể xóa admin: {str(e)}")


@invalidate_cache(tags=["admins", "roles"])
def assign_roles_to_admin(
    db: Session,
    admin_id: int,
    role_ids: List[int],
    assigner_admin_id: int,
    append: bool = False,
) -> Admin:
    """
    Gán vai trò (roles) cho admin.

    Args:
        db: Database session
        admin_id: ID của admin
        role_ids: Danh sách các role ID cần gán
        assigner_admin_id: ID của admin thực hiện hành động gán
        append: True để thêm vào danh sách có sẵn, False để thay thế hoàn toàn

    Returns:
        Admin object đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy admin hoặc vai trò
        ServerException: Lỗi khác trong quá trình xử lý
    """
    try:
        # Kiểm tra admin tồn tại
        admin = AdminRepository.get_by_id(db, admin_id)
        if not admin:
            logger.warning(f"Không tìm thấy admin với ID={admin_id}")
            raise NotFoundException(detail=f"Không tìm thấy admin với ID={admin_id}")

        # Lấy danh sách vai trò cũ
        old_roles = AdminRepository.get_roles(db, admin_id)
        old_role_ids = [role.id for role in old_roles]

        # Nếu mode append, thêm role mới vào danh sách hiện tại
        if append:
            role_ids = list(set(old_role_ids + role_ids))  # Loại bỏ trùng lặp

        # Kiểm tra role_ids không rỗng
        if not role_ids:
            raise BadRequestException(detail="Danh sách vai trò không được rỗng")

        # Kiểm tra tất cả role tồn tại
        roles = []
        for role_id in role_ids:
            role = RoleRepository.get_by_id(db, role_id)
            if not role:
                logger.warning(f"Không tìm thấy vai trò với ID={role_id}")
                raise NotFoundException(
                    detail=f"Không tìm thấy vai trò với ID={role_id}"
                )
            roles.append(role)

        # Chuẩn bị dữ liệu
        admin_roles = []
        now = datetime.now(timezone.utc)

        for role_id in role_ids:
            admin_roles.append(
                {
                    "admin_id": admin_id,
                    "role_id": role_id,
                    "granted_by": assigner_admin_id,
                    "granted_at": now,
                }
            )

        # Gán vai trò
        updated_admin = AdminRepository.set_roles(db, admin_id, admin_roles)

        # Log admin activity
        try:
            role_names = [role.name for role in roles]
            old_role_names = [role.name for role in old_roles]

            action_type = "Appended roles to" if append else "Replaced all roles for"

            create_admin_activity_log(
                db,
                AdminActivityLogCreate(
                    admin_id=assigner_admin_id,
                    activity_type="UPDATE",
                    entity_type="ADMIN_ROLE",
                    entity_id=admin_id,
                    description=f"{action_type} admin - ID: {admin_id}, Username: {admin.username}",
                    metadata={
                        "target_admin_id": admin_id,
                        "target_admin_username": admin.username,
                        "old_role_ids": old_role_ids,
                        "old_role_names": old_role_names,
                        "new_role_ids": role_ids,
                        "new_role_names": role_names,
                        "operation_type": "append" if append else "replace",
                        "added_roles": [
                            id for id in role_ids if id not in old_role_ids
                        ],
                        "removed_roles": [
                            id for id in old_role_ids if id not in role_ids
                        ],
                    },
                ),
            )
        except Exception as e:
            logger.error(f"Failed to log admin activity: {str(e)}")

        return updated_admin
    except Exception as e:
        if isinstance(e, (NotFoundException, BadRequestException)):
            raise e
        logger.error(f"Lỗi khi gán vai trò: {str(e)}")
        raise ServerException(detail=f"Không thể gán vai trò: {str(e)}")


# Tạo alias cho hàm assign_roles_to_admin để duy trì tương thích ngược
set_admin_roles = assign_roles_to_admin


@cached(ttl=3600, namespace="admin:admins:roles", tags=["admins", "roles"])
def get_admin_roles(db: Session, admin_id: int) -> List[Role]:
    """
    Lấy danh sách role của admin.

    Args:
        db: Database session
        admin_id: ID admin

    Returns:
        Danh sách Role

    Raises:
        NotFoundException: Nếu không tìm thấy admin
    """
    # Kiểm tra admin tồn tại
    admin = AdminRepository.get_by_id(db, admin_id)
    if not admin:
        logger.warning(f"Không tìm thấy admin với ID={admin_id}")
        raise NotFoundException(detail=f"Không tìm thấy admin với ID={admin_id}")

    try:
        return AdminRepository.get_roles(db, admin_id)
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách role của admin: {str(e)}")
        raise ServerException(detail=f"Lỗi khi lấy danh sách role của admin: {str(e)}")


@cached(ttl=3600, namespace="admin:admins:permissions", tags=["admins", "permissions"])
def has_permission(db: Session, admin_id: int, permission_name: str) -> bool:
    """
    Kiểm tra admin có quyền cụ thể hay không.

    Args:
        db: Database session
        admin_id: ID admin
        permission_name: Tên quyền

    Returns:
        True nếu admin có quyền, False nếu không
    """
    try:
        return AdminRepository.has_permission(db, admin_id, permission_name)
    except Exception as e:
        logger.error(f"Lỗi khi kiểm tra quyền của admin: {str(e)}")
        return False


@invalidate_cache(tags=["admins"])
def toggle_admin_status(db: Session, admin_id: int) -> Admin:
    """
    Bật/tắt trạng thái hoạt động của admin.

    Args:
        db: Database session
        admin_id: ID admin

    Returns:
        Admin object đã cập nhật

    Raises:
        NotFoundException: Nếu không tìm thấy admin
        ServerException: Nếu có lỗi khác xảy ra
    """
    # Kiểm tra admin tồn tại
    admin = AdminRepository.get_by_id(db, admin_id)
    if not admin:
        logger.warning(f"Không tìm thấy admin với ID={admin_id}")
        raise NotFoundException(detail=f"Không tìm thấy admin với ID={admin_id}")

    # Cập nhật trạng thái
    try:
        update_data = {
            "is_active": not admin.is_active,
            "updated_at": datetime.now(timezone.utc),
        }

        updated_admin = AdminRepository.update(db, admin_id, update_data)
        if not updated_admin:
            raise ServerException(
                detail=f"Không thể cập nhật trạng thái admin với ID={admin_id}"
            )

        return updated_admin
    except Exception as e:
        if isinstance(e, NotFoundException) or isinstance(e, ServerException):
            raise e
        logger.error(f"Lỗi khi thay đổi trạng thái admin: {str(e)}")
        raise ServerException(detail=f"Không thể thay đổi trạng thái admin: {str(e)}")
