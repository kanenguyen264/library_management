from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, validator, root_validator
from decimal import Decimal


class TransactionType(str, Enum):
    """Loại giao dịch."""

    PAYMENT = "payment"
    REFUND = "refund"
    CREDIT = "credit"
    DEBIT = "debit"
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    SUBSCRIPTION = "subscription"
    OTHER = "other"


class TransactionStatus(str, Enum):
    """Trạng thái của giao dịch."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    EXPIRED = "expired"
    PROCESSING = "processing"


class PaymentMethod(str, Enum):
    """Phương thức thanh toán."""

    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    BANK_TRANSFER = "bank_transfer"
    E_WALLET = "e_wallet"
    PAYPAL = "paypal"
    CRYPTO = "crypto"
    CASH = "cash"
    OTHER = "other"


class EntityType(str, Enum):
    """Loại thực thể liên quan đến giao dịch."""

    BOOK = "book"
    SUBSCRIPTION = "subscription"
    AUTHOR = "author"
    USER = "user"
    SERVICE = "service"
    OTHER = "other"


class TransactionBase(BaseModel):
    """Base schema cho giao dịch."""

    amount: Decimal = Field(..., description="Số tiền giao dịch")
    currency: str = Field(default="USD", description="Loại tiền tệ")
    transaction_type: TransactionType = Field(..., description="Loại giao dịch")
    payment_method: Optional[PaymentMethod] = Field(
        None, description="Phương thức thanh toán"
    )
    description: Optional[str] = Field(None, description="Mô tả giao dịch")
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="Thông tin bổ sung"
    )
    related_entity_type: Optional[EntityType] = Field(
        None, description="Loại thực thể liên quan"
    )
    related_entity_id: Optional[int] = Field(
        None, description="ID của thực thể liên quan"
    )


class TransactionCreate(TransactionBase):
    """Schema để tạo giao dịch mới."""

    pass


class TransactionUpdate(BaseModel):
    """Schema để cập nhật giao dịch."""

    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    transaction_type: Optional[TransactionType] = None
    status: Optional[TransactionStatus] = None
    payment_method: Optional[PaymentMethod] = None
    description: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    payment_url: Optional[str] = None
    gateway_response: Optional[Dict[str, Any]] = None


class TransactionResponse(TransactionBase):
    """Schema để trả về thông tin giao dịch."""

    id: int
    user_id: int
    status: TransactionStatus
    reference_code: Optional[str] = None
    payment_url: Optional[str] = None
    original_transaction_id: Optional[int] = None
    refund_reason: Optional[str] = None
    gateway_response: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TransactionListResponse(BaseModel):
    """Schema để trả về danh sách giao dịch."""

    items: List[TransactionResponse]
    total: int
    page: int
    page_size: int
    pages: int

    @validator("pages")
    def compute_pages(cls, v, values):
        """Tính số trang dựa trên tổng số mục và kích thước trang."""
        if "total" not in values or "page_size" not in values:
            return 0
        return max(
            1, (values["total"] + values["page_size"] - 1) // values["page_size"]
        )


class TransactionFilterParams(BaseModel):
    """Các tham số để lọc giao dịch."""

    status: Optional[TransactionStatus] = None
    transaction_type: Optional[TransactionType] = None
    payment_method: Optional[PaymentMethod] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    min_amount: Optional[Decimal] = None
    max_amount: Optional[Decimal] = None
    related_entity_type: Optional[EntityType] = None
    related_entity_id: Optional[int] = None

    @root_validator(skip_on_failure=True)
    def validate_dates(cls, values):
        """Kiểm tra ngày bắt đầu và kết thúc."""
        start_date = values.get("start_date")
        end_date = values.get("end_date")
        if start_date and end_date and start_date > end_date:
            raise ValueError("Ngày bắt đầu phải trước ngày kết thúc")
        return values

    @root_validator(skip_on_failure=True)
    def validate_amount_range(cls, values):
        """Kiểm tra khoảng số tiền."""
        min_amount = values.get("min_amount")
        max_amount = values.get("max_amount")
        if (
            min_amount is not None
            and max_amount is not None
            and min_amount > max_amount
        ):
            raise ValueError("Số tiền tối thiểu phải nhỏ hơn hoặc bằng số tiền tối đa")
        return values


class TransactionSummaryResponse(BaseModel):
    """Schema để trả về tổng hợp giao dịch của người dùng."""

    total_spent: Decimal
    transactions_count: Dict[TransactionType, int]
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None


class TransactionStatisticsResponse(BaseModel):
    """Schema để trả về thống kê giao dịch."""

    total_count: int
    total_amount: Decimal
    by_type: Dict[TransactionType, Dict[str, Union[int, Decimal]]]
    daily_stats: Dict[str, Dict[str, Union[int, Decimal]]]
    period_start: datetime
    period_end: datetime
    days: int


class PaymentRequest(BaseModel):
    """Schema yêu cầu thanh toán."""

    amount: Decimal = Field(..., description="Số tiền thanh toán")
    currency: str = Field(default="USD", description="Loại tiền tệ")
    payment_method: PaymentMethod = Field(..., description="Phương thức thanh toán")
    description: Optional[str] = Field(None, description="Mô tả thanh toán")
    related_entity_type: Optional[EntityType] = Field(
        None, description="Loại thực thể liên quan"
    )
    related_entity_id: Optional[int] = Field(
        None, description="ID của thực thể liên quan"
    )
    return_url: Optional[str] = Field(
        None, description="URL chuyển hướng sau khi thanh toán thành công"
    )
    cancel_url: Optional[str] = Field(
        None, description="URL chuyển hướng sau khi hủy thanh toán"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="Thông tin bổ sung"
    )


class PaymentResponse(BaseModel):
    """Schema phản hồi yêu cầu thanh toán."""

    transaction_id: int
    reference_code: str
    amount: Decimal
    currency: str
    status: TransactionStatus
    payment_url: Optional[str] = None
    created_at: datetime


class RefundRequest(BaseModel):
    """Schema yêu cầu hoàn tiền."""

    transaction_id: int = Field(..., description="ID giao dịch cần hoàn tiền")
    amount: Optional[Decimal] = Field(
        None, description="Số tiền hoàn lại (nếu không có sẽ hoàn toàn bộ)"
    )
    reason: str = Field(..., description="Lý do hoàn tiền")
