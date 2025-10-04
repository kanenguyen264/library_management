from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    authors,
    books,
    categories,
    chapters,
    favorites,
    reading_lists,
    reading_progress,
    search,
    upload,
    users,
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(books.router, prefix="/books", tags=["books"])
api_router.include_router(authors.router, prefix="/authors", tags=["authors"])
api_router.include_router(categories.router, prefix="/categories", tags=["categories"])
api_router.include_router(chapters.router, prefix="/chapters", tags=["chapters"])
api_router.include_router(
    reading_progress.router, prefix="/reading-progress", tags=["reading-progress"]
)
api_router.include_router(favorites.router, prefix="/favorites", tags=["favorites"])
api_router.include_router(
    reading_lists.router, prefix="/reading-lists", tags=["reading-lists"]
)
api_router.include_router(search.router, prefix="/search", tags=["search"])
api_router.include_router(upload.router, prefix="/upload", tags=["upload"])
