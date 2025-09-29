from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    Date,
    DateTime,
    Enum,
    Index,
    func,
    event,
)
from sqlalchemy.orm import relationship, validates
from app.core.db import Base
from app.core.model_mixins import (
    SoftDeleteMixin,
    AuditMixin,
    RateLimitMixin,
    EventMixin,
)
from app.security.encryption.field_encryption import EncryptedString
from app.security.input_validation.validators import (
    validate_email as security_validate_email,
)
import enum


class Gender(str, enum.Enum):
    male = "male"
    female = "female"
    other = "other"
    prefer_not_to_say = "prefer_not_to_say"


class User(Base, SoftDeleteMixin, AuditMixin, RateLimitMixin, EventMixin):
    __tablename__ = "users"
    __table_args__ = (
        Index("idx_users_username", "username"),
        Index("idx_users_email", "email"),
        Index("idx_users_is_premium", "is_premium"),
        Index("idx_users_is_active", "is_active"),
        {"schema": "user_data"},
    )

    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(EncryptedString, nullable=False)  # Encrypted password
    full_name = Column(String(255), nullable=True)
    display_name = Column(String(100), nullable=True)
    avatar_url = Column(String(500), nullable=True)
    bio = Column(Text, nullable=True)
    birth_date = Column(Date, nullable=True)
    gender = Column(Enum(Gender), nullable=True)
    country = Column(String(100), nullable=True)
    language = Column(String(50), nullable=True)
    is_premium = Column(Boolean, default=False)
    premium_until = Column(DateTime, nullable=True)
    is_verified = Column(Boolean, default=False)
    verification_token = Column(EncryptedString, nullable=True)  # Encrypted token
    reset_password_token = Column(EncryptedString, nullable=True)  # Encrypted token
    reset_token_expires = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    last_login = Column(DateTime, nullable=True)
    last_active = Column(DateTime, nullable=True)
    registration_ip = Column(String(50), nullable=True)
    login_attempts = Column(Integer, default=0)  # Track failed login attempts
    locked_until = Column(DateTime, nullable=True)  # Account lockout time

    # Relationships
    social_profiles = relationship("SocialProfile", back_populates="user")
    preferences = relationship("UserPreference", back_populates="user")
    reading_histories = relationship("ReadingHistory", back_populates="user")
    reading_sessions = relationship("ReadingSession", back_populates="user")
    bookmarks = relationship("Bookmark", back_populates="user")
    bookshelves = relationship("Bookshelf", back_populates="user")
    reviews = relationship("Review", back_populates="user")
    review_likes = relationship("ReviewLike", back_populates="user")
    review_reports = relationship(
        "ReviewReport",
        foreign_keys="[ReviewReport.reporter_id]",
        back_populates="reporter",
    )
    annotations = relationship("Annotation", back_populates="user")
    quotes = relationship("Quote", back_populates="user")
    quote_likes = relationship("QuoteLike", back_populates="user")
    achievements = relationship("UserAchievement", back_populates="user")
    badges = relationship("UserBadge", back_populates="user")
    reading_goals = relationship("ReadingGoal", back_populates="user", lazy="dynamic")
    book_lists = relationship("UserBookList", back_populates="user", lazy="dynamic")
    followers = relationship(
        "UserFollowing",
        foreign_keys="UserFollowing.following_id",
        back_populates="following",
        lazy="dynamic",
    )
    following = relationship(
        "UserFollowing",
        foreign_keys="UserFollowing.follower_id",
        back_populates="follower",
        lazy="dynamic",
    )
    notifications = relationship(
        "UserNotification", back_populates="user", lazy="dynamic"
    )
    discussions = relationship("Discussion", back_populates="user", lazy="dynamic")
    discussion_comments = relationship(
        "DiscussionComment", back_populates="user", lazy="dynamic"
    )
    subscriptions = relationship(
        "UserSubscription", back_populates="user", lazy="dynamic"
    )
    payment_transactions = relationship(
        "Payment", back_populates="user", lazy="dynamic"
    )
    payment_methods = relationship(
        "PaymentMethod", back_populates="user", lazy="dynamic"
    )
    recommendations = relationship(
        "Recommendation", back_populates="user", lazy="dynamic"
    )

    # Validators
    @validates("email")
    def validate_email(self, key, email):
        """Validate email trước khi lưu vào DB."""
        result = security_validate_email(email)
        if not result:
            from sqlalchemy.exc import ValidationError

            raise ValidationError("Email không hợp lệ")
        return email  # Trả về chuỗi email gốc, không phải giá trị boolean

    @validates("password_hash")
    def validate_password_hash(self, key, password_hash):
        """Ensure password hash is strong enough"""
        if len(password_hash) < 60:  # bcrypt hash length
            raise ValueError("Password hash is not valid")
        return password_hash

    # Business Methods
    def record_login_attempt(self, success: bool = True):
        """Record login attempt and handle lockout logic"""
        if success:
            self.login_attempts = 0
            self.locked_until = None
            self.last_login = func.now()
        else:
            self.login_attempts += 1
            # Lock account after 5 failed attempts for 15 minutes
            if self.login_attempts >= 5:
                from datetime import datetime, timedelta

                self.locked_until = datetime.utcnow() + timedelta(minutes=15)

    def is_locked(self) -> bool:
        """Check if account is locked due to failed login attempts"""
        from datetime import datetime

        if self.locked_until and self.locked_until > datetime.utcnow():
            return True
        return False

    def check_premium_status(self) -> bool:
        """Check and update premium status based on subscription end date"""
        from datetime import datetime

        if not self.is_premium:
            return False

        if self.premium_until and self.premium_until < datetime.utcnow():
            self.is_premium = False
            return False

        return True

    def refresh_last_active(self):
        """Update last active timestamp"""
        self.last_active = func.now()

    def calculate_reading_stats(self) -> dict:
        """Calculate reading statistics for the user"""
        try:
            # This needs to be executed in a session context
            total_books = self.reading_histories.filter_by(is_completed=True).count()
            total_time = (
                self.reading_sessions.with_entities(
                    func.sum(
                        (
                            self.reading_sessions.end_time
                            - self.reading_sessions.start_time
                        )
                    )
                ).scalar()
                or 0
            )

            return {
                "total_books_read": total_books,
                "total_reading_time": total_time,
                "average_per_book": total_time / total_books if total_books > 0 else 0,
            }
        except Exception:
            return {
                "total_books_read": 0,
                "total_reading_time": 0,
                "average_per_book": 0,
            }

    def publish_user_event(self, event_type, **data):
        """
        Phát hành sự kiện liên quan đến người dùng

        Args:
            event_type: Tên sự kiện từ lớp UserEvent
            **data: Dữ liệu bổ sung để gửi đến các subscriber

        Returns:
            int: Số lượng subscriber được thông báo
        """
        # Loại bỏ thông tin nhạy cảm
        clean_data = data.copy()
        sensitive_fields = [
            "password_hash",
            "verification_token",
            "reset_password_token",
            "email",
        ]
        for field in sensitive_fields:
            if field in clean_data:
                del clean_data[field]

        from app.core.event import publish_user_event

        return publish_user_event(
            event_type, self.id, username=self.username, **clean_data
        )
