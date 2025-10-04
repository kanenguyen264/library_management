from sqlalchemy import Column, Date, DateTime, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Author(Base):
    __tablename__ = "authors"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    bio = Column(Text, nullable=True)
    birth_date = Column(Date, nullable=True)
    death_date = Column(Date, nullable=True)
    nationality = Column(String, nullable=True)
    website = Column(String, nullable=True)
    image_url = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    books = relationship("Book", back_populates="author")

    def __repr__(self):
        return f"<Author(id={self.id}, name='{self.name}')>"
