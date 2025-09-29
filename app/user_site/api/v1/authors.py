from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, Path, Query, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.db.session import get_db
from app.user_site.api.deps import get_current_user
from app.user_site.models.user import User
from app.user_site.schemas.author import (
    AuthorResponse,
    AuthorDetailResponse,
    AuthorListResponse,
    AuthorStatsResponse,
    AuthorWithBooksResponse,
)
from app.user_site.schemas.book import BookBrief
from app.user_site.services.author_service import AuthorService
from app.logging.setup import get_logger
from app.monitoring.metrics import track_request_time
from app.cache.decorators import cache_response
from app.core.exceptions import NotFoundException, BadRequestException, ServerException

router = APIRouter()
logger = get_logger("author_api")


@router.get("/", response_model=AuthorListResponse)
@track_request_time(endpoint="list_authors")
@cache_response(ttl=600, vary_by=["page", "limit", "search", "sort_by", "genre_id"])
async def list_authors(
    page: int = Query(1, ge=1, description="Trang hiện tại"),
    limit: int = Query(20, ge=1, le=100, description="Số lượng tác giả mỗi trang"),
    search: Optional[str] = Query(
        None, min_length=2, description="Tìm kiếm theo tên tác giả"
    ),
    sort_by: str = Query(
        "popularity",
        regex="^(name|popularity|book_count)$",
        description="Sắp xếp theo trường",
    ),
    sort_desc: bool = Query(True, description="Sắp xếp giảm dần"),
    genre_id: Optional[int] = Query(None, gt=0, description="Lọc theo thể loại"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách tác giả với các tùy chọn lọc và sắp xếp.

    - **page**: Trang hiện tại
    - **limit**: Số lượng tác giả mỗi trang
    - **search**: Tìm kiếm theo tên tác giả (ít nhất 2 ký tự)
    - **sort_by**: Sắp xếp theo trường (name, popularity, book_count)
    - **sort_desc**: Sắp xếp giảm dần (true) hoặc tăng dần (false)
    - **genre_id**: Lọc tác giả theo thể loại sách
    """
    author_service = AuthorService(db)

    try:
        # Tính toán skip từ page và limit
        skip = (page - 1) * limit

        authors, total = await author_service.list_authors(
            skip=skip,
            limit=limit,
            search=search,
            sort_by=sort_by,
            sort_desc=sort_desc,
            genre_id=genre_id,
        )

        # Tính toán tổng số trang
        total_pages = (total + limit - 1) // limit if total > 0 else 0

        return {
            "items": authors,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
        }
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách tác giả: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy danh sách tác giả")


@router.get("/popular", response_model=List[AuthorResponse])
@track_request_time(endpoint="get_popular_authors")
@cache_response(ttl=3600, vary_by=["limit"])
async def get_popular_authors(
    limit: int = Query(10, ge=1, le=50, description="Số lượng tác giả trả về"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách tác giả phổ biến.

    Trả về danh sách tác giả được đọc nhiều nhất trên hệ thống, dựa trên số lượt xem và đánh giá sách.
    """
    author_service = AuthorService(db)

    try:
        return await author_service.get_popular_authors(limit=limit)
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách tác giả phổ biến: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy danh sách tác giả phổ biến")


@router.get("/{author_id}", response_model=AuthorDetailResponse)
@track_request_time(endpoint="get_author")
@cache_response(ttl=1800, vary_by=["author_id"])
async def get_author(
    author_id: int = Path(..., gt=0, description="ID của tác giả"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy thông tin chi tiết của một tác giả.

    Trả về thông tin chi tiết về tác giả bao gồm tiểu sử, thống kê sách, thể loại và thông tin khác.
    """
    author_service = AuthorService(db)

    try:
        author = await author_service.get_author_by_id(author_id)

        if not author:
            raise NotFoundException(
                detail=f"Không tìm thấy tác giả với ID: {author_id}",
                code="author_not_found",
            )

        return author
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin tác giả {author_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy thông tin tác giả")


@router.get("/slug/{slug}", response_model=AuthorDetailResponse)
@track_request_time(endpoint="get_author_by_slug")
@cache_response(ttl=1800, vary_by=["slug"])
async def get_author_by_slug(
    slug: str = Path(..., min_length=1, description="Slug của tác giả"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy thông tin chi tiết của một tác giả theo slug.

    Slug là một chuỗi thân thiện với URL dựa trên tên của tác giả.
    """
    author_service = AuthorService(db)

    try:
        author = await author_service.get_author_by_slug(slug)

        if not author:
            raise NotFoundException(
                detail=f"Không tìm thấy tác giả với slug: {slug}",
                code="author_not_found",
            )

        return author
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin tác giả theo slug {slug}: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy thông tin tác giả")


@router.get("/{author_id}/books", response_model=Dict[str, Any])
@track_request_time(endpoint="get_author_books")
@cache_response(
    ttl=600, vary_by=["author_id", "page", "page_size", "sort_by", "category_id"]
)
async def get_author_books(
    author_id: int = Path(..., gt=0, description="ID của tác giả"),
    page: int = Query(1, ge=1, description="Trang hiện tại"),
    page_size: int = Query(20, ge=1, le=50, description="Số lượng sách mỗi trang"),
    sort_by: str = Query(
        "popularity",
        regex="^(title|publication_date|popularity|rating)$",
        description="Sắp xếp theo trường",
    ),
    sort_desc: bool = Query(True, description="Sắp xếp giảm dần"),
    category_id: Optional[int] = Query(None, gt=0, description="Lọc theo danh mục"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """
    Lấy danh sách sách của một tác giả với nhiều tùy chọn lọc và sắp xếp.

    - **author_id**: ID của tác giả
    - **page**: Trang hiện tại
    - **page_size**: Số lượng sách mỗi trang
    - **sort_by**: Sắp xếp theo trường (title, publication_date, popularity, rating)
    - **sort_desc**: Sắp xếp giảm dần (true) hoặc tăng dần (false)
    - **category_id**: Lọc sách theo danh mục
    """
    author_service = AuthorService(db)

    try:
        # Kiểm tra tác giả có tồn tại không
        author = await author_service.get_author_by_id(author_id)
        if not author:
            raise NotFoundException(
                detail=f"Không tìm thấy tác giả với ID: {author_id}",
                code="author_not_found",
            )

        books, total_books, total_pages = await author_service.get_author_books(
            author_id=author_id,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_desc=sort_desc,
            category_id=category_id,
            user_id=current_user.id if current_user else None,
        )

        return {
            "items": books,
            "total": total_books,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "author": {"id": author.id, "name": author.name, "slug": author.slug},
        }
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách sách của tác giả {author_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy danh sách sách của tác giả")


@router.get("/genre/{genre_id}/popular", response_model=List[AuthorResponse])
@track_request_time(endpoint="get_popular_authors_by_genre")
@cache_response(ttl=3600, vary_by=["genre_id", "limit"])
async def get_popular_authors_by_genre(
    genre_id: int = Path(..., gt=0, description="ID của thể loại"),
    limit: int = Query(10, ge=1, le=50, description="Số lượng tác giả trả về"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách tác giả phổ biến trong một thể loại cụ thể.

    Trả về các tác giả nổi tiếng nhất trong thể loại được chỉ định, dựa trên lượt đọc và đánh giá.
    """
    author_service = AuthorService(db)

    try:
        # Kiểm tra thể loại có tồn tại không
        if not await author_service.genre_exists(genre_id):
            raise NotFoundException(
                detail=f"Không tìm thấy thể loại với ID: {genre_id}",
                code="genre_not_found",
            )

        authors = await author_service.get_popular_authors_by_genre(genre_id, limit)
        return authors
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy tác giả phổ biến theo thể loại {genre_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy tác giả phổ biến theo thể loại")


@router.get("/{author_id}/similar", response_model=List[AuthorResponse])
@track_request_time(endpoint="get_similar_authors")
@cache_response(ttl=1800, vary_by=["author_id", "limit"])
async def get_similar_authors(
    author_id: int = Path(..., gt=0, description="ID của tác giả"),
    limit: int = Query(5, ge=1, le=20, description="Số lượng tác giả trả về"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách các tác giả tương tự với một tác giả cụ thể.

    Tìm tác giả tương tự dựa trên thể loại sách, phong cách viết và độc giả đọc chung.
    """
    author_service = AuthorService(db)

    try:
        # Kiểm tra tác giả có tồn tại không
        if not await author_service.author_exists(author_id):
            raise NotFoundException(
                detail=f"Không tìm thấy tác giả với ID: {author_id}",
                code="author_not_found",
            )

        similar_authors = await author_service.get_similar_authors(author_id, limit)
        return similar_authors
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy tác giả tương tự với tác giả {author_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy tác giả tương tự")


@router.get("/{author_id}/stats", response_model=AuthorStatsResponse)
@track_request_time(endpoint="get_author_stats")
@cache_response(ttl=1800, vary_by=["author_id"])
async def get_author_stats(
    author_id: int = Path(..., gt=0, description="ID của tác giả"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy thống kê chi tiết về một tác giả.

    Bao gồm tổng số sách, phân phối thể loại, xếp hạng trung bình, lượt đọc và số liệu khác.
    """
    author_service = AuthorService(db)

    try:
        # Kiểm tra tác giả có tồn tại không
        if not await author_service.author_exists(author_id):
            raise NotFoundException(
                detail=f"Không tìm thấy tác giả với ID: {author_id}",
                code="author_not_found",
            )

        stats = await author_service.get_author_stats(author_id)
        return stats
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thống kê tác giả {author_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy thống kê tác giả")


@router.get("/{author_id}/complete", response_model=AuthorWithBooksResponse)
@track_request_time(endpoint="get_author_with_books")
@cache_response(ttl=1200, vary_by=["author_id"])
async def get_author_with_books(
    author_id: int = Path(..., gt=0, description="ID của tác giả"),
    limit: int = Query(10, ge=1, le=50, description="Số lượng sách hiển thị"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy thông tin đầy đủ về tác giả bao gồm cả danh sách các sách nổi bật.

    Endpoint này kết hợp thông tin tác giả và một số sách tiêu biểu trong một lần gọi API.
    """
    author_service = AuthorService(db)

    try:
        # Kiểm tra tác giả có tồn tại không
        author = await author_service.get_author_by_id(author_id)
        if not author:
            raise NotFoundException(
                detail=f"Không tìm thấy tác giả với ID: {author_id}",
                code="author_not_found",
            )

        # Lấy danh sách sách nổi bật của tác giả
        featured_books = await author_service.get_author_featured_books(
            author_id, limit
        )

        return {"author": author, "featured_books": featured_books}
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin đầy đủ của tác giả {author_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy thông tin đầy đủ của tác giả")


@router.get("/trending", response_model=List[AuthorResponse])
@track_request_time(endpoint="get_trending_authors")
@cache_response(ttl=1800, vary_by=["time_period", "limit"])
async def get_trending_authors(
    time_period: str = Query(
        "week",
        regex="^(day|week|month)$",
        description="Khoảng thời gian (day, week, month)",
    ),
    limit: int = Query(10, ge=1, le=50, description="Số lượng tác giả trả về"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách tác giả đang thịnh hành trong khoảng thời gian cụ thể.

    Tác giả thịnh hành được xác định dựa trên hoạt động gần đây về lượt đọc, đánh giá và bình luận.
    """
    author_service = AuthorService(db)

    try:
        trending_authors = await author_service.get_trending_authors(time_period, limit)
        return trending_authors
    except Exception as e:
        logger.error(f"Lỗi khi lấy tác giả thịnh hành: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy tác giả thịnh hành")


@router.get("/search/advanced", response_model=AuthorListResponse)
@track_request_time(endpoint="advanced_author_search")
async def advanced_author_search(
    query: str = Query(None, min_length=2, description="Từ khóa tìm kiếm"),
    genres: List[int] = Query(None, description="Danh sách ID thể loại"),
    min_books: int = Query(None, ge=1, description="Số lượng sách tối thiểu"),
    min_rating: float = Query(None, ge=1, le=5, description="Xếp hạng tối thiểu"),
    language: str = Query(None, description="Ngôn ngữ viết"),
    page: int = Query(1, ge=1, description="Trang hiện tại"),
    limit: int = Query(20, ge=1, le=100, description="Số lượng kết quả mỗi trang"),
    db: AsyncSession = Depends(get_db),
):
    """
    Tìm kiếm nâng cao với nhiều điều kiện lọc cho tác giả.

    Cho phép tìm kiếm phức tạp dựa trên các tiêu chí như thể loại, số lượng sách, đánh giá và ngôn ngữ.
    """
    author_service = AuthorService(db)

    try:
        # Tính toán skip từ page và limit
        skip = (page - 1) * limit

        # Tạo dict các tham số tìm kiếm
        search_params = {
            "query": query,
            "genres": genres,
            "min_books": min_books,
            "min_rating": min_rating,
            "language": language,
            "skip": skip,
            "limit": limit,
        }

        # Lọc các giá trị None
        search_params = {k: v for k, v in search_params.items() if v is not None}

        authors, total = await author_service.advanced_author_search(search_params)

        # Tính toán tổng số trang
        total_pages = (total + limit - 1) // limit if total > 0 else 0

        return {
            "items": authors,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
        }
    except BadRequestException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi tìm kiếm nâng cao tác giả: {str(e)}")
        raise ServerException(detail="Lỗi khi tìm kiếm nâng cao tác giả")
