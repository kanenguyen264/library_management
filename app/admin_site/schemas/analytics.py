from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import date, datetime

class AnalyticsBase(BaseModel):
    """Schema cơ sở cho phân tích."""
    start_date: date
    end_date: date

class UserAnalyticsDataPoint(BaseModel):
    """Schema điểm dữ liệu phân tích người dùng."""
    date: date
    new_users: int
    active_users: int
    total_users: int

class UserAnalyticsResponse(AnalyticsBase):
    """Schema phản hồi phân tích người dùng."""
    summary: Dict[str, Any]
    data_points: List[UserAnalyticsDataPoint]
    demographics: Optional[Dict[str, List[Dict[str, Any]]]] = None
    engagement_metrics: Optional[Dict[str, Any]] = None

class ContentAnalyticsDataPoint(BaseModel):
    """Schema điểm dữ liệu phân tích nội dung."""
    date: date
    new_content: int
    views: int
    reads: int
    likes: int
    reviews: int

class ContentAnalyticsResponse(AnalyticsBase):
    """Schema phản hồi phân tích nội dung."""
    summary: Dict[str, Any]
    data_points: List[ContentAnalyticsDataPoint]
    popular_content: Optional[List[Dict[str, Any]]] = None
    categories_distribution: Optional[List[Dict[str, Any]]] = None

class RevenueAnalyticsDataPoint(BaseModel):
    """Schema điểm dữ liệu phân tích doanh thu."""
    date: date
    total_revenue: float
    subscription_revenue: float
    one_time_purchases: float
    new_subscriptions: int

class RevenueAnalyticsResponse(AnalyticsBase):
    """Schema phản hồi phân tích doanh thu."""
    summary: Dict[str, Any]
    data_points: List[RevenueAnalyticsDataPoint]
    subscription_breakdown: Optional[List[Dict[str, Any]]] = None
    payment_methods: Optional[List[Dict[str, Any]]] = None
    
class EngagementAnalyticsDataPoint(BaseModel):
    """Schema điểm dữ liệu phân tích tương tác."""
    date: date
    sessions: int
    page_views: int
    reading_time: float
    interactions: int

class EngagementAnalyticsResponse(AnalyticsBase):
    """Schema phản hồi phân tích tương tác."""
    summary: Dict[str, Any]
    data_points: List[EngagementAnalyticsDataPoint]
    peak_hours: Optional[List[Dict[str, Any]]] = None
    feature_usage: Optional[List[Dict[str, Any]]] = None
