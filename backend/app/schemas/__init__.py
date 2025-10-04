# Import all schemas
from app.schemas.author import *
from app.schemas.book import *
from app.schemas.category import *
from app.schemas.chapter import *
from app.schemas.favorite import *
from app.schemas.reading_list import *
from app.schemas.reading_progress import *
from app.schemas.response import *
from app.schemas.token import *
from app.schemas.user import *


def rebuild_schemas():
    """Rebuild all schemas to resolve forward references."""
    import app.schemas.author as author_module
    import app.schemas.book as book_module
    import app.schemas.category as category_module
    import app.schemas.chapter as chapter_module
    import app.schemas.favorite as favorite_module
    import app.schemas.reading_list as reading_list_module
    import app.schemas.reading_progress as reading_progress_module

    # Rebuild schemas that have forward references
    try:
        if hasattr(book_module.BookWithDetails, "model_rebuild"):
            book_module.BookWithDetails.model_rebuild()
        if hasattr(chapter_module.ChapterWithDetails, "model_rebuild"):
            chapter_module.ChapterWithDetails.model_rebuild()
        if hasattr(favorite_module.FavoriteWithDetails, "model_rebuild"):
            favorite_module.FavoriteWithDetails.model_rebuild()
        if hasattr(author_module, "AuthorWithBooks") and hasattr(
            author_module.AuthorWithBooks, "model_rebuild"
        ):
            author_module.AuthorWithBooks.model_rebuild()
        if hasattr(category_module, "CategoryWithBooks") and hasattr(
            category_module.CategoryWithBooks, "model_rebuild"
        ):
            category_module.CategoryWithBooks.model_rebuild()
        if hasattr(reading_list_module, "ReadingListWithItems") and hasattr(
            reading_list_module.ReadingListWithItems, "model_rebuild"
        ):
            reading_list_module.ReadingListWithItems.model_rebuild()
        if hasattr(reading_list_module, "ReadingListItemWithDetails") and hasattr(
            reading_list_module.ReadingListItemWithDetails, "model_rebuild"
        ):
            reading_list_module.ReadingListItemWithDetails.model_rebuild()
        if hasattr(reading_progress_module, "ReadingProgressWithDetails") and hasattr(
            reading_progress_module.ReadingProgressWithDetails, "model_rebuild"
        ):
            reading_progress_module.ReadingProgressWithDetails.model_rebuild()
    except Exception:
        # Silently handle rebuild errors - they're not critical for basic functionality
        pass


# Rebuild schemas on import
rebuild_schemas()
