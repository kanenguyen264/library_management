from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from app.user_site.repositories.book_repo import BookRepository
from app.user_site.repositories.reading_history_repo import ReadingHistoryRepository
from app.user_site.repositories.category_repo import CategoryRepository
from app.user_site.repositories.author_repo import AuthorRepository
from app.user_site.repositories.user_repo import UserRepository
from app.user_site.repositories.preference_repo import PreferenceRepository
from app.user_site.repositories.tag_repo import TagRepository
from app.core.exceptions import (
    NotFoundException,
    BadRequestException,
    ValidationException,
)
from app.cache.decorators import cached
from app.user_site.repositories.recommendation_repo import RecommendationRepository
from app.user_site.repositories.review_repo import ReviewRepository
from app.monitoring.metrics.business_metrics import track_recommendation


class RecommendationService:
    def __init__(self, db: AsyncSession):
        """
        Khởi tạo dịch vụ gợi ý đọc sách

        Args:
            db: Phiên làm việc cơ sở dữ liệu không đồng bộ
        """
        self.db = db
        self.book_repo = BookRepository(db)
        self.reading_history_repo = ReadingHistoryRepository(db)
        self.category_repo = CategoryRepository(db)
        self.author_repo = AuthorRepository(db)
        self.user_repo = UserRepository(db)
        self.preference_repo = PreferenceRepository(db)
        self.tag_repo = TagRepository(db)
        self.recommendation_repo = RecommendationRepository(db)
        self.review_repo = ReviewRepository(db)

    @cached(
        ttl=3600,
        namespace="recommendations",
        key_prefix="personalized",
        tags=["recommendations"],
    )
    async def get_personalized_recommendations(
        self, user_id: int, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Lấy gợi ý đọc sách cá nhân hóa cho người dùng dựa trên lịch sử đọc, đánh giá và sở thích

        Args:
            user_id: ID người dùng
            limit: Số lượng gợi ý tối đa

        Returns:
            Danh sách các gợi ý sách với thông tin chi tiết
        """
        # Kiểm tra người dùng tồn tại
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng có ID {user_id}")

        # Lấy gợi ý chưa bị bỏ qua từ kho dữ liệu
        recommendations = await self.recommendation_repo.list_by_user(
            user_id=user_id,
            limit=limit * 2,  # Lấy nhiều hơn để lọc sau
            is_dismissed=False,
            sort_by="confidence_score",
            sort_desc=True,
            with_relations=["book"],
        )

        # Nếu không đủ gợi ý, tạo thêm
        if len(recommendations) < limit:
            await self._generate_recommendations(user_id)
            # Lấy lại sau khi tạo
            recommendations = await self.recommendation_repo.list_by_user(
                user_id=user_id,
                limit=limit * 2,
                is_dismissed=False,
                sort_by="confidence_score",
                sort_desc=True,
                with_relations=["book"],
            )

        # Chuyển đổi sang định dạng phản hồi
        result = []
        for rec in recommendations[:limit]:
            if not rec.book:  # Bỏ qua nếu không có thông tin sách
                continue

            # Bổ sung thông tin book nếu cần
            book_data = {
                "id": rec.book.id,
                "title": rec.book.title,
                "cover_image_url": rec.book.cover_image_url,
                "cover_thumbnail_url": rec.book.cover_thumbnail_url,
                "avg_rating": rec.book.avg_rating,
                "recommendation_type": rec.recommendation_type,
                "confidence_score": rec.confidence_score,
                "recommendation_id": rec.id,
            }

            # Thêm thông tin tác giả nếu có
            if hasattr(rec.book, "authors") and rec.book.authors:
                book_data["authors"] = [
                    {"id": author.id, "name": author.name}
                    for author in rec.book.authors
                ]

            result.append(book_data)

        # Theo dõi chỉ số
        track_recommendation("personalized", len(result), "registered")

        return result

    async def _generate_recommendations(self, user_id: int) -> None:
        """
        Tạo các gợi ý mới cho người dùng dựa trên thuật toán gợi ý

        Args:
            user_id: ID người dùng
        """
        # 1. Lấy sách đã đọc gần đây
        reading_history = await self.reading_history_repo.list_by_user(
            user_id=user_id, limit=10, sort_by="updated_at", sort_desc=True
        )

        recent_book_ids = [
            history.book_id for history in reading_history if history.book_id
        ]

        # 2. Lấy các sách đã đánh giá cao
        liked_reviews = await self.review_repo.list_reviews(
            user_id=user_id, limit=10, sort_by="rating", sort_desc=True
        )

        liked_book_ids = [
            review.book_id for review in liked_reviews if review.rating >= 4
        ]

        # 3. Kết hợp và tìm sách tương tự
        seed_book_ids = list(set(recent_book_ids + liked_book_ids))

        if not seed_book_ids:
            # Không có dữ liệu để gợi ý, lấy sách phổ biến
            popular_books = await self.book_repo.find_popular_books(limit=20)

            # Tạo gợi ý từ sách phổ biến
            recommendations_to_create = []
            for book in popular_books:
                recommendations_to_create.append(
                    {
                        "user_id": user_id,
                        "book_id": book.id,
                        "recommendation_type": "popular",
                        "confidence_score": 0.5,  # Độ tin cậy trung bình
                        "is_dismissed": False,
                    }
                )

            if recommendations_to_create:
                await self.recommendation_repo.bulk_create(recommendations_to_create)
            return

        # 4. Tìm sách liên quan từ seed books
        for book_id in seed_book_ids[:5]:  # Giới hạn số lượng seed books để xử lý
            similar_books = await self.book_repo.find_similar_books(
                book_id=book_id, limit=5
            )

            # Tạo gợi ý từ sách tương tự
            recommendations_to_create = []
            for book, similarity in similar_books:
                # Kiểm tra xem đã đọc hoặc đã gợi ý chưa
                if book.id in recent_book_ids:
                    continue

                # Kiểm tra đã tồn tại gợi ý chưa
                existing = await self.recommendation_repo.get_by_user_book(
                    user_id=user_id, book_id=book.id
                )

                if not existing:
                    recommendations_to_create.append(
                        {
                            "user_id": user_id,
                            "book_id": book.id,
                            "recommendation_type": "similar_to_read",
                            "confidence_score": similarity,  # Độ tương tự là độ tin cậy
                            "is_dismissed": False,
                        }
                    )

            if recommendations_to_create:
                await self.recommendation_repo.bulk_create(recommendations_to_create)

    @cached(
        ttl=3600,
        namespace="recommendations",
        key_prefix="similar_books",
        tags=["recommendations"],
    )
    async def get_similar_books(
        self, book_id: int, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Lấy danh sách sách tương tự với một cuốn sách

        Args:
            book_id: ID của sách
            limit: Số lượng sách tương tự tối đa

        Returns:
            Danh sách các sách tương tự
        """
        # Kiểm tra sách tồn tại
        book = await self.book_repo.get_by_id(book_id)
        if not book:
            raise NotFoundException(f"Không tìm thấy sách có ID {book_id}")

        # Tìm sách tương tự
        similar_books = await self.book_repo.find_similar_books(
            book_id=book_id, limit=limit
        )

        # Chuyển đổi sang định dạng phản hồi
        result = []
        for book, similarity in similar_books:
            book_data = {
                "id": book.id,
                "title": book.title,
                "cover_image_url": book.cover_image_url,
                "cover_thumbnail_url": book.cover_thumbnail_url,
                "avg_rating": book.avg_rating,
                "similarity_score": similarity,
            }

            # Thêm thông tin tác giả nếu có
            if hasattr(book, "authors") and book.authors:
                book_data["authors"] = [
                    {"id": author.id, "name": author.name} for author in book.authors
                ]

            result.append(book_data)

        return result

    @cached(
        ttl=7200,
        namespace="recommendations",
        key_prefix="category",
        tags=["recommendations"],
    )
    async def get_category_recommendations(
        self, category_id: int, user_id: Optional[int] = None, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Lấy gợi ý sách theo thể loại, có thể cá nhân hóa nếu cung cấp user_id

        Args:
            category_id: ID thể loại
            user_id: ID người dùng (tùy chọn)
            limit: Số lượng gợi ý tối đa

        Returns:
            Danh sách các sách được gợi ý cho thể loại
        """
        # Kiểm tra thể loại tồn tại
        category = await self.book_repo.get_category_by_id(category_id)
        if not category:
            raise NotFoundException(f"Không tìm thấy thể loại có ID {category_id}")

        if user_id:
            # Nếu có user_id, lấy sách phổ biến trong thể loại mà người dùng chưa đọc
            # 1. Lấy lịch sử đọc của người dùng
            reading_history = await self.reading_history_repo.list_by_user(
                user_id=user_id, limit=50
            )
            read_book_ids = set(
                history.book_id for history in reading_history if history.book_id
            )

            # 2. Lấy sách phổ biến trong thể loại
            category_books = await self.book_repo.find_books_by_category(
                category_id=category_id,
                sort_by="popularity_score",
                sort_desc=True,
                limit=limit * 2,  # Lấy nhiều hơn để lọc
            )

            # 3. Lọc sách đã đọc
            books = [book for book in category_books if book.id not in read_book_ids][
                :limit
            ]
        else:
            # Lấy sách phổ biến trong thể loại
            books = await self.book_repo.find_books_by_category(
                category_id=category_id,
                sort_by="popularity_score",
                sort_desc=True,
                limit=limit,
            )

        # Chuyển đổi sang định dạng phản hồi
        result = []
        for book in books:
            book_data = {
                "id": book.id,
                "title": book.title,
                "cover_image_url": book.cover_image_url,
                "cover_thumbnail_url": book.cover_thumbnail_url,
                "avg_rating": book.avg_rating,
                "popularity_score": book.popularity_score,
            }

            # Thêm thông tin tác giả nếu có
            if hasattr(book, "authors") and book.authors:
                book_data["authors"] = [
                    {"id": author.id, "name": author.name} for author in book.authors
                ]

            result.append(book_data)

        # Theo dõi chỉ số
        user_type = "registered" if user_id else "anonymous"
        track_recommendation("category", len(result), user_type)

        return result

    @cached(
        ttl=7200,
        namespace="recommendations",
        key_prefix="author",
        tags=["recommendations"],
    )
    async def get_author_recommendations(
        self, author_id: int, user_id: Optional[int] = None, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Lấy gợi ý sách của một tác giả, có thể cá nhân hóa nếu cung cấp user_id

        Args:
            author_id: ID tác giả
            user_id: ID người dùng (tùy chọn)
            limit: Số lượng gợi ý tối đa

        Returns:
            Danh sách các sách được gợi ý của tác giả
        """
        # Kiểm tra tác giả tồn tại
        author = await self.book_repo.get_author_by_id(author_id)
        if not author:
            raise NotFoundException(f"Không tìm thấy tác giả có ID {author_id}")

        if user_id:
            # Nếu có user_id, lấy sách của tác giả mà người dùng chưa đọc
            # 1. Lấy lịch sử đọc của người dùng
            reading_history = await self.reading_history_repo.list_by_user(
                user_id=user_id, limit=50
            )
            read_book_ids = set(
                history.book_id for history in reading_history if history.book_id
            )

            # 2. Lấy sách của tác giả
            author_books = await self.book_repo.find_books_by_author(
                author_id=author_id,
                sort_by="publication_date",
                sort_desc=True,
                limit=limit * 2,  # Lấy nhiều hơn để lọc
            )

            # 3. Lọc sách đã đọc
            books = [book for book in author_books if book.id not in read_book_ids][
                :limit
            ]
        else:
            # Lấy sách của tác giả
            books = await self.book_repo.find_books_by_author(
                author_id=author_id,
                sort_by="publication_date",
                sort_desc=True,
                limit=limit,
            )

        # Chuyển đổi sang định dạng phản hồi
        result = []
        for book in books:
            book_data = {
                "id": book.id,
                "title": book.title,
                "cover_image_url": book.cover_image_url,
                "cover_thumbnail_url": book.cover_thumbnail_url,
                "avg_rating": book.avg_rating,
                "publication_date": book.publication_date,
            }

            # Thêm thông tin thể loại nếu có
            if hasattr(book, "categories") and book.categories:
                book_data["categories"] = [
                    {"id": category.id, "name": category.name}
                    for category in book.categories
                ]

            result.append(book_data)

        return result

    @cached(
        ttl=3600,
        namespace="recommendations",
        key_prefix="trending",
        tags=["recommendations"],
    )
    async def get_trending_books(
        self,
        user_id: Optional[int] = None,
        category_id: Optional[int] = None,
        time_period: str = "week",
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Lấy danh sách sách đang thịnh hành

        Args:
            user_id: ID người dùng (tùy chọn)
            category_id: ID thể loại (tùy chọn)
            time_period: Khoảng thời gian ("day", "week", "month")
            limit: Số lượng sách tối đa

        Returns:
            Danh sách các sách đang thịnh hành
        """
        # Xác định khoảng thời gian
        now = datetime.now(timezone.utc)
        if time_period == "day":
            start_date = now - timedelta(days=1)
        elif time_period == "week":
            start_date = now - timedelta(days=7)
        elif time_period == "month":
            start_date = now - timedelta(days=30)
        else:
            raise ValidationException(f"Khoảng thời gian không hợp lệ: {time_period}")

        # Lấy sách thịnh hành
        trending_books = await self.book_repo.find_trending_books(
            start_date=start_date, category_id=category_id, limit=limit
        )

        # Nếu có user_id, lọc sách đã đọc
        if user_id:
            # Lấy lịch sử đọc của người dùng
            reading_history = await self.reading_history_repo.list_by_user(
                user_id=user_id, limit=50
            )
            read_book_ids = set(
                history.book_id for history in reading_history if history.book_id
            )

            # Lọc sách đã đọc
            trending_books = [
                book for book in trending_books if book.id not in read_book_ids
            ]

        # Chuyển đổi sang định dạng phản hồi
        result = []
        for book in trending_books[:limit]:
            book_data = {
                "id": book.id,
                "title": book.title,
                "cover_image_url": book.cover_image_url,
                "cover_thumbnail_url": book.cover_thumbnail_url,
                "avg_rating": book.avg_rating,
                "trending_score": getattr(book, "trending_score", None),
                "view_count": getattr(book, "view_count", None),
            }

            # Thêm thông tin tác giả nếu có
            if hasattr(book, "authors") and book.authors:
                book_data["authors"] = [
                    {"id": author.id, "name": author.name} for author in book.authors
                ]

            # Thêm thông tin thể loại nếu có
            if hasattr(book, "categories") and book.categories:
                book_data["categories"] = [
                    {"id": category.id, "name": category.name}
                    for category in book.categories
                ]

            result.append(book_data)

        # Theo dõi chỉ số
        user_type = "registered" if user_id else "anonymous"
        track_recommendation("trending", len(result), user_type)

        return result

    @cached(
        ttl=7200,
        namespace="recommendations",
        key_prefix="new_releases",
        tags=["recommendations"],
    )
    async def get_new_releases(
        self,
        user_id: Optional[int] = None,
        category_id: Optional[int] = None,
        days: int = 30,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Lấy danh sách sách mới phát hành

        Args:
            user_id: ID người dùng (tùy chọn)
            category_id: ID thể loại (tùy chọn)
            days: Số ngày xem là mới
            limit: Số lượng sách tối đa

        Returns:
            Danh sách các sách mới phát hành
        """
        # Xác định khoảng thời gian
        start_date = datetime.now(timezone.utc) - timedelta(days=days)

        # Lấy sách mới phát hành
        new_books = await self.book_repo.find_new_releases(
            since_date=start_date,
            category_id=category_id,
            limit=limit * 2,  # Lấy nhiều hơn để lọc
        )

        # Nếu có user_id và đủ sách, lọc theo sở thích
        if user_id and len(new_books) > limit:
            # Lấy sở thích thể loại của người dùng
            user_preferences = await self.user_repo.get_user_preferences(user_id)
            preferred_categories = set()

            if user_preferences and hasattr(user_preferences, "preferred_categories"):
                preferred_categories = set(user_preferences.preferred_categories)

            # Sắp xếp ưu tiên sách thuộc thể loại ưa thích
            def preference_score(book):
                if not hasattr(book, "categories"):
                    return 0

                category_ids = {category.id for category in book.categories}
                return len(category_ids.intersection(preferred_categories))

            new_books.sort(key=preference_score, reverse=True)

        # Chuyển đổi sang định dạng phản hồi
        result = []
        for book in new_books[:limit]:
            book_data = {
                "id": book.id,
                "title": book.title,
                "cover_image_url": book.cover_image_url,
                "cover_thumbnail_url": book.cover_thumbnail_url,
                "avg_rating": book.avg_rating,
                "publication_date": book.publication_date,
            }

            # Thêm thông tin tác giả nếu có
            if hasattr(book, "authors") and book.authors:
                book_data["authors"] = [
                    {"id": author.id, "name": author.name} for author in book.authors
                ]

            # Thêm thông tin thể loại nếu có
            if hasattr(book, "categories") and book.categories:
                book_data["categories"] = [
                    {"id": category.id, "name": category.name}
                    for category in book.categories
                ]

            result.append(book_data)

        return result

    @cached(
        ttl=7200,
        namespace="recommendations",
        key_prefix="tags",
        tags=["recommendations"],
    )
    async def get_tag_recommendations(
        self, tag_id: int, user_id: Optional[int] = None, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Lấy gợi ý sách theo tag

        Args:
            tag_id: ID tag
            user_id: ID người dùng (tùy chọn)
            limit: Số lượng gợi ý tối đa

        Returns:
            Danh sách các sách được gợi ý cho tag
        """
        # Kiểm tra tag tồn tại
        tag_repo = self.book_repo.get_tag_repository()  # Giả sử có phương thức này
        tag = await tag_repo.get_by_id(tag_id)
        if not tag:
            raise NotFoundException(f"Không tìm thấy tag có ID {tag_id}")

        # Lấy sách theo tag
        books = await self.book_repo.find_books_by_tag(
            tag_id=tag_id,
            sort_by="popularity_score",
            sort_desc=True,
            limit=limit * 2,  # Lấy nhiều hơn để lọc
        )

        # Nếu có user_id, lọc sách đã đọc
        if user_id:
            # Lấy lịch sử đọc của người dùng
            reading_history = await self.reading_history_repo.list_by_user(
                user_id=user_id, limit=50
            )
            read_book_ids = set(
                history.book_id for history in reading_history if history.book_id
            )

            # Lọc sách đã đọc
            books = [book for book in books if book.id not in read_book_ids]

        # Chuyển đổi sang định dạng phản hồi
        result = []
        for book in books[:limit]:
            book_data = {
                "id": book.id,
                "title": book.title,
                "cover_image_url": book.cover_image_url,
                "cover_thumbnail_url": book.cover_thumbnail_url,
                "avg_rating": book.avg_rating,
            }

            # Thêm thông tin tác giả nếu có
            if hasattr(book, "authors") and book.authors:
                book_data["authors"] = [
                    {"id": author.id, "name": author.name} for author in book.authors
                ]

            result.append(book_data)

        return result

    @cached(
        ttl=1800,
        namespace="recommendations",
        key_prefix="for_you",
        tags=["recommendations"],
        invalidate_on_startup=True,
    )
    async def get_recommended_for_you(
        self, user_id: int, limit: int = 20
    ) -> Dict[str, Any]:
        """
        Lấy bộ gợi ý 'Dành cho bạn' bao gồm nhiều loại gợi ý

        Args:
            user_id: ID người dùng
            limit: Số lượng gợi ý tối đa cho mỗi loại

        Returns:
            Dict chứa các loại gợi ý khác nhau
        """
        # Kiểm tra người dùng tồn tại
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng có ID {user_id}")

        # Tạo cấu trúc dữ liệu trả về
        result = {
            "personalized": [],
            "continue_reading": [],
            "trending": [],
            "new_releases": [],
        }

        # 1. Gợi ý cá nhân hóa
        personalized = await self.get_personalized_recommendations(
            user_id=user_id, limit=limit // 2  # Giảm số lượng cho mỗi loại
        )
        result["personalized"] = personalized

        # 2. Sách đang đọc dở
        reading_history = await self.reading_history_repo.list_in_progress(
            user_id=user_id, limit=limit // 4
        )

        for history in reading_history:
            if not history.book:
                continue

            book_data = {
                "id": history.book.id,
                "title": history.book.title,
                "cover_image_url": history.book.cover_image_url,
                "cover_thumbnail_url": history.book.cover_thumbnail_url,
                "avg_rating": history.book.avg_rating,
                "progress": history.progress,
                "last_read_at": history.updated_at,
            }
            result["continue_reading"].append(book_data)

        # 3. Sách thịnh hành
        trending = await self.get_trending_books(user_id=user_id, limit=limit // 4)
        result["trending"] = trending

        # 4. Sách mới phát hành
        new_releases = await self.get_new_releases(user_id=user_id, limit=limit // 4)
        result["new_releases"] = new_releases

        return result

    @cached(
        ttl=3600,
        namespace="recommendations",
        key_prefix="you_may_like",
        tags=["recommendations"],
    )
    async def get_books_you_may_like(
        self, user_id: int, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Lấy danh sách 'Có thể bạn thích' dựa trên lịch sử đọc và đánh giá

        Args:
            user_id: ID người dùng
            limit: Số lượng sách gợi ý tối đa

        Returns:
            Danh sách các sách được gợi ý
        """
        # Kiểm tra người dùng tồn tại
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(f"Không tìm thấy người dùng có ID {user_id}")

        # Lấy sách đã đọc
        reading_history = await self.reading_history_repo.list_by_user(
            user_id=user_id, limit=50
        )
        read_book_ids = set(
            history.book_id for history in reading_history if history.book_id
        )

        # Lấy sách đã đánh giá cao
        liked_reviews = await self.review_repo.list_reviews(
            user_id=user_id, limit=10, sort_by="rating", sort_desc=True
        )
        liked_book_ids = set(
            review.book_id for review in liked_reviews if review.rating >= 4
        )

        # Lấy thể loại ưa thích từ sách đã đọc và đánh giá cao
        category_counts = {}

        # Đếm thể loại từ sách đã đọc
        for book_id in read_book_ids:
            book = await self.book_repo.get_by_id(
                book_id, with_relations=["categories"]
            )
            if book and hasattr(book, "categories"):
                for category in book.categories:
                    category_counts[category.id] = (
                        category_counts.get(category.id, 0) + 1
                    )

        # Đếm thể loại từ sách đã thích (đánh giá cao hơn)
        for book_id in liked_book_ids:
            book = await self.book_repo.get_by_id(
                book_id, with_relations=["categories"]
            )
            if book and hasattr(book, "categories"):
                for category in book.categories:
                    category_counts[category.id] = (
                        category_counts.get(category.id, 0) + 2
                    )  # Trọng số cao hơn

        # Sắp xếp thể loại theo số lần xuất hiện
        popular_categories = sorted(
            category_counts.items(), key=lambda x: x[1], reverse=True
        )
        top_categories = [category_id for category_id, _ in popular_categories[:5]]

        # Lấy sách từ các thể loại ưa thích
        result = []
        books_added = set()

        for category_id in top_categories:
            if len(result) >= limit:
                break

            category_books = await self.book_repo.find_books_by_category(
                category_id=category_id,
                sort_by="popularity_score",
                sort_desc=True,
                limit=limit,
            )

            for book in category_books:
                # Bỏ qua sách đã đọc hoặc đã thêm vào kết quả
                if book.id in read_book_ids or book.id in books_added:
                    continue

                book_data = {
                    "id": book.id,
                    "title": book.title,
                    "cover_image_url": book.cover_image_url,
                    "cover_thumbnail_url": book.cover_thumbnail_url,
                    "avg_rating": book.avg_rating,
                }

                # Thêm thông tin tác giả nếu có
                if hasattr(book, "authors") and book.authors:
                    book_data["authors"] = [
                        {"id": author.id, "name": author.name}
                        for author in book.authors
                    ]

                result.append(book_data)
                books_added.add(book.id)

                if len(result) >= limit:
                    break

        # Nếu không đủ sách, bổ sung bằng sách phổ biến
        if len(result) < limit:
            popular_books = await self.book_repo.find_popular_books(limit=limit * 2)

            for book in popular_books:
                if len(result) >= limit:
                    break

                # Bỏ qua sách đã đọc hoặc đã thêm vào kết quả
                if book.id in read_book_ids or book.id in books_added:
                    continue

                book_data = {
                    "id": book.id,
                    "title": book.title,
                    "cover_image_url": book.cover_image_url,
                    "cover_thumbnail_url": book.cover_thumbnail_url,
                    "avg_rating": book.avg_rating,
                }

                # Thêm thông tin tác giả nếu có
                if hasattr(book, "authors") and book.authors:
                    book_data["authors"] = [
                        {"id": author.id, "name": author.name}
                        for author in book.authors
                    ]

                result.append(book_data)
                books_added.add(book.id)

        # Theo dõi chỉ số
        track_recommendation("you_may_like", len(result), "registered")

        return result
