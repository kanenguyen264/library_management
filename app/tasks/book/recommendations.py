"""
Tác vụ gợi ý sách

Module này cung cấp các tác vụ liên quan đến gợi ý sách:
- Tạo gợi ý sách dựa trên thể loại
- Tạo gợi ý sách dựa trên lịch sử đọc
- Tạo gợi ý sách tương tự
"""

import datetime
import asyncio
from typing import Dict, Any, List, Optional

from app.core.config import get_settings
from app.logging.setup import get_logger
from app.tasks.worker import celery_app
from app.tasks.base_task import BaseTask
from app.core.db import async_session

# Lấy settings
settings = get_settings()

# Logger
logger = get_logger(__name__)


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="app.tasks.book.recommendations.generate_recommendations",
    queue="recommendations",
    max_retries=3,
)
def generate_recommendations(self, user_id: int) -> Dict[str, Any]:
    """
    Tạo gợi ý sách cho người dùng.

    Args:
        user_id: ID của người dùng

    Returns:
        Dict chứa kết quả gợi ý
    """
    try:
        logger.info(f"Generating recommendations for user_id={user_id}")

        # Khởi tạo kết quả
        result = {
            "user_id": user_id,
            "generated_at": datetime.datetime.now().isoformat(),
            "recommendations": [],
            "status": "success",
        }

        # 1. Lấy lịch sử đọc sách
        reading_history = get_user_reading_history(user_id)

        # 2. Lấy thể loại yêu thích
        favorite_genres = get_user_favorite_genres(user_id, reading_history)

        # 3. Gợi ý sách dựa trên thể loại
        genre_recommendations = recommend_by_genre(user_id, favorite_genres)
        result["recommendations"].extend(genre_recommendations)

        # 4. Gợi ý sách tương tự đã đọc
        similar_recommendations = recommend_similar_books(user_id, reading_history)
        result["recommendations"].extend(similar_recommendations)

        # 5. Gợi ý sách phổ biến
        popular_recommendations = recommend_popular_books(user_id)
        result["recommendations"].extend(popular_recommendations)

        # Loại bỏ các sách đã đọc và trùng lặp
        result["recommendations"] = filter_recommendations(
            user_id, result["recommendations"]
        )

        # Lưu gợi ý vào database
        save_recommendations_to_db(user_id, result["recommendations"])

        logger.info(
            f"Generated {len(result['recommendations'])} recommendations for user_id={user_id}"
        )
        return result

    except Exception as e:
        logger.error(
            f"Error generating recommendations for user_id={user_id}: {str(e)}"
        )
        self.retry(exc=e, countdown=60)


def get_user_reading_history(user_id: int) -> List[Dict[str, Any]]:
    """
    Lấy lịch sử đọc sách của người dùng.

    Args:
        user_id: ID của người dùng

    Returns:
        Danh sách các sách đã đọc
    """
    try:

        async def get_history():
            from app.user_site.models.reading_history import ReadingHistory
            from app.user_site.models.book import Book
            from sqlalchemy import select, desc
            from sqlalchemy.orm import joinedload

            async with async_session() as session:
                # Lấy lịch sử đọc sách từ database
                stmt = (
                    select(ReadingHistory, Book)
                    .join(Book, ReadingHistory.book_id == Book.id)
                    .where(ReadingHistory.user_id == user_id)
                    .order_by(desc(ReadingHistory.last_read_at))
                    .limit(50)
                )

                result = await session.execute(stmt)
                history = []

                for reading_history, book in result:
                    history.append(
                        {
                            "book_id": book.id,
                            "title": book.title,
                            "author": book.author_name,
                            "genres": book.genres if hasattr(book, "genres") else [],
                            "last_read_at": reading_history.last_read_at,
                            "read_percentage": reading_history.read_percentage,
                            "rating": reading_history.rating,
                        }
                    )

                return history

        # Chạy async task
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(get_history())

    except Exception as e:
        logger.error(f"Error getting reading history: {str(e)}")
        return []


