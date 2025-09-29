from sqlalchemy import Column, Integer, String, Text, DateTime, Index, func
from sqlalchemy.orm import relationship
from app.core.db import Base


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (Index("idx_roles_name", "name"), {"schema": "admin"})

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    # created_at và updated_at được thừa kế từ CustomBase

    # Relationships
    permissions = relationship("Permission", secondary="role_permissions")
    admins = relationship("Admin", backref="roles")
    admin_roles = relationship("AdminRole")
    role_permissions = relationship("RolePermission")
