from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import date, datetime
from app.admin_site.models.report import ReportStatus, ReportType, ReportEntityType


# User Report Models
class UserGrowthData(BaseModel):
    date: date
    new_users: int
    total_users: int


class UserDemographicData(BaseModel):
    category: str
    count: int
    percentage: float


class UserEngagementData(BaseModel):
    metric: str
    value: float
    change_percentage: Optional[float] = None


class UserReportResponse(BaseModel):
    start_date: date
    end_date: date
    summary: Dict[str, Any]
    growth_data: List[UserGrowthData]
    demographics: Dict[str, List[UserDemographicData]]
    engagement: List[UserEngagementData]
    retention_rate: float
    active_users: Dict[str, int]  # daily, weekly, monthly
    dormant_users: int
    top_users: List[Dict[str, Any]]


# Content Report Models
class ContentCountData(BaseModel):
    date: date
    books: int
    authors: int
    reviews: int


class ContentPopularityData(BaseModel):
    id: int
    title: str
    author: Optional[str] = None
    views: int
    reads: int
    rating: Optional[float] = None


class CategoryDistributionData(BaseModel):
    category: str
    count: int
    percentage: float


class ContentReportResponse(BaseModel):
    start_date: date
    end_date: date
    summary: Dict[str, Any]
    content_counts: List[ContentCountData]
    popular_books: List[ContentPopularityData]
    popular_authors: List[Dict[str, Any]]
    category_distribution: List[CategoryDistributionData]
    review_stats: Dict[str, Any]
    reading_stats: Dict[str, Any]


# Financial Report Models
class RevenueData(BaseModel):
    date: date
    amount: float
    subscription_revenue: float
    one_time_purchases: float


class SubscriptionData(BaseModel):
    plan: str
    count: int
    revenue: float
    percentage: float


class FinancialReportResponse(BaseModel):
    start_date: date
    end_date: date
    summary: Dict[str, Any]
    revenue_data: List[RevenueData]
    subscription_data: List[SubscriptionData]
    conversion_rate: float
    average_revenue_per_user: float
    churn_rate: float
    lifetime_value: float
    payment_methods: List[Dict[str, Any]]
    revenue_by_country: List[Dict[str, Any]]


# System Report Models
class PerformanceMetricData(BaseModel):
    timestamp: datetime
    response_time: float
    cpu_usage: float
    memory_usage: float
    active_connections: int


class ErrorCountData(BaseModel):
    date: date
    count: int
    category: str


class SystemReportResponse(BaseModel):
    start_date: date
    end_date: date
    summary: Dict[str, Any]
    performance_metrics: List[PerformanceMetricData]
    error_counts: List[ErrorCountData]
    uptime_percentage: float
    average_response_time: float
    peak_usage_times: List[Dict[str, Any]]
    resource_utilization: Dict[str, Any]
    api_usage: List[Dict[str, Any]]
    cache_effectiveness: Dict[str, Any]


# Activity Report Models
class ActivityCountData(BaseModel):
    date: date
    views: int
    reads: int
    downloads: int
    interactions: int


class UserActivityData(BaseModel):
    hour: int
    count: int
    percentage: float


class ActivityReportResponse(BaseModel):
    start_date: date
    end_date: date
    summary: Dict[str, Any]
    activity_counts: List[ActivityCountData]
    peak_hours: List[UserActivityData]
    most_active_days: List[Dict[str, Any]]
    user_sessions: Dict[str, Any]
    feature_usage: List[Dict[str, Any]]
    search_queries: List[Dict[str, Any]]
    reading_sessions: Dict[str, Any]


class ReportBase(BaseModel):
    """Base schema for report data"""

    entity_type: ReportEntityType
    entity_id: int
    report_type: ReportType
    description: Optional[str] = None


class ReportCreate(ReportBase):
    """Schema for creating a new report"""

    reporter_id: Optional[int] = None
    status: ReportStatus = ReportStatus.PENDING


class ReportUpdate(BaseModel):
    """Schema for updating an existing report"""

    status: Optional[ReportStatus] = None
    admin_notes: Optional[str] = None
    handled_by: Optional[int] = None


class ReportResponse(ReportBase):
    """Schema for report response"""

    id: int
    reporter_id: Optional[int] = None
    status: ReportStatus
    admin_notes: Optional[str] = None
    handled_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ReporterInfo(BaseModel):
    """Brief information about the reporter"""

    id: int
    username: str
    email: Optional[str] = None

    class Config:
        from_attributes = True


class AdminInfo(BaseModel):
    """Brief information about the admin who handled the report"""

    id: int
    username: str

    class Config:
        from_attributes = True


class ReportDetailResponse(ReportResponse):
    """Detailed report response including reporter and admin info"""

    reporter: Optional[ReporterInfo] = None
    admin_handler: Optional[AdminInfo] = None

    class Config:
        from_attributes = True


class ReportListResponse(BaseModel):
    """Schema for a list of reports"""

    items: List[ReportResponse]
    total: int

    class Config:
        from_attributes = True
