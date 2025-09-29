from sqlalchemy import Column, Integer, String, Text, DateTime, Index, func
from sqlalchemy.orm import relationship
from app.core.db import Base


class Permission(Base):
    __tablename__ = "permissions"
    __table_args__ = (
        Index("idx_permissions_name", "name"),
        Index("idx_permissions_resource", "resource"),
        Index("idx_permissions_action", "action"),
        {"schema": "admin"},
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    resource = Column(String(100), nullable=False)
    action = Column(String(100), nullable=False)
    # created_at và updated_at được thừa kế từ CustomBase

    # Relationships
    roles = relationship("Role", secondary="role_permissions")
    role_permissions = relationship("RolePermission")
