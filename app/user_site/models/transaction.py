import json
from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    ForeignKey,
    Text,
    DateTime,
    Index,
    Enum,
    JSON,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.ext.mutable import MutableDict
import uuid
import enum

from app.common.db.base_class import BaseModel
from app.user_site.models.user import User
from app.user_site.schemas.transaction import (
    TransactionType,
    TransactionStatus,
    PaymentMethod,
    EntityType,
)


class Transaction(BaseModel):
    """Model for user transactions."""

    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_user_status", "user_id", "status"),
        Index("ix_transactions_user_type", "user_id", "transaction_type"),
        Index("ix_transactions_created_at", "created_at"),
        Index(
            "ix_transactions_related_entity", "related_entity_type", "related_entity_id"
        ),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount = Column(Float, nullable=False)
    currency = Column(String(10), nullable=False, default="USD")
    transaction_type = Column(Enum(TransactionType), nullable=False)
    status = Column(
        Enum(TransactionStatus), nullable=False, default=TransactionStatus.PENDING
    )
    payment_method = Column(Enum(PaymentMethod), nullable=True)
    description = Column(Text, nullable=True)
    transaction_metadata = Column(JSON, nullable=True)
    reference_code = Column(String(100), nullable=True, unique=True, index=True)
    payment_url = Column(String(500), nullable=True)
    original_transaction_id = Column(
        Integer, ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True
    )
    refund_reason = Column(Text, nullable=True)
    gateway_response = Column(JSON, nullable=True)
    related_entity_type = Column(Enum(EntityType), nullable=True)
    related_entity_id = Column(Integer, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="transactions")
    original_transaction = relationship(
        "Transaction", remote_side=[id], backref="refund_transactions"
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.reference_code:
            self.reference_code = f"TXN-{uuid.uuid4().hex[:10].upper()}"

    def mark_as_completed(self):
        """Mark the transaction as completed and set completion timestamp."""
        self.status = TransactionStatus.COMPLETED
        self.completed_at = datetime.utcnow()

    def mark_as_failed(self):
        """Mark the transaction as failed."""
        self.status = TransactionStatus.FAILED

    def mark_as_refunded(self):
        """Mark the transaction as refunded."""
        self.status = TransactionStatus.REFUNDED

    def to_dict(self) -> Dict[str, Any]:
        """Convert the transaction model to a dictionary."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "amount": self.amount,
            "currency": self.currency,
            "transaction_type": self.transaction_type.value,
            "status": self.status.value,
            "payment_method": (
                self.payment_method.value if self.payment_method else None
            ),
            "description": self.description,
            "metadata": self.transaction_metadata,
            "reference_code": self.reference_code,
            "payment_url": self.payment_url,
            "original_transaction_id": self.original_transaction_id,
            "refund_reason": self.refund_reason,
            "gateway_response": self.gateway_response,
            "related_entity_type": (
                self.related_entity_type.value if self.related_entity_type else None
            ),
            "related_entity_id": self.related_entity_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
        }

    def get_metadata(self) -> Dict[str, Any]:
        """Trả về metadata dưới dạng dict."""
        if self.transaction_metadata is None:
            return {}
        return self.transaction_metadata

    def update_metadata(self, data: Dict[str, Any]) -> None:
        """Cập nhật metadata."""
        current = self.get_metadata()
        current.update(data)
        self.transaction_metadata = current

    def add_gateway_response(self, response: Dict[str, Any]) -> None:
        """Thêm phản hồi từ cổng thanh toán."""
        if self.gateway_response is None:
            self.gateway_response = {}
        self.gateway_response.update(response)

    @property
    def is_pending(self) -> bool:
        """Kiểm tra giao dịch có đang chờ xử lý không."""
        return self.status == TransactionStatus.PENDING

    @property
    def is_completed(self) -> bool:
        """Kiểm tra giao dịch đã hoàn thành chưa."""
        return self.status == TransactionStatus.COMPLETED

    @property
    def is_failed(self) -> bool:
        """Kiểm tra giao dịch có thất bại không."""
        return self.status == TransactionStatus.FAILED

    @property
    def is_refunded(self) -> bool:
        """Kiểm tra giao dịch đã được hoàn tiền chưa."""
        return self.status == TransactionStatus.REFUNDED

    @property
    def age_in_seconds(self) -> int:
        """Tính tuổi của giao dịch tính bằng giây."""
        if self.created_at is None:
            return 0
        delta = datetime.utcnow() - self.created_at
        return int(delta.total_seconds())

    def __repr__(self) -> str:
        return f"<Transaction {self.id}: {self.transaction_type} - {self.amount} {self.currency} - {self.status}>"
