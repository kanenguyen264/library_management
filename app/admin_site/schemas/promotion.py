from pydantic import BaseModel, Field, validator
from typing import Optional, Any, Dict, List
from datetime import datetime, date


class PromotionBase(BaseModel):
    """Schema cơ bản cho Promotion."""

    name: str
    description: Optional[str] = None
    discount_type: str
    discount_value: float
    start_date: datetime
    end_date: Optional[datetime] = None
    coupon_code: Optional[str] = None
    usage_limit: Optional[int] = None
    is_active: bool = True


class PromotionCreate(PromotionBase):
    """Schema tạo mới Promotion."""

    @validator("discount_type")
    def validate_discount_type(cls, v):
        """Kiểm tra loại giảm giá hợp lệ."""
        valid_types = ["percentage", "fixed_amount"]
        if v not in valid_types:
            raise ValueError(
                f"Loại giảm giá phải là một trong: {', '.join(valid_types)}"
            )
        return v

    @validator("discount_value")
    def validate_discount_value(cls, v, values):
        """Kiểm tra giá trị giảm giá hợp lệ."""
        if "discount_type" in values:
            if values["discount_type"] == "percentage" and (v <= 0 or v > 100):
                raise ValueError(
                    "Giảm giá theo phần trăm phải nằm trong khoảng (0, 100]"
                )
            elif values["discount_type"] == "fixed_amount" and v <= 0:
                raise ValueError("Giảm giá theo số tiền phải lớn hơn 0")
        return v

    @validator("end_date")
    def validate_end_date(cls, v, values):
        """Kiểm tra ngày kết thúc hợp lệ."""
        if v and "start_date" in values and v <= values["start_date"]:
            raise ValueError("Ngày kết thúc phải sau ngày bắt đầu")
        return v

    @validator("coupon_code")
    def validate_coupon_code(cls, v):
        """Chuẩn hóa mã khuyến mãi."""
        if v:
            return v.upper()
        return v


class PromotionUpdate(BaseModel):
    """Schema cập nhật Promotion."""

    name: Optional[str] = None
    description: Optional[str] = None
    discount_type: Optional[str] = None
    discount_value: Optional[float] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    coupon_code: Optional[str] = None
    usage_limit: Optional[int] = None
    is_active: Optional[bool] = None

    @validator("discount_type")
    def validate_discount_type(cls, v):
        """Kiểm tra loại giảm giá hợp lệ."""
        if v is None:
            return v

        valid_types = ["percentage", "fixed_amount"]
        if v not in valid_types:
            raise ValueError(
                f"Loại giảm giá phải là một trong: {', '.join(valid_types)}"
            )
        return v

    @validator("discount_value")
    def validate_discount_value(cls, v, values):
        """Kiểm tra giá trị giảm giá hợp lệ."""
        if v is None:
            return v

        if "discount_type" in values and values["discount_type"]:
            if values["discount_type"] == "percentage" and (v <= 0 or v > 100):
                raise ValueError(
                    "Giảm giá theo phần trăm phải nằm trong khoảng (0, 100]"
                )
            elif values["discount_type"] == "fixed_amount" and v <= 0:
                raise ValueError("Giảm giá theo số tiền phải lớn hơn 0")
        return v

    @validator("end_date")
    def validate_end_date(cls, v, values):
        """Kiểm tra ngày kết thúc hợp lệ."""
        if (
            v
            and "start_date" in values
            and values["start_date"]
            and v <= values["start_date"]
        ):
            raise ValueError("Ngày kết thúc phải sau ngày bắt đầu")
        return v

    @validator("coupon_code")
    def validate_coupon_code(cls, v):
        """Chuẩn hóa mã khuyến mãi."""
        if v:
            return v.upper()
        return v


class PromotionInDB(PromotionBase):
    """Schema Promotion trong database."""

    id: int
    usage_count: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PromotionInfo(PromotionInDB):
    """Schema thông tin Promotion."""

    is_expired: bool = False  # Tính toán dựa trên ngày
    remaining_uses: Optional[int] = None  # Số lượng sử dụng còn lại

    class Config:
        from_attributes = True
