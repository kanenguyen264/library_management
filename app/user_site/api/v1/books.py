from typing import Any, List, Optional, Dict
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Path,
    Query,
    status,
    Request,
    Body,
)
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.common.db.session import get_db
from app.user_site.api.deps import (
    get_current_user,
    get_current_active_user,
    get_current_premium_user,
)
from app.user_site.api.v1 import throttle_requests
from app.user_site.models.user import User
from app.user_site.schemas.book import (
    BookResponse,
    BookDetailResponse,
    BookListResponse,
    BookRatingCreate,
    BookRecommendationResponse,
)
from app.user_site.services.book_service import BookService
from app.user_site.services.review_service import ReviewService
from app.logging.setup import get_logger
from app.monitoring.metrics import track_request_time
from app.cache.decorators import cache_response, invalidate_cache
from app.security.audit.audit_trails import log_data_operation
from app.core.exceptions import (
    NotFoundException,
    ForbiddenException,
    BadRequestException,
    ConflictException,
)

router = APIRouter()
logger = get_logger("book_api")


@router.get("/", response_model=BookListResponse)
@track_request_time(endpoint="list_books")
@cache_response(
    ttl=300,
    vary_by=[
        "skip",
        "limit",
        "sort_by",
        "sort_desc",
        "category_id",
        "tag_id",
        "author_id",
        "is_featured",
        "language",
        "search",
        "min_rating",
        "max_rating",
        "has_audio",
        "is_premium",
    ],
)
async def list_books(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    sort_by: str = Query(
        "popularity_score",
        regex="^(title|publication_date|avg_rating|popularity_score|release_date)$",
    ),
    sort_desc: bool = Query(True),
    category_id: Optional[int] = Query(None, gt=0),
    tag_id: Optional[int] = Query(None, gt=0),
    author_id: Optional[int] = Query(None, gt=0),
    is_featured: Optional[bool] = Query(None),
    language: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    min_rating: Optional[float] = Query(None, ge=0, le=5),
    max_rating: Optional[float] = Query(None, ge=0, le=5),
    has_audio: Optional[bool] = Query(None),
    is_premium: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
) -> Any:
    """
    Lấy danh sách sách với nhiều điều kiện lọc.

    - **skip**: Số lượng bản ghi bỏ qua (phân trang)
    - **limit**: Số lượng bản ghi lấy về
    - **sort_by**: Sắp xếp theo trường (title, publication_date, avg_rating, popularity_score, release_date)
    - **sort_desc**: Sắp xếp giảm dần (True) hoặc tăng dần (False)
    - **category_id**: Lọc theo danh mục
    - **tag_id**: Lọc theo tag
    - **author_id**: Lọc theo tác giả
    - **is_featured**: Lọc sách nổi bật
    - **language**: Lọc theo ngôn ngữ
    - **search**: Tìm kiếm theo từ khóa
    - **min_rating**: Lọc theo đánh giá tối thiểu
    - **max_rating**: Lọc theo đánh giá tối đa
    - **has_audio**: Lọc sách có audio
    - **is_premium**: Lọc sách premium
    """
    try:
        book_service = BookService(db)

        # Điều chỉnh tham số tìm kiếm (nếu có)
        if search and len(search) < 2:
            search = None

        # Validate điều kiện lọc
        if (
            min_rating is not None
            and max_rating is not None
            and min_rating > max_rating
        ):
            raise BadRequestException(
                detail="min_rating không thể lớn hơn max_rating", field="min_rating"
            )

        books, total = await book_service.list_books(
            skip=skip,
            limit=limit,
            sort_by=sort_by,
            sort_desc=sort_desc,
            category_id=category_id,
            tag_id=tag_id,
            author_id=author_id,
            is_featured=is_featured,
            language=language,
            search=search,
            min_rating=min_rating,
            max_rating=max_rating,
            has_audio=has_audio,
            is_premium=is_premium,
            user_id=current_user.id if current_user else None,
        )

        return {"items": books, "total": total}
    except BadRequestException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách sách: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi lấy danh sách sách",
        )


