from pydantic import BaseModel, Field, validator
from typing import Optional, Any, Dict, List
from datetime import datetime, date


class FeaturedContentBase(BaseModel):
    """Schema cơ bản cho FeaturedContent."""

    content_type: str
    content_id: int
    position: Optional[int] = 0
    start_date: datetime
    end_date: Optional[datetime] = None


class FeaturedContentCreate(FeaturedContentBase):
    """Schema tạo mới FeaturedContent."""

    @validator("content_type")
    def validate_content_type(cls, v):
        """Kiểm tra loại nội dung hợp lệ."""
        valid_types = ["book", "author", "series", "collection", "promotion"]
        if v not in valid_types:
            raise ValueError(
                f"Loại nội dung phải là một trong: {', '.join(valid_types)}"
            )
        return v

    @validator("end_date")
    def validate_end_date(cls, v, values):
        """Kiểm tra ngày kết thúc hợp lệ."""
        if v and "start_date" in values and v <= values["start_date"]:
            raise ValueError("Ngày kết thúc phải sau ngày bắt đầu")
        return v


class FeaturedContentUpdate(BaseModel):
    """Schema cập nhật FeaturedContent."""

    position: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

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


class FeaturedContentInDB(FeaturedContentBase):
    """Schema FeaturedContent trong database."""

    id: int
    created_by: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class FeaturedContentInfo(FeaturedContentInDB):
    """Schema thông tin FeaturedContent."""

    is_active: bool = True  # Tính toán dựa trên ngày

    class Config:
        from_attributes = True


class FeaturedContentResponse(FeaturedContentInfo):
    """Schema phản hồi cho FeaturedContent API."""

    content_details: Optional[Dict[str, Any]] = None
    admin_name: Optional[str] = None

    class Config:
        from_attributes = True
