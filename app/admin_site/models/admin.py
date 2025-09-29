"""
Admin model for the admin site.
"""

from datetime import datetime
from typing import List
from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    Table,
    Text,
    Index,
    func,
)
from sqlalchemy.orm import relationship
from app.core.db import Base
from app.core.models import TimestampMixin
from app.security.encryption.field_encryption import EncryptedString


class Admin(Base, TimestampMixin):
    """Admin model."""

    __tablename__ = "admins"
    __table_args__ = (
        Index("idx_admins_username", "username"),
        Index("idx_admins_email", "email"),
        Index("idx_admins_is_active", "is_active"),
        {"schema": "admin"},
    )

    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(EncryptedString, nullable=False)
    full_name = Column(String(255))
    avatar_url = Column(String(500))
    is_active = Column(Boolean, default=True)
    is_superadmin = Column(Boolean, default=False)
    role_id = Column(Integer, ForeignKey("admin.roles.id"), nullable=True)
    phone = Column(String(50))
    note = Column(Text)
    last_login = Column(DateTime, nullable=True)
    login_count = Column(Integer, default=0)
    failed_login_attempts = Column(Integer, default=0)
    last_failed_login = Column(DateTime, nullable=True)

    # Relationships
    role = relationship("Role", foreign_keys=[role_id])
    sessions = relationship("AdminSession", back_populates="admin")

    def __init__(self, **kwargs):
        """Initialize admin."""
        super().__init__(**kwargs)

    def get_full_name(self):
        """Get full name."""
        return self.full_name if self.full_name else self.username

    def has_permission(self, permission_name: str) -> bool:
        """
        Check if admin has a specific permission.

        Args:
            permission_name: Permission to check

        Returns:
            True if has permission, False otherwise
        """
        if self.is_superadmin:
            return True

        if self.role and hasattr(self.role, "permissions"):
            for permission in self.role.permissions:
                if permission.name == permission_name:
                    return True
        return False

    def has_role(self, role_name: str) -> bool:
        """
        Check if admin has a specific role.

        Args:
            role_name: Role to check

        Returns:
            True if has role, False otherwise
        """
        if self.is_superadmin:
            return True

        return self.role and self.role.name == role_name

    def update_login_success(self) -> None:
        """Update login timestamp and count."""
        self.last_login = func.now()
        self.login_count += 1
        self.failed_login_attempts = 0

    def update_login_failure(self) -> None:
        """Update login failure information."""
        self.last_failed_login = func.now()
        self.failed_login_attempts += 1

    @property
    def permissions(self):
        """Get all permissions for the admin."""
        if self.is_superadmin:
            from app.admin_site.models.permission import Permission

            # Get all available permissions
            return [p.name for p in Permission.query.all()]

        # Aggregate permissions from role
        permissions = set()
        if self.role and hasattr(self.role, "permissions"):
            for permission in self.role.permissions:
                permissions.add(permission.name)

        return list(permissions)

    def check_password(self, password: str) -> bool:
        """
        Kiểm tra mật khẩu có khớp với password_hash không.

        Args:
            password: Mật khẩu cần kiểm tra

        Returns:
            bool: True nếu mật khẩu đúng, False nếu sai
        """
        from app.security.password import verify_password

        return verify_password(password, self.password_hash)

    def set_password(self, password: str) -> None:
        """
        Set mật khẩu mới cho admin (đã được hash).

        Args:
            password: Mật khẩu mới (chưa hash)
        """
        from app.security.password import get_password_hash

        self.password_hash = get_password_hash(password)

    def to_dict(self) -> dict:
        """
        Chuyển đổi admin thành dictionary.

        Returns:
            dict: Thông tin admin dưới dạng dictionary
        """
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "full_name": self.full_name,
            "avatar_url": self.avatar_url,
            "is_active": self.is_active,
            "is_superadmin": self.is_superadmin,
            "role_id": self.role_id,
            "phone": self.phone,
            "note": self.note,
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Role(Base, TimestampMixin):
    """Role model."""

    __tablename__ = "roles"
    __table_args__ = ({"schema": "admin"},)

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(String(200))

    # Relationships
    admins = relationship("Admin", secondary="admin.admin_roles", back_populates="role")
    permissions = relationship(
        "Permission", secondary="admin.role_permissions", back_populates="roles"
    )


class Permission(Base, TimestampMixin):
    """Permission model."""

    __tablename__ = "permissions"
    __table_args__ = ({"schema": "admin"},)

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(String(200))
    module = Column(String(50), nullable=False)  # For categorization

    # Relationships
    roles = relationship(
        "Role", secondary="admin.role_permissions", back_populates="permissions"
    )


class AdminRole(Base):
    """Association table for Admin and Role."""

    __tablename__ = "admin_roles"
    __table_args__ = ({"schema": "admin"},)

    admin_id = Column(
        Integer, ForeignKey("admin.admins.id", ondelete="CASCADE"), primary_key=True
    )
    role_id = Column(
        Integer, ForeignKey("admin.roles.id", ondelete="CASCADE"), primary_key=True
    )
    created_at = Column(DateTime, default=func.now())


class RolePermission(Base):
    """Association table for Role and Permission."""

    __tablename__ = "role_permissions"
    __table_args__ = ({"schema": "admin"},)

    role_id = Column(
        Integer, ForeignKey("admin.roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id = Column(
        Integer,
        ForeignKey("admin.permissions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at = Column(DateTime, default=func.now())