def get_user_favorite_genres(
    user_id: int, reading_history: List[Dict[str, Any]]
) -> List[str]:
    """
    Xác định thể loại yêu thích của người dùng dựa trên lịch sử đọc.

    Args:
        user_id: ID của người dùng
        reading_history: Lịch sử đọc sách

    Returns:
        Danh sách thể loại yêu thích
    """
    try:
        # Đếm số lượng sách đọc theo thể loại
        genre_counts = {}

        for item in reading_history:
            genres = item.get("genres", [])
            for genre in genres:
                if genre in genre_counts:
                    # Tăng điểm cho thể loại nếu người dùng đọc nhiều
                    genre_counts[genre] += 1
                    # Tăng thêm điểm nếu người dùng đánh giá cao
                    if item.get("rating", 0) >= 4:
                        genre_counts[genre] += 1
                    # Tăng thêm điểm nếu đọc gần đây
                    if (
                        datetime.datetime.now()
                        - item.get("last_read_at", datetime.datetime.now())
                    ).days < 30:
                        genre_counts[genre] += 0.5
                else:
                    genre_counts[genre] = 1

        # Sắp xếp thể loại theo độ phổ biến
        sorted_genres = sorted(genre_counts.items(), key=lambda x: x[1], reverse=True)

        # Lấy tối đa 5 thể loại yêu thích
        favorite_genres = [genre for genre, count in sorted_genres[:5]]

        return favorite_genres

    except Exception as e:
        logger.error(f"Error getting favorite genres: {str(e)}")
        return []


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="app.tasks.book.recommendations.recommend_by_genre",
    queue="recommendations",
)
def recommend_by_genre(self, user_id: int, genres: List[str]) -> List[Dict[str, Any]]:
    """
    Tạo gợi ý sách dựa trên thể loại yêu thích.

    Args:
        user_id: ID của người dùng
        genres: Danh sách thể loại yêu thích

    Returns:
        Danh sách sách được gợi ý
    """
    try:
        if not genres:
            return []

        async def get_books_by_genre():
            from app.user_site.models.book import Book
            from app.user_site.models.reading_history import ReadingHistory
            from sqlalchemy import select, or_, func

            async with async_session() as session:
                # Lấy sách đã đọc để loại trừ
                stmt_read = select(ReadingHistory.book_id).where(
                    ReadingHistory.user_id == user_id
                )
                result_read = await session.execute(stmt_read)
                read_book_ids = [row[0] for row in result_read]

                # Tạo điều kiện OR cho các thể loại
                genre_conditions = []
                for genre in genres:
                    genre_conditions.append(Book.genres.contains([genre]))

                # Lấy sách theo thể loại, sắp xếp theo đánh giá
                stmt = (
                    select(Book)
                    .where(or_(*genre_conditions))
                    .where(~Book.id.in_(read_book_ids))
                    .order_by(Book.average_rating.desc())
                    .limit(20)
                )

                result = await session.execute(stmt)
                books = []

                for book in result.scalars().unique():
                    books.append(
                        {
                            "book_id": book.id,
                            "title": book.title,
                            "author": book.author_name,
                            "average_rating": book.average_rating,
                            "cover_image": book.cover_image,
                            "recommendation_type": "genre",
                            "recommendation_reason": f"Dựa trên thể loại yêu thích của bạn: {', '.join(set(genres).intersection(set(book.genres)))}",
                        }
                    )

                return books

        # Chạy async task
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(get_books_by_genre())

    except Exception as e:
        logger.error(f"Error recommending by genre: {str(e)}")
        return []


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="app.tasks.book.recommendations.recommend_similar_books",
    queue="recommendations",
)
def recommend_similar_books(
    self, user_id: int, reading_history: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Tạo gợi ý sách tương tự với sách đã đọc.

    Args:
        user_id: ID của người dùng
        reading_history: Lịch sử đọc sách

    Returns:
        Danh sách sách được gợi ý
    """
    try:
        if not reading_history:
            return []

        # Lấy các sách đã đọc gần đây và có đánh giá cao
        recent_books = []
        for item in reading_history[:10]:  # Chỉ xem xét 10 sách đọc gần đây
            if item.get("rating", 0) >= 4 or item.get("read_percentage", 0) > 70:
                recent_books.append(item["book_id"])

        if not recent_books:
            recent_books = [item["book_id"] for item in reading_history[:3]]

        async def get_similar_books():
            from app.user_site.models.book import Book
            from app.user_site.models.reading_history import ReadingHistory
            from sqlalchemy import select, or_, func

            async with async_session() as session:
                # Lấy sách đã đọc để loại trừ
                stmt_read = select(ReadingHistory.book_id).where(
                    ReadingHistory.user_id == user_id
                )
                result_read = await session.execute(stmt_read)
                read_book_ids = [row[0] for row in result_read]

                recommendations = []

                # Với mỗi sách đã đọc, tìm sách tương tự
                for book_id in recent_books[
                    :3
                ]:  # Giới hạn 3 sách để tránh quá nhiều truy vấn
                    # Lấy thông tin sách
                    stmt_book = select(Book).where(Book.id == book_id)
                    result_book = await session.execute(stmt_book)
                    book = result_book.scalars().first()

                    if not book:
                        continue

                    # Tìm sách cùng tác giả
                    stmt_author = (
                        select(Book)
                        .where(Book.author_name == book.author_name)
                        .where(Book.id != book_id)
                        .where(~Book.id.in_(read_book_ids))
                        .limit(3)
                    )

                    result_author = await session.execute(stmt_author)
                    for similar_book in result_author.scalars():
                        recommendations.append(
                            {
                                "book_id": similar_book.id,
                                "title": similar_book.title,
                                "author": similar_book.author_name,
                                "average_rating": similar_book.average_rating,
                                "cover_image": similar_book.cover_image,
                                "recommendation_type": "author",
                                "recommendation_reason": f"Cùng tác giả với '{book.title}' mà bạn đã đọc",
                            }
                        )

                    # Tìm sách cùng thể loại và có đánh giá cao
                    if hasattr(book, "genres") and book.genres:
                        genre_conditions = []
                        for genre in book.genres:
                            genre_conditions.append(Book.genres.contains([genre]))

                        stmt_genre = (
                            select(Book)
                            .where(or_(*genre_conditions))
                            .where(Book.id != book_id)
                            .where(~Book.id.in_(read_book_ids))
                            .order_by(Book.average_rating.desc())
                            .limit(3)
                        )

                        result_genre = await session.execute(stmt_genre)
                        for similar_book in result_genre.scalars():
                            recommendations.append(
                                {
                                    "book_id": similar_book.id,
                                    "title": similar_book.title,
                                    "author": similar_book.author_name,
                                    "average_rating": similar_book.average_rating,
                                    "cover_image": similar_book.cover_image,
                                    "recommendation_type": "similar",
                                    "recommendation_reason": f"Tương tự với '{book.title}' mà bạn đã đọc",
                                }
                            )

                return recommendations

        # Chạy async task
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(get_similar_books())

    except Exception as e:
        logger.error(f"Error recommending similar books: {str(e)}")
        return []


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="app.tasks.book.recommendations.recommend_popular_books",
    queue="recommendations",
)
def recommend_popular_books(self, user_id: int) -> List[Dict[str, Any]]:
    """
    Tạo gợi ý sách phổ biến.

    Args:
        user_id: ID của người dùng

    Returns:
        Danh sách sách được gợi ý
    """
    try:

        async def get_popular_books():
            from app.user_site.models.book import Book
            from app.user_site.models.reading_history import ReadingHistory
            from sqlalchemy import select, func

            async with async_session() as session:
                # Lấy sách đã đọc để loại trừ
                stmt_read = select(ReadingHistory.book_id).where(
                    ReadingHistory.user_id == user_id
                )
                result_read = await session.execute(stmt_read)
                read_book_ids = [row[0] for row in result_read]

                # Lấy sách phổ biến dựa trên số lượt đọc và đánh giá
                stmt = (
                    select(Book, func.count(ReadingHistory.id).label("read_count"))
                    .join(ReadingHistory, Book.id == ReadingHistory.book_id)
                    .where(~Book.id.in_(read_book_ids))
                    .group_by(Book.id)
                    .order_by(
                        func.count(ReadingHistory.id).desc(), Book.average_rating.desc()
                    )
                    .limit(10)
                )

                result = await session.execute(stmt)
                books = []

                for book, read_count in result:
                    books.append(
                        {
                            "book_id": book.id,
                            "title": book.title,
                            "author": book.author_name,
                            "average_rating": book.average_rating,
                            "cover_image": book.cover_image,
                            "recommendation_type": "popular",
                            "recommendation_reason": f"Sách phổ biến với {read_count} lượt đọc",
                        }
                    )

                return books

        # Chạy async task
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(get_popular_books())

    except Exception as e:
        logger.error(f"Error recommending popular books: {str(e)}")
        return []


def filter_recommendations(
    user_id: int, recommendations: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Lọc các gợi ý sách để loại bỏ trùng lặp và sắp xếp lại.

    Args:
        user_id: ID của người dùng
        recommendations: Danh sách sách được gợi ý ban đầu

    Returns:
        Danh sách sách được gợi ý sau khi lọc
    """
    try:
        # Loại bỏ sách trùng lặp dựa trên book_id
        unique_recommendations = {}
        for rec in recommendations:
            book_id = rec["book_id"]
            if book_id not in unique_recommendations:
                unique_recommendations[book_id] = rec

        # Chuyển về danh sách
        filtered_recommendations = list(unique_recommendations.values())

        # Sắp xếp: ưu tiên similar > genre > popular
        def get_priority(rec_type):
            if rec_type == "similar":
                return 1
            elif rec_type == "genre":
                return 2
            else:
                return 3

        filtered_recommendations.sort(
            key=lambda x: (
                get_priority(x["recommendation_type"]),
                -x.get("average_rating", 0),
            )
        )

        # Giới hạn số lượng
        return filtered_recommendations[:20]

    except Exception as e:
        logger.error(f"Error filtering recommendations: {str(e)}")
        return recommendations


def save_recommendations_to_db(
    user_id: int, recommendations: List[Dict[str, Any]]
) -> None:
    """
    Lưu gợi ý sách vào database.

    Args:
        user_id: ID của người dùng
        recommendations: Danh sách sách được gợi ý
    """
    try:

        async def save_to_db():
            from app.user_site.models.recommendation import BookRecommendation
            from sqlalchemy import delete

            async with async_session() as session:
                # Xóa các gợi ý cũ
                stmt_delete = delete(BookRecommendation).where(
                    BookRecommendation.user_id == user_id
                )
                await session.execute(stmt_delete)

                # Thêm các gợi ý mới
                for i, rec in enumerate(recommendations):
                    new_rec = BookRecommendation(
                        user_id=user_id,
                        book_id=rec["book_id"],
                        recommendation_type=rec["recommendation_type"],
                        recommendation_reason=rec["recommendation_reason"],
                        position=i + 1,
                        created_at=datetime.datetime.now(),
                    )
                    session.add(new_rec)

                await session.commit()

        # Chạy async task
        loop = asyncio.get_event_loop()
        loop.run_until_complete(save_to_db())

    except Exception as e:
        logger.error(f"Error saving recommendations to database: {str(e)}")
