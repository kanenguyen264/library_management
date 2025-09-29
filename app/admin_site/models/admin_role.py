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


class AdminRole(Base):
    __tablename__ = "admin_roles"
    __table_args__ = (
        PrimaryKeyConstraint("admin_id", "role_id"),
        Index("idx_admin_roles_admin_id", "admin_id"),
        Index("idx_admin_roles_role_id", "role_id"),
        {"schema": "admin", "extend_existing": True},
    )

    admin_id = Column(Integer, ForeignKey("admin.admins.id"), primary_key=True)
    role_id = Column(Integer, ForeignKey("roles.id"), primary_key=True)
    granted_by = Column(Integer, ForeignKey("admin.admins.id"), nullable=True)
    # created_at được thừa kế từ CustomBase

    # Relationships
    admin = relationship("Admin", foreign_keys=[admin_id])
    role = relationship("Role")
    granter = relationship("Admin", foreign_keys=[granted_by])
