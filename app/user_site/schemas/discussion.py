from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, validator
from app.user_site.schemas.user import UserPublicResponse


class DiscussionBase(BaseModel):
    title: str = Field(..., min_length=3, max_length=255)
    content: str = Field(..., min_length=10)
    is_spoiler: Optional[bool] = False


class DiscussionCreate(DiscussionBase):
    book_id: int
    chapter_id: Optional[int] = None


class DiscussionUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=255)
    content: Optional[str] = Field(None, min_length=10)
    is_spoiler: Optional[bool] = None


class UserBrief(BaseModel):
    id: int
    username: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None

    class Config:
        from_attributes = True


class DiscussionResponse(DiscussionBase):
    id: int
    book_id: int
    chapter_id: Optional[int] = None
    user_id: int
    upvotes: int
    downvotes: int
    comments_count: int
    is_pinned: bool
    created_at: datetime
    updated_at: datetime
    user: Optional[UserBrief] = None

    class Config:
        from_attributes = True


class DiscussionListResponse(BaseModel):
    items: List[DiscussionResponse]
    total: int


class CommentBase(BaseModel):
    content: str = Field(..., min_length=1)
    is_spoiler: Optional[bool] = False


class CommentCreate(CommentBase):
    discussion_id: int
    parent_id: Optional[int] = None


class CommentUpdate(BaseModel):
    content: Optional[str] = Field(None, min_length=1)
    is_spoiler: Optional[bool] = None


class CommentResponse(CommentBase):
    id: int
    discussion_id: int
    user_id: int
    parent_id: Optional[int] = None
    upvotes: int
    downvotes: int
    created_at: datetime
    updated_at: datetime
    user: Optional[UserBrief] = None
    replies: Optional[List["CommentResponse"]] = None

    class Config:
        from_attributes = True


class CommentListResponse(BaseModel):
    items: List[CommentResponse]
    total: int


# Để giải quyết vấn đề reference trước khi đã khai báo
CommentResponse.update_forward_refs()


class FollowingResponse(BaseModel):
    follower_id: int
    following_id: int
    follower: Optional[UserPublicResponse] = None
    following: Optional[UserPublicResponse] = None
    created_at: datetime

    class Config:
        from_attributes = True


# Thêm các model còn thiếu
class DiscussionCommentCreate(BaseModel):
    content: str = Field(..., min_length=1, description="Nội dung bình luận")
    parent_id: Optional[int] = Field(
        None, description="ID của bình luận cha (nếu trả lời)"
    )
    is_spoiler: Optional[bool] = Field(
        False, description="Đánh dấu bình luận có spoiler"
    )
    user_id: Optional[int] = Field(
        None, description="ID của người dùng (có thể bỏ qua nếu dùng token)"
    )


class DiscussionCommentUpdate(BaseModel):
    content: Optional[str] = Field(
        None, min_length=1, description="Nội dung bình luận mới"
    )
    is_spoiler: Optional[bool] = Field(None, description="Cập nhật trạng thái spoiler")


class DiscussionCommentInfo(BaseModel):
    id: int
    discussion_id: int
    user_id: int
    parent_id: Optional[int] = None
    content: str
    is_spoiler: bool
    upvotes: int
    downvotes: int
    created_at: datetime
    updated_at: datetime
    user: Optional[UserBrief] = None
    replies_count: Optional[int] = 0

    class Config:
        from_attributes = True


class DiscussionCommentResponse(BaseModel):
    id: int
    discussion_id: int
    user_id: int
    parent_id: Optional[int] = None
    content: str
    is_spoiler: bool
    upvotes: int
    downvotes: int
    created_at: datetime
    updated_at: datetime
    user: Optional[UserBrief] = None
    replies: Optional[List["DiscussionCommentResponse"]] = []

    class Config:
        from_attributes = True


# Forward reference
DiscussionCommentResponse.update_forward_refs()


class DiscussionCommentListResponse(BaseModel):
    items: List[DiscussionCommentResponse]
    total: int
    page: int
    page_size: int
    pages: int


class DiscussionStatistics(BaseModel):
    total_discussions: int
    total_comments: int
    most_active_books: List[Dict[str, Any]] = []
    most_commented_discussions: List[DiscussionResponse] = []
    recent_discussions: List[DiscussionResponse] = []
    most_active_users: List[Dict[str, Any]] = []
    comments_per_day: Dict[str, int] = {}
    discussions_per_day: Dict[str, int] = {}
    pinned_discussions_count: int
    spoiler_discussions_count: int

    class Config:
        from_attributes = True


class DiscussionDetailResponse(DiscussionResponse):
    """Phiên bản mở rộng của DiscussionResponse với thông tin chi tiết hơn"""

    comments: Optional[List[DiscussionCommentResponse]] = []
    related_discussions: Optional[List[DiscussionResponse]] = []
    book_title: Optional[str] = None
    chapter_title: Optional[str] = None
    user_vote: Optional[int] = None  # 1 for upvote, -1 for downvote, None for no vote

    class Config:
        from_attributes = True


class DiscussionReportCreate(BaseModel):
    reason: str = Field(..., min_length=3, max_length=1000)
    report_type: str = Field(
        ..., description="Loại báo cáo: spam, offensive, inappropriate, etc."
    )


