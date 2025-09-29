from sqlalchemy import Column, Integer, String, Text, DateTime, Index, func
from sqlalchemy.orm import relationship
from app.core.db import Base


class Publisher(Base):
    __tablename__ = "publishers"
    __table_args__ = (Index("idx_publishers_name", "name"), {"schema": "public"})

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    logo_url = Column(String(500), nullable=True)
    website = Column(String(255), nullable=True)
    contact_email = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    books = relationship("Book", back_populates="publisher")
