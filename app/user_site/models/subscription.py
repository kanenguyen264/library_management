from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    Float,
    DateTime,
    ForeignKey,
    Index,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
import enum
from app.core.db import Base


class SubscriptionStatus(str, enum.Enum):
    """Trạng thái đăng ký"""

    ACTIVE = "active"
    CANCELED = "canceled"
    EXPIRED = "expired"
    PENDING = "pending"
    TRIAL = "trial"
    PAUSED = "paused"


class SubscriptionType(str, enum.Enum):
    """Loại đăng ký"""

    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"
    LIFETIME = "lifetime"
    TRIAL = "trial"


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"
    __table_args__ = (
        Index("idx_subscription_plans_is_active", "is_active"),
        Index("idx_subscription_plans_price", "price"),
        Index("idx_subscription_plans_billing_cycle", "billing_cycle"),
        {"schema": "user_data"},
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Float, nullable=False)
    currency = Column(String(10), nullable=False)
    billing_cycle = Column(String(50), nullable=False)
    features_json = Column(JSONB, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    subscriptions = relationship("UserSubscription", back_populates="plan")


class UserSubscription(Base):
    __tablename__ = "user_subscriptions"
    __table_args__ = (
        Index("idx_user_subscriptions_user_id", "user_id"),
        Index("idx_user_subscriptions_plan_id", "plan_id"),
        Index("idx_user_subscriptions_status", "status"),
        Index("idx_user_subscriptions_renewal_date", "renewal_date"),
        {"schema": "user_data"},
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_data.users.id"), nullable=False)
    plan_id = Column(
        Integer, ForeignKey("user_data.subscription_plans.id"), nullable=False
    )
    status = Column(String(50), nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=True)
    renewal_date = Column(DateTime, nullable=True)
    payment_method = Column(String(100), nullable=True)
    auto_renew = Column(Boolean, default=True, nullable=False)
    billing_info_json = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="subscriptions")
    plan = relationship("SubscriptionPlan", back_populates="subscriptions")
    transactions = relationship("Payment", back_populates="subscription")


# For backward compatibility with other modules
Subscription = UserSubscription
