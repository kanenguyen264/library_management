"""
Các tác vụ liên quan đến sách

Module này cung cấp các tác vụ xử lý sách, bao gồm:
- Phân tích dữ liệu sách
- Xử lý file sách
- Tạo gợi ý sách
"""

from app.tasks.book.analytics import (
    analyze_reading_trends,
    generate_reading_report,
    track_user_reading_patterns,
)

from app.tasks.book.processing import (
    process_book_upload,
    generate_book_preview,
    extract_book_metadata,
    generate_book_thumbnail,
)

from app.tasks.book.recommendations import (
    generate_recommendations,
    generate_trending_books,
    update_user_recommendations,
)

__all__ = [
    # Analytics
    "analyze_reading_trends",
    "generate_reading_report",
    "track_user_reading_patterns",
    # Processing
    "process_book_upload",
    "generate_book_preview",
    "extract_book_metadata",
    "generate_book_thumbnail",
    # Recommendations
    "generate_recommendations",
    "generate_trending_books",
    "update_user_recommendations",
]