@router.get("/trending", response_model=List[BookResponse])
@track_request_time(endpoint="trending_books")
@cache_response(ttl=1800, vary_by=["limit", "period"])
async def get_trending_books(
    limit: int = Query(10, ge=1, le=50),
    period: str = Query("week", regex="^(day|week|month)$"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Lấy danh sách sách đang thịnh hành.

    - **limit**: Số lượng sách trả về
    - **period**: Khoảng thời gian (day, week, month)
    """
    try:
        book_service = BookService(db)

        trending_books = await book_service.get_trending_books(
            limit=limit, period=period
        )

        return trending_books
    except Exception as e:
        logger.error(f"Lỗi khi lấy sách trending: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi lấy sách trending",
        )


@router.get("/new-releases", response_model=List[BookResponse])
@track_request_time(endpoint="new_release_books")
@cache_response(ttl=3600, vary_by=["limit", "days"])
async def get_new_releases(
    limit: int = Query(10, ge=1, le=50),
    days: int = Query(30, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Lấy danh sách sách mới phát hành.

    - **limit**: Số lượng sách trả về
    - **days**: Số ngày gần đây để lọc (mặc định 30 ngày)
    """
    try:
        book_service = BookService(db)

        new_books = await book_service.get_new_releases(limit=limit, days=days)

        return new_books
    except Exception as e:
        logger.error(f"Lỗi khi lấy sách mới phát hành: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi lấy sách mới phát hành",
        )


@router.get("/{book_id}", response_model=BookDetailResponse)
@track_request_time(endpoint="get_book")
@cache_response(ttl=300, vary_by=["book_id", "current_user.id"])
async def get_book(
    book_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
    request: Request = None,
) -> Any:
    """
    Lấy thông tin chi tiết của một cuốn sách.

    - **book_id**: ID của sách
    """
    book_service = BookService(db)

    try:
        book = await book_service.get_book_by_id(
            book_id=book_id, user_id=current_user.id if current_user else None
        )

        if not book:
            raise NotFoundException(
                detail=f"Không tìm thấy sách với ID: {book_id}", code="book_not_found"
            )

        # Ghi nhận lượt xem
        await book_service.record_book_view(book_id)

        # Ghi lại lịch sử xem nếu có user đăng nhập
        if current_user:
            await book_service.record_book_view_history(
                user_id=current_user.id, book_id=book_id
            )

        # Ghi log hành động
        client_ip = request.client.host if request else None
        user_agent = request.headers.get("User-Agent", "") if request else None

        if current_user and request:
            await log_data_operation(
                operation="view",
                resource_type="book",
                resource_id=str(book_id),
                user_id=str(current_user.id),
                user_type="user",
                status="success",
                ip_address=client_ip,
                user_agent=user_agent,
            )

        return book
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin sách {book_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi lấy thông tin sách",
        )


@router.get("/{book_id}/similar", response_model=List[BookResponse])
@track_request_time(endpoint="get_similar_books")
@cache_response(ttl=1800, vary_by=["book_id", "limit"])
async def get_similar_books(
    book_id: int = Path(..., gt=0),
    limit: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Lấy danh sách sách tương tự với một cuốn sách nhất định.

    - **book_id**: ID của sách
    - **limit**: Số lượng sách tương tự trả về
    """
    book_service = BookService(db)

    try:
        # Kiểm tra sách có tồn tại không
        book = await book_service.get_book_by_id(book_id)
        if not book:
            raise NotFoundException(
                detail=f"Không tìm thấy sách với ID: {book_id}", code="book_not_found"
            )

        similar_books = await book_service.get_similar_books(
            book_id=book_id, limit=limit
        )
        return similar_books
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy sách tương tự với sách {book_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi lấy sách tương tự",
        )


@router.get("/{book_id}/chapters", response_model=List[Dict[str, Any]])
@track_request_time(endpoint="get_book_chapters")
@cache_response(ttl=300, vary_by=["book_id", "current_user.id"])
async def get_book_chapters(
    book_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
) -> Any:
    """
    Lấy danh sách các chương của một cuốn sách.

    - **book_id**: ID của sách
    """
    book_service = BookService(db)

    try:
        # Kiểm tra sách có tồn tại không
        book = await book_service.get_book_by_id(book_id)
        if not book:
            raise NotFoundException(
                detail=f"Không tìm thấy sách với ID: {book_id}", code="book_not_found"
            )

        # Kiểm tra sách có yêu cầu quyền truy cập không
        if book.is_premium and (not current_user or not current_user.is_premium):
            raise ForbiddenException(
                detail="Sách này yêu cầu tài khoản Premium để xem nội dung",
                code="premium_required",
            )

        chapters = await book_service.get_book_chapters(
            book_id=book_id, user_id=current_user.id if current_user else None
        )

        return chapters
    except NotFoundException:
        raise
    except ForbiddenException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách chương của sách {book_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi lấy danh sách chương",
        )


@router.post("/{book_id}/rate", status_code=status.HTTP_201_CREATED)
@track_request_time(endpoint="rate_book")
@invalidate_cache(namespace="books", tags=["book_ratings"])
async def rate_book(
    book_id: int = Path(..., gt=0),
    rating_data: BookRatingCreate = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
) -> Dict[str, Any]:
    """
    Đánh giá sách.

    - **book_id**: ID của sách
    - **rating**: Điểm đánh giá (1-5)
    """
    # Giới hạn số lần đánh giá sách
    await throttle_requests(
        "rate_book",
        limit=20,
        period=3600,
        request=request,
        current_user=current_user,
        db=db,
    )

    try:
        book_service = BookService(db)

        # Kiểm tra sách có tồn tại không
        book = await book_service.get_book_by_id(book_id)
        if not book:
            raise NotFoundException(
                detail=f"Không tìm thấy sách với ID: {book_id}", code="book_not_found"
            )

        # Tạo đánh giá
        rating = await book_service.rate_book(
            user_id=current_user.id, book_id=book_id, rating=rating_data.rating
        )

        # Ghi log hành động
        client_ip = request.client.host if request else None
        user_agent = request.headers.get("User-Agent", "") if request else None

        await log_data_operation(
            operation="rate",
            resource_type="book",
            resource_id=str(book_id),
            user_id=str(current_user.id),
            user_type="user",
            status="success",
            ip_address=client_ip,
            changes={"rating": rating_data.rating},
            user_agent=user_agent,
        )

        return {
            "success": True,
            "message": "Đánh giá sách thành công",
            "book_id": book_id,
            "rating": rating_data.rating,
            "updated": rating["updated"],
        }

    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi đánh giá sách {book_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi đánh giá sách",
        )


@router.post("/{book_id}/favorite", status_code=status.HTTP_200_OK)
@track_request_time(endpoint="favorite_book")
@invalidate_cache(namespace="books", tags=["user_favorites"])
async def favorite_book(
    book_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
) -> Dict[str, Any]:
    """
    Thêm sách vào danh sách yêu thích.

    - **book_id**: ID của sách
    """
    try:
        book_service = BookService(db)

        # Kiểm tra sách có tồn tại không
        book = await book_service.get_book_by_id(book_id)
        if not book:
            raise NotFoundException(
                detail=f"Không tìm thấy sách với ID: {book_id}", code="book_not_found"
            )

        # Thêm vào yêu thích
        is_new = await book_service.add_to_favorites(
            user_id=current_user.id, book_id=book_id
        )

        # Ghi log hành động
        client_ip = request.client.host if request else None
        user_agent = request.headers.get("User-Agent", "") if request else None

        await log_data_operation(
            operation="favorite",
            resource_type="book",
            resource_id=str(book_id),
            user_id=str(current_user.id),
            user_type="user",
            status="success",
            ip_address=client_ip,
            user_agent=user_agent,
        )

        if is_new:
            return {
                "success": True,
                "message": "Thêm sách vào danh sách yêu thích thành công",
                "book_id": book_id,
            }
        else:
            return {
                "success": True,
                "message": "Sách đã có trong danh sách yêu thích",
                "book_id": book_id,
            }

    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi thêm sách {book_id} vào yêu thích: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi thêm sách vào danh sách yêu thích",
        )


@router.delete("/{book_id}/favorite", status_code=status.HTTP_200_OK)
@track_request_time(endpoint="unfavorite_book")
@invalidate_cache(namespace="books", tags=["user_favorites"])
async def unfavorite_book(
    book_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
) -> Dict[str, Any]:
    """
    Xóa sách khỏi danh sách yêu thích.

    - **book_id**: ID của sách
    """
    try:
        book_service = BookService(db)

        # Xóa khỏi yêu thích
        removed = await book_service.remove_from_favorites(
            user_id=current_user.id, book_id=book_id
        )

        if not removed:
            return {
                "success": True,
                "message": "Sách không có trong danh sách yêu thích",
                "book_id": book_id,
            }

        # Ghi log hành động
        client_ip = request.client.host if request else None
        user_agent = request.headers.get("User-Agent", "") if request else None

        await log_data_operation(
            operation="unfavorite",
            resource_type="book",
            resource_id=str(book_id),
            user_id=str(current_user.id),
            user_type="user",
            status="success",
            ip_address=client_ip,
            user_agent=user_agent,
        )

        return {
            "success": True,
            "message": "Xóa sách khỏi danh sách yêu thích thành công",
            "book_id": book_id,
        }

    except Exception as e:
        logger.error(f"Lỗi khi xóa sách {book_id} khỏi yêu thích: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi xóa sách khỏi danh sách yêu thích",
        )


@router.get("/favorites", response_model=BookListResponse)
@track_request_time(endpoint="list_favorite_books")
@cache_response(ttl=300, vary_by=["current_user.id", "skip", "limit"])
async def list_favorite_books(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Lấy danh sách sách yêu thích của người dùng.

    - **skip**: Số lượng bản ghi bỏ qua (phân trang)
    - **limit**: Số lượng bản ghi lấy về
    """
    try:
        book_service = BookService(db)

        books, total = await book_service.get_favorite_books(
            user_id=current_user.id, skip=skip, limit=limit
        )

        return {"items": books, "total": total}
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách sách yêu thích: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi lấy danh sách sách yêu thích",
        )


@router.get(
    "/recommendations/personalized", response_model=List[BookRecommendationResponse]
)
@track_request_time(endpoint="get_personalized_recommendations")
@cache_response(ttl=1800, vary_by=["current_user.id", "limit"])
async def get_personalized_recommendations(
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Lấy danh sách sách được đề xuất cá nhân hóa dựa trên lịch sử đọc, sở thích.

    - **limit**: Số lượng sách đề xuất
    """
    try:
        book_service = BookService(db)

        recommendations = await book_service.get_personalized_recommendations(
            user_id=current_user.id, limit=limit
        )

        return recommendations
    except Exception as e:
        logger.error(f"Lỗi khi lấy đề xuất sách cá nhân: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi lấy đề xuất sách cá nhân",
        )
