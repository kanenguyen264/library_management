from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Index,
    func,
    Enum,
)
from sqlalchemy.orm import relationship
import enum
from app.core.db import Base


class SocialProvider(str, enum.Enum):
    """Các nhà cung cấp mạng xã hội được hỗ trợ"""

    FACEBOOK = "facebook"
    GOOGLE = "google"
    TWITTER = "twitter"
    GITHUB = "github"
    LINKEDIN = "linkedin"
    APPLE = "apple"


# Đổi tên class để tương thích với import trong social_profile_service.py
class SocialProfile(Base):
    __tablename__ = "user_social_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="user_provider_unique"),
        Index("idx_user_social_profiles_user_id", "user_id"),
        Index("idx_user_social_profiles_provider", "provider"),
        {"schema": "user_data"},
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_data.users.id"), nullable=False)
    provider = Column(Enum(SocialProvider), nullable=False)
    provider_id = Column(String(255), nullable=False)
    provider_username = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="social_profiles")
