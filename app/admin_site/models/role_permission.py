from sqlalchemy import (
    Column,
    Integer,
    DateTime,
    ForeignKey,
    PrimaryKeyConstraint,
    Index,
    func,
)
from sqlalchemy.orm import relationship
from app.core.db import Base


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (
        PrimaryKeyConstraint("role_id", "permission_id"),
        Index("ix_role_permissions_role_id", "role_id"),
        Index("ix_role_permissions_permission_id", "permission_id"),
        {"schema": "admin", "extend_existing": True},
    )

    role_id = Column(Integer, ForeignKey("roles.id"), primary_key=True)
    permission_id = Column(Integer, ForeignKey("permissions.id"), primary_key=True)
    # created_at được thừa kế từ CustomBase

    # Relationships
    role = relationship("Role")
    permission = relationship("Permission")