class DiscussionVoteResponse(BaseModel):
    discussion_id: int
    upvotes: int
    downvotes: int
    user_vote: int  # 1 for upvote, -1 for downvote, 0 for no vote


class DiscussionReplyCreate(BaseModel):
    comment_id: int
    content: str = Field(..., min_length=1)
    is_spoiler: Optional[bool] = False


class DiscussionReplyResponse(BaseModel):
    id: int
    comment_id: int
    user_id: int
    content: str
    is_spoiler: bool
    upvotes: int
    downvotes: int
    created_at: datetime
    updated_at: datetime
    user: Optional[UserBrief] = None

    class Config:
        from_attributes = True


class DiscussionReplyUpdate(BaseModel):
    content: Optional[str] = Field(None, min_length=1)
    is_spoiler: Optional[bool] = None


class DiscussionStatsResponse(BaseModel):
    total_discussions: int
    total_comments: int
    active_discussions: int
    trending_topics: List[str] = []
    discussions_per_day: Dict[str, int] = {}


class TrendingDiscussionResponse(DiscussionResponse):
    score: float  # Trending score
    comment_count_24h: int  # Comments in the last 24 hours
    vote_count_24h: int  # Votes in the last 24 hours


class DiscussionModerationAction(BaseModel):
    action: str = Field(
        ..., description="Action type: pin, unpin, close, open, delete, etc."
    )
    reason: Optional[str] = None
    notify_user: Optional[bool] = True


class ReportDiscussionRequest(BaseModel):
    reason: str
    category: str = Field(
        ..., description="Report category: spam, offensive, inappropriate, etc."
    )
    details: Optional[str] = None


class DiscussionQualityResponse(BaseModel):
    id: int
    quality_score: float
    engagement_score: float
    sentiment_score: Optional[float] = None
    toxicity_score: Optional[float] = None
    topics: List[str] = []


class DiscussionReactionCreate(BaseModel):
    reaction_type: str = Field(
        ..., description="Reaction type: like, love, laugh, etc."
    )


class DiscussionReactionResponse(BaseModel):
    id: int
    discussion_id: int
    user_id: int
    reaction_type: str
    created_at: datetime
    user: Optional[UserBrief] = None

    class Config:
        from_attributes = True


class DiscussionSyncRequest(BaseModel):
    last_sync_time: datetime
    limit: int = 50


class DiscussionAnalyticsResponse(BaseModel):
    views: int
    unique_viewers: int
    avg_time_spent: float  # in seconds
    conversion_rate: float  # percentage of viewers who comment
    top_referrers: Dict[str, int] = {}
    demographics: Dict[str, Any] = {}
    peak_hours: List[Dict[str, Any]] = []


class DiscussionBulkDeleteRequest(BaseModel):
    discussion_ids: List[int]
    reason: Optional[str] = None
    permanent: bool = False


class DiscussionBulkUpdateRequest(BaseModel):
    discussion_ids: List[int]
    update_data: Dict[str, Any]


class DiscussionBulkActionResponse(BaseModel):
    success_count: int
    failed_count: int
    failed_ids: List[int] = []
    error_messages: Dict[str, str] = {}


class DiscussionTimeSeriesResponse(BaseModel):
    data: List[Dict[str, Any]]
    period: str
    start_date: datetime
    end_date: datetime


class DiscussionActivitySummary(BaseModel):
    discussions_created: int
    comments_posted: int
    votes_cast: int
    reports_made: int
    received_upvotes: int
    most_upvoted_discussion: Optional[DiscussionResponse] = None
    most_commented_discussion: Optional[DiscussionResponse] = None
    activity_history: Dict[str, int] = {}


class DiscussionHighlightResponse(BaseModel):
    popular_discussions: List[DiscussionResponse] = []
    controversial_discussions: List[DiscussionResponse] = []
    trending_discussions: List[TrendingDiscussionResponse] = []
    featured_discussions: List[DiscussionResponse] = []


class DiscussionPollOption(BaseModel):
    text: str
    order: int


class DiscussionPollCreate(BaseModel):
    question: str
    options: List[DiscussionPollOption]
    allow_multiple: bool = False
    expires_at: Optional[datetime] = None


class DiscussionPollOptionResponse(DiscussionPollOption):
    id: int
    votes_count: int
    percentage: float

    class Config:
        from_attributes = True


class DiscussionPollResponse(BaseModel):
    id: int
    discussion_id: int
    question: str
    options: List[DiscussionPollOptionResponse]
    allow_multiple: bool
    expires_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    total_votes: int
    user_voted: bool = False
    user_choices: List[int] = []

    class Config:
        from_attributes = True


class DiscussionPollVoteRequest(BaseModel):
    option_ids: List[int]


class VoteRequest(BaseModel):
    """Request for voting on a discussion or comment"""

    vote_type: str = Field(..., description="Type of vote: 'upvote' or 'downvote'")


class DiscussionSearchParams(BaseModel):
    keywords: Optional[str] = None
    book_id: Optional[int] = None
    chapter_id: Optional[int] = None
    user_id: Optional[int] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    is_spoiler: Optional[bool] = None
    is_pinned: Optional[bool] = None
    sort_by: str = "created_at"
    sort_order: str = "desc"
    page: int = 1
    page_size: int = 20
