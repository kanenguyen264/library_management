from pydantic import BaseModel, Field, validator
from typing import Optional, Any, Dict, List
from datetime import datetime

class AchievementBase(BaseModel):
    """Schema cơ bản cho Achievement."""
    name: str
    description: Optional[str] = None
    icon_url: Optional[str] = None
    criteria_json: Optional[Dict[str, Any]] = None
    points: int = 0
    difficulty_level: Optional[str] = None
    is_active: bool = True
    
class AchievementCreate(AchievementBase):
    """Schema tạo mới Achievement."""
    @validator('difficulty_level')
    def validate_difficulty_level(cls, v):
        """Kiểm tra độ khó hợp lệ."""
        if v is None:
            return v
            
        valid_levels = ['easy', 'medium', 'hard', 'expert']
        if v not in valid_levels:
            raise ValueError(f"Độ khó phải là một trong: {', '.join(valid_levels)}")
        return v
    
    @validator('points')
    def validate_points(cls, v):
        """Kiểm tra điểm thưởng hợp lệ."""
        if v < 0:
            raise ValueError("Điểm thưởng không được âm")
        return v

class AchievementUpdate(BaseModel):
    """Schema cập nhật Achievement."""
    name: Optional[str] = None
    description: Optional[str] = None
    icon_url: Optional[str] = None
    criteria_json: Optional[Dict[str, Any]] = None
    points: Optional[int] = None
    difficulty_level: Optional[str] = None
    is_active: Optional[bool] = None
    
    @validator('difficulty_level')
    def validate_difficulty_level(cls, v):
        """Kiểm tra độ khó hợp lệ."""
        if v is None:
            return v
            
        valid_levels = ['easy', 'medium', 'hard', 'expert']
        if v not in valid_levels:
            raise ValueError(f"Độ khó phải là một trong: {', '.join(valid_levels)}")
        return v
    
    @validator('points')
    def validate_points(cls, v):
        """Kiểm tra điểm thưởng hợp lệ."""
        if v is not None and v < 0:
            raise ValueError("Điểm thưởng không được âm")
        return v

class AchievementInDB(AchievementBase):
    """Schema Achievement trong database."""
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class AchievementInfo(AchievementInDB):
    """Schema thông tin Achievement."""
    class Config:
        from_attributes = True
