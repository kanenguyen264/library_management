from fastapi import APIRouter

# Import throttle_requests từ module mới
from app.user_site.api.throttling import throttle_requests

from app.user_site.api.v1 import (
    achievements,
    annotations,
    auth,
    authors,
    badges,
    books,
    book_lists,
    book_series,
    bookmarks,
    bookshelves,
    categories,
    chapters,
    discussions,
    following,
    notifications,
    payments,
    preferences,
    publishers,
    quotes,
    reading_goals,
    reading_history,
    reading_sessions,
    recommendations,
    reviews,
    search,
    social_profiles,
    subscriptions,
    tags,
    users,
)

# Export throttle_requests để các module con có thể sử dụng
__all__ = ["api_router", "throttle_requests"]

api_router = APIRouter()

# Đăng ký các routers
api_router.include_router(
    achievements.router, prefix="/achievements", tags=["achievements"]
)
api_router.include_router(
    annotations.router, prefix="/annotations", tags=["annotations"]
)
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(authors.router, prefix="/authors", tags=["authors"])
api_router.include_router(badges.router, prefix="/badges", tags=["badges"])
api_router.include_router(books.router, prefix="/books", tags=["books"])
api_router.include_router(book_lists.router, prefix="/book-lists", tags=["book-lists"])
api_router.include_router(
    book_series.router, prefix="/book-series", tags=["book-series"]
)
api_router.include_router(bookmarks.router, prefix="/bookmarks", tags=["bookmarks"])
api_router.include_router(
    bookshelves.router, prefix="/bookshelves", tags=["bookshelves"]
)
api_router.include_router(categories.router, prefix="/categories", tags=["categories"])
api_router.include_router(chapters.router, prefix="/chapters", tags=["chapters"])
api_router.include_router(
    discussions.router, prefix="/discussions", tags=["discussions"]
)
api_router.include_router(following.router, prefix="/following", tags=["following"])
api_router.include_router(
    notifications.router, prefix="/notifications", tags=["notifications"]
)
api_router.include_router(payments.router, prefix="/payments", tags=["payments"])
api_router.include_router(
    preferences.router, prefix="/preferences", tags=["preferences"]
)
api_router.include_router(publishers.router, prefix="/publishers", tags=["publishers"])
api_router.include_router(quotes.router, prefix="/quotes", tags=["quotes"])
api_router.include_router(
    reading_goals.router, prefix="/reading-goals", tags=["reading-goals"]
)
api_router.include_router(
    reading_history.router, prefix="/reading-history", tags=["reading-history"]
)
api_router.include_router(
    reading_sessions.router, prefix="/reading-sessions", tags=["reading-sessions"]
)
api_router.include_router(
    recommendations.router, prefix="/recommendations", tags=["recommendations"]
)
api_router.include_router(reviews.router, prefix="/reviews", tags=["reviews"])
api_router.include_router(search.router, prefix="/search", tags=["search"])
api_router.include_router(
    social_profiles.router, prefix="/social-profiles", tags=["social-profiles"]
)
api_router.include_router(
    subscriptions.router, prefix="/subscriptions", tags=["subscriptions"]
)
api_router.include_router(tags.router, prefix="/tags", tags=["tags"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
