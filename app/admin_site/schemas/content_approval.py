from pydantic import BaseModel, Field, validator
from typing import Optional, Any, Dict, List
from datetime import datetime

class ContentApprovalBase(BaseModel):
    """Schema cơ bản cho ContentApprovalQueue."""
    content_type: str
    content_id: int
    submitted_by: int
    
class ContentApprovalCreate(ContentApprovalBase):
    """Schema tạo mới ContentApprovalQueue."""
    @validator('content_type')
    def validate_content_type(cls, v):
        """Kiểm tra loại nội dung hợp lệ."""
        valid_types = ['book', 'chapter', 'review', 'discussion', 'author', 'quote']
        if v not in valid_types:
            raise ValueError(f"Loại nội dung phải là một trong: {', '.join(valid_types)}")
        return v

class ContentApprovalUpdate(BaseModel):
    """Schema cập nhật ContentApprovalQueue."""
    content_type: Optional[str] = None
    content_id: Optional[int] = None
    
    @validator('content_type')
    def validate_content_type(cls, v):
        """Kiểm tra loại nội dung hợp lệ."""
        if v is None:
            return v
            
        valid_types = ['book', 'chapter', 'review', 'discussion', 'author', 'quote']
        if v not in valid_types:
            raise ValueError(f"Loại nội dung phải là một trong: {', '.join(valid_types)}")
        return v

class ContentApprovalInDB(ContentApprovalBase):
    """Schema ContentApprovalQueue trong database."""
    id: int
    status: str
    reviewer_id: Optional[int] = None
    review_notes: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class ContentApprovalInfo(ContentApprovalInDB):
    """Schema thông tin ContentApprovalQueue."""
    class Config:
        from_attributes = True

class ContentApprovalAction(BaseModel):
    """Schema hành động phê duyệt/từ chối."""
    notes: Optional[str] = None
