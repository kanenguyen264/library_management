from typing import List, Optional, Dict, Any
from datetime import datetime, date
from pydantic import BaseModel, Field
from enum import Enum


class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    PENDING = "pending"


class SubscriptionType(str, Enum):
    STANDARD = "standard"
    PREMIUM = "premium"
    GOLD = "gold"
    FAMILY = "family"
    STUDENT = "student"


class BillingPeriod(str, Enum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class SubscriptionPlanBase(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    currency: str = "USD"
    billing_cycle: str
    features_json: Optional[dict] = None
    is_active: bool = True


class SubscriptionPlanResponse(SubscriptionPlanBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SubscriptionPlanListResponse(BaseModel):
    items: List[SubscriptionPlanResponse]
    total: int

    class Config:
        from_attributes = True


class SubscriptionBase(BaseModel):
    plan_id: int
    payment_method: Optional[str] = None
    auto_renew: bool = True
    renewal_date: Optional[datetime] = None
    billing_info_json: Optional[dict] = None


class SubscriptionCreate(SubscriptionBase):
    pass


class SubscriptionUpdate(BaseModel):
    plan_id: Optional[int] = None
    payment_method: Optional[str] = None
    auto_renew: Optional[bool] = None
    renewal_date: Optional[datetime] = None
    billing_info_json: Optional[dict] = None
    status: Optional[SubscriptionStatus] = None


class SubscriptionResponse(SubscriptionBase):
    id: int
    user_id: int
    status: SubscriptionStatus
    start_date: datetime
    end_date: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    plan: Optional[SubscriptionPlanResponse] = None

    class Config:
        from_attributes = True


class SubscriptionListResponse(BaseModel):
    items: List[SubscriptionResponse]
    total: int
    page: Optional[int] = 1
    size: Optional[int] = 10

    class Config:
        from_attributes = True


class SubscriptionStatsResponse(BaseModel):
    total_subscriptions: int
    active_subscriptions: int
    expired_subscriptions: int
    cancelled_subscriptions: int
    pending_subscriptions: int
    subscriptions_by_type: Dict[str, int] = {}
    subscriptions_by_plan: Dict[str, int] = {}
    revenue_by_period: Dict[str, float] = {}
    renewals_due_next_month: int = 0
    new_subscriptions_this_month: int = 0
    cancellations_this_month: int = 0
    average_subscription_duration: float = 0  # días
    renewal_rate: float = 0  # porcentaje
    most_popular_plans: List[Dict[str, Any]] = []
    recent_subscriptions: List[SubscriptionResponse] = []

    class Config:
        from_attributes = True


class SubscriptionUsageResponse(BaseModel):
    """Phản hồi sử dụng gói đăng ký."""

    subscription_id: int
    user_id: int
    plan_name: str
    books_accessed: int
    books_remaining: Optional[int] = None
    download_count: int
    downloads_remaining: Optional[int] = None
    audio_minutes_used: int
    audio_minutes_remaining: Optional[int] = None
    special_content_accessed: int
    special_offers_used: int
    usage_percentage: float
    start_date: datetime
    end_date: datetime
    is_unlimited: bool = False

    class Config:
        from_attributes = True


class SubscriptionExtendRequest(BaseModel):
    """Yêu cầu gia hạn gói đăng ký."""

    subscription_id: int
    duration_days: int
    reason: Optional[str] = None
    payment_method_id: Optional[int] = None
    prorate: bool = True
