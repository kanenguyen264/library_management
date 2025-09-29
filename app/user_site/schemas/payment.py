from typing import List, Optional, Dict
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


class PaymentStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class PaymentMethodType(str, Enum):
    CREDIT_CARD = "credit_card"
    PAYPAL = "paypal"
    BANK_TRANSFER = "bank_transfer"


class PaymentMethodBase(BaseModel):
    type: PaymentMethodType
    provider: str
    account_number: Optional[str] = None
    expiry_date: Optional[str] = None
    card_holder_name: Optional[str] = None
    is_default: bool = False


class PaymentMethodCreate(PaymentMethodBase):
    pass


class PaymentMethodUpdate(BaseModel):
    type: Optional[PaymentMethodType] = None
    provider: Optional[str] = None
    account_number: Optional[str] = None
    expiry_date: Optional[str] = None
    card_holder_name: Optional[str] = None
    is_default: Optional[bool] = None


class PaymentMethodResponse(PaymentMethodBase):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class PaymentMethodListResponse(BaseModel):
    items: List[PaymentMethodResponse]
    total: int

    class Config:
        from_attributes = True


class PaymentBase(BaseModel):
    amount: float
    currency: str = "USD"
    payment_method: str
    subscription_id: Optional[int] = None
    description: Optional[str] = None


class PaymentCreate(PaymentBase):
    pass


class PaymentUpdate(BaseModel):
    amount: Optional[float] = None
    currency: Optional[str] = None
    payment_method: Optional[str] = None
    subscription_id: Optional[int] = None
    description: Optional[str] = None
    status: Optional[PaymentStatus] = None
    error_message: Optional[str] = None


class PaymentResponse(PaymentBase):
    id: int
    user_id: int
    status: PaymentStatus
    transaction_id: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PaymentListResponse(BaseModel):
    items: List[PaymentResponse]
    total: int

    class Config:
        from_attributes = True


class PaymentStatusUpdate(BaseModel):
    """Cập nhật trạng thái thanh toán."""

    status: PaymentStatus
    transaction_id: Optional[str] = None
    error_message: Optional[str] = None


class PaymentRefund(BaseModel):
    """Yêu cầu hoàn tiền cho thanh toán."""

    reason: str
    amount: Optional[float] = None  # Nếu None sẽ hoàn toàn bộ số tiền
    refund_to_original_method: bool = True


class PaymentStats(BaseModel):
    """Thống kê thanh toán."""

    total_amount: float = 0
    count: int = 0
    successful_amount: float = 0
    successful_count: int = 0
    refunded_amount: float = 0
    refunded_count: int = 0
    failed_count: int = 0
    by_month: Dict[str, float] = {}
    by_payment_method: Dict[str, float] = {}


class PaymentStatsResponse(BaseModel):
    """Phản hồi thống kê thanh toán."""

    stats: PaymentStats
    period: str
    currency: str = "USD"

    class Config:
        from_attributes = True


class PaymentSearchParams(BaseModel):
    """Tham số tìm kiếm thanh toán."""

    query: Optional[str] = None
    status: Optional[List[PaymentStatus]] = None
    payment_method: Optional[List[str]] = None
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
