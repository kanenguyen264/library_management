from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, validator
from app.user_site.models.recommendation import RecommendationType


class RecommendationBase(BaseModel):
    """Base schema for recommendation data"""

    user_id: Optional[int] = None
    book_id: Optional[int] = None
    recommendation_type: str
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: Optional[str] = None
    is_active: bool = True

    @validator("recommendation_type")
    def validate_recommendation_type(cls, v):
        try:
            # Verify the recommendation type is valid
            RecommendationType(v)
            return v
        except ValueError:
            valid_types = [t.value for t in RecommendationType]
            raise ValueError(
                f"Invalid recommendation type. Must be one of: {', '.join(valid_types)}"
            )


class RecommendationCreate(RecommendationBase):
    """Schema for creating a new recommendation"""

    metadata: Optional[Dict[str, Any]] = None


class RecommendationUpdate(BaseModel):
    """Schema for updating an existing recommendation"""

    user_id: Optional[int] = None
    book_id: Optional[int] = None
    recommendation_type: Optional[str] = None
    score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    reason: Optional[str] = None
    is_active: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None

    @validator("recommendation_type")
    def validate_recommendation_type(cls, v):
        if v is None:
            return v
        try:
            # Verify the recommendation type is valid
            RecommendationType(v)
            return v
        except ValueError:
            valid_types = [t.value for t in RecommendationType]
            raise ValueError(
                f"Invalid recommendation type. Must be one of: {', '.join(valid_types)}"
            )


class RecommendationResponse(RecommendationBase):
    """Schema for recommendation response"""

    id: int
    created_at: datetime
    updated_at: datetime
    metadata: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True
