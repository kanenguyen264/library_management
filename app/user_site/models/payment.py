from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    ForeignKey,
    Index,
    func,
    Boolean,
    Text,
    JSON,
)
from sqlalchemy.orm import relationship
from app.core.db import Base


class Payment(Base):
    __tablename__ = "payment_transactions"
    __table_args__ = (
        Index("idx_payment_transactions_user_id", "user_id"),
        Index("idx_payment_transactions_subscription_id", "subscription_id"),
        Index("idx_payment_transactions_status", "status"),
        Index("idx_payment_transactions_created_at", "created_at"),
        {"schema": "user_data"},
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_data.users.id"), nullable=False)
    subscription_id = Column(
        Integer, ForeignKey("user_data.user_subscriptions.id"), nullable=True
    )
    amount = Column(Float, nullable=False)
    currency = Column(String(10), nullable=False)
    transaction_id = Column(String(255), nullable=True)
    payment_method = Column(String(100), nullable=False)
    status = Column(String(50), nullable=False)
    error_message = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="payment_transactions")
    subscription = relationship("UserSubscription", back_populates="transactions")


# Alias for Payment for backward compatibility
PaymentTransaction = Payment


class PaymentMethod(Base):
    __tablename__ = "payment_methods"
    __table_args__ = (
        Index("idx_payment_methods_user_id", "user_id"),
        Index("idx_payment_methods_is_default", "is_default"),
        Index("idx_payment_methods_is_active", "is_active"),
        Index("idx_payment_methods_created_at", "created_at"),
        {"schema": "user_data"},
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_data.users.id"), nullable=False)
    type = Column(
        String(50), nullable=False
    )  # 'credit_card', 'paypal', 'bank_transfer', etc.
    provider = Column(
        String(100), nullable=False
    )  # 'visa', 'mastercard', 'paypal', etc.
    account_number = Column(
        String(255), nullable=True
    )  # Last 4 digits or tokenized value
    card_holder_name = Column(String(255), nullable=True)
    expiry_date = Column(String(10), nullable=True)  # Format: MM/YY
    billing_address = Column(Text, nullable=True)
    config = Column(JSON, nullable=True)  # Renamed from metadata
    is_default = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="payment_methods")

    def __repr__(self):
        return f"<PaymentMethod(id={self.id}, user_id={self.user_id}, type={self.type}, provider={self.provider})>"
