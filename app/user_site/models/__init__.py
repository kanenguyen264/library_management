# Import các model
from app.core.db import Base

# Public schema models
from app.user_site.models.book import Book
from app.user_site.models.book_series import BookSeries, BookSeriesItem
from app.user_site.models.author import Author, BookAuthor
from app.user_site.models.category import Category, BookCategory
from app.user_site.models.tag import Tag, BookTag
from app.user_site.models.chapter import Chapter, ChapterMedia
from app.user_site.models.publisher import Publisher

# User data schema models
from app.user_site.models.user import User
from app.user_site.models.social_profile import SocialProfile
from app.user_site.models.preference import UserPreference
from app.user_site.models.reading_history import ReadingHistory
from app.user_site.models.reading_session import ReadingSession
from app.user_site.models.bookmark import Bookmark
from app.user_site.models.bookshelf import Bookshelf, BookshelfItem
from app.user_site.models.review import Review, ReviewLike, ReviewReport
from app.user_site.models.annotation import Annotation
from app.user_site.models.quote import Quote, QuoteLike
from app.user_site.models.achievement import UserAchievement
from app.user_site.models.badge import UserBadge
from app.user_site.models.reading_goal import ReadingGoal, ReadingGoalProgress
from app.user_site.models.book_list import UserBookList, UserBookListItem
from app.user_site.models.following import UserFollowing
from app.user_site.models.notification import UserNotification
from app.user_site.models.discussion import Discussion, DiscussionComment
from app.user_site.models.subscription import SubscriptionPlan, UserSubscription
from app.user_site.models.payment import Payment, PaymentMethod
from app.user_site.models.recommendation import Recommendation

__all__ = [
    "Book",
    "BookSeries",
    "BookSeriesItem",
    "Author",
    "BookAuthor",
    "Category",
    "BookCategory",
    "Tag",
    "BookTag",
    "Chapter",
    "ChapterMedia",
    "Publisher",
    "User",
    "SocialProfile",
    "UserPreference",
    "ReadingHistory",
    "ReadingSession",
    "Bookmark",
    "Bookshelf",
    "BookshelfItem",
    "Review",
    "ReviewLike",
    "ReviewReport",
    "Annotation",
    "Quote",
    "QuoteLike",
    "UserAchievement",
    "UserBadge",
    "ReadingGoal",
    "ReadingGoalProgress",
    "UserBookList",
    "UserBookListItem",
    "UserFollowing",
    "UserNotification",
    "Discussion",
    "DiscussionComment",
    "SubscriptionPlan",
    "UserSubscription",
    "Payment",
    "PaymentMethod",
    "Recommendation",
]
