from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, Path, Query, status, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.user_site.api.v1 import throttle_requests

from app.common.db.session import get_db
from app.user_site.api.deps import get_current_user
from app.user_site.models.user import User
from app.user_site.schemas.book_series import (
    BookSeriesResponse,
    BookSeriesDetailResponse,
    BookSeriesWithBooksResponse,
)
from app.user_site.services.book_series_service import BookSeriesService
from app.user_site.services.book_service import BookService
from app.logging.setup import get_logger
from app.monitoring.metrics import track_request_time
from app.cache.decorators import cache_response
from app.core.exceptions import (
    NotFoundException,
    ServerException,
    ForbiddenException,
    BadRequestException,
)

router = APIRouter()
logger = get_logger("book_series_api")


@router.get("", response_model=Dict[str, Any])
@track_request_time(endpoint="list_book_series")
@cache_response(
    ttl=600, vary_by=["page", "page_size", "sort_by", "sort_desc", "search", "genre_id"]
)
async def list_book_series(
    page: int = Query(1, ge=1, description="Trang hiện tại"),
    page_size: int = Query(20, ge=1, le=100, description="Số lượng series mỗi trang"),
    sort_by: str = Query(
        "created_at",
        regex="^(created_at|popularity|name)$",
        description="Sắp xếp theo trường",
    ),
    sort_desc: bool = Query(True, description="Sắp xếp giảm dần"),
    search: Optional[str] = Query(None, description="Tìm kiếm theo tên series"),
    genre_id: Optional[int] = Query(None, description="Lọc theo thể loại"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """
    Lấy danh sách series sách.

    - **page**: Trang hiện tại
    - **page_size**: Số lượng series mỗi trang
    - **sort_by**: Sắp xếp theo trường (created_at, popularity, name)
    - **sort_desc**: Sắp xếp giảm dần (True) hoặc tăng dần (False)
    - **search**: Tìm kiếm theo tên series
    - **genre_id**: Lọc theo thể loại
    """
    book_series_service = BookSeriesService(db)

    try:
        # Tính toán skip từ page và page_size
        skip = (page - 1) * page_size

        # Lấy danh sách series
        series_list, total = await book_series_service.list_book_series(
            skip=skip,
            limit=page_size,
            sort_by=sort_by,
            sort_desc=sort_desc,
            search=search,
            genre_id=genre_id,
        )

        # Nếu người dùng đã đăng nhập, đánh dấu series nào đã follow
        if current_user:
            followed_series = await book_series_service.get_followed_series_ids(
                current_user.id
            )

            for series in series_list:
                series.is_followed = series.id in followed_series

        # Tính toán thông tin phân trang
        total_pages = (total + page_size - 1) // page_size

        return {
            "items": series_list,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách series sách: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy danh sách series sách")


@router.get("/trending", response_model=List[BookSeriesResponse])
@track_request_time(endpoint="get_trending_series")
@cache_response(ttl=3600, vary_by=["limit"])
async def get_trending_series(
    limit: int = Query(10, ge=1, le=50, description="Số lượng series trả về"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """
    Lấy danh sách series sách thịnh hành.

    - **limit**: Số lượng series trả về
    """
    book_series_service = BookSeriesService(db)

    try:
        # Lấy danh sách series thịnh hành
        trending_series = await book_series_service.get_trending_series(limit=limit)

        # Nếu người dùng đã đăng nhập, đánh dấu series nào đã follow
        if current_user:
            followed_series = await book_series_service.get_followed_series_ids(
                current_user.id
            )

            for series in trending_series:
                series.is_followed = series.id in followed_series

        return trending_series
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách series sách thịnh hành: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy danh sách series sách thịnh hành")


@router.get("/recommended", response_model=List[BookSeriesResponse])
@track_request_time(endpoint="get_recommended_series")
@cache_response(ttl=1800, vary_by=["limit", "current_user.id"])
async def get_recommended_series(
    limit: int = Query(10, ge=1, le=50, description="Số lượng series trả về"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """
    Lấy danh sách series sách được đề xuất.

    - **limit**: Số lượng series trả về
    """
    book_series_service = BookSeriesService(db)

    try:
        # Nếu người dùng đã đăng nhập, lấy đề xuất dựa trên lịch sử đọc
        if current_user:
            recommended_series = (
                await book_series_service.get_personalized_recommendations(
                    user_id=current_user.id, limit=limit
                )
            )

            # Đánh dấu series nào đã follow
            followed_series = await book_series_service.get_followed_series_ids(
                current_user.id
            )

            for series in recommended_series:
                series.is_followed = series.id in followed_series
        else:
            # Nếu chưa đăng nhập, lấy đề xuất chung
            recommended_series = await book_series_service.get_general_recommendations(
                limit=limit
            )

        return recommended_series
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách series sách đề xuất: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy danh sách series sách đề xuất")


@router.get("/{series_id}", response_model=BookSeriesDetailResponse)
@track_request_time(endpoint="get_book_series")
@cache_response(ttl=600, vary_by=["series_id", "current_user.id"])
async def get_book_series(
    series_id: int = Path(..., gt=0, description="ID của series sách"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """
    Lấy thông tin chi tiết của một series sách.

    - **series_id**: ID của series sách
    """
    book_series_service = BookSeriesService(db)

    try:
        # Lấy thông tin series
        series = await book_series_service.get_book_series_by_id(series_id)

        if not series:
            raise NotFoundException(
                detail=f"Không tìm thấy series sách với ID: {series_id}",
                code="series_not_found",
            )

        # Tăng số lượt xem
        await book_series_service.increment_view_count(series_id)

        # Kiểm tra xem người dùng đã follow series này chưa
        if current_user:
            series.is_followed = await book_series_service.is_following_series(
                user_id=current_user.id, series_id=series_id
            )

            # Ghi lại lịch sử xem của người dùng
            await book_series_service.record_series_view(
                user_id=current_user.id, series_id=series_id
            )

        return series
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin series sách {series_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy thông tin series sách")


@router.get("/{series_id}/books", response_model=BookSeriesWithBooksResponse)
@track_request_time(endpoint="get_series_books")
@cache_response(ttl=600, vary_by=["series_id", "current_user.id"])
async def get_series_books(
    series_id: int = Path(..., gt=0, description="ID của series sách"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """
    Lấy danh sách sách trong một series.

    - **series_id**: ID của series sách
    """
    book_series_service = BookSeriesService(db)
    book_service = BookService(db)

    try:
        # Lấy thông tin series
        series = await book_series_service.get_book_series_by_id(series_id)

        if not series:
            raise NotFoundException(
                detail=f"Không tìm thấy series sách với ID: {series_id}",
                code="series_not_found",
            )

        # Lấy danh sách sách trong series
        books = await book_series_service.get_books_in_series(series_id)

        # Nếu người dùng đã đăng nhập, đánh dấu sách nào đã đọc
        if current_user:
            # Lấy danh sách sách đã đọc
            read_books = await book_service.get_read_books_by_user(current_user.id)

            for book in books:
                book.is_read = book.id in read_books

            # Ghi lại lịch sử xem của người dùng
            await book_series_service.record_series_view(
                user_id=current_user.id, series_id=series_id
            )

        # Kiểm tra xem người dùng đã follow series này chưa
        if current_user:
            series.is_followed = await book_series_service.is_following_series(
                user_id=current_user.id, series_id=series_id
            )

        # Tăng số lượt xem
        await book_series_service.increment_view_count(series_id)

        return {"series": series, "books": books}
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách sách trong series {series_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy danh sách sách trong series")


@router.post("/{series_id}/follow", status_code=status.HTTP_204_NO_CONTENT)
@track_request_time(endpoint="follow_series")
async def follow_series(
    series_id: int = Path(..., gt=0, description="ID của series sách"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """
    Theo dõi một series sách.

    - **series_id**: ID của series sách
    """
    book_series_service = BookSeriesService(db)

    try:
        # Giới hạn số lượng action trong 1 phút
        await throttle_requests(
            "follow_series",
            limit=10,
            period=60,
            current_user=current_user,
            request=request,
            db=db,
        )

        # Kiểm tra series có tồn tại không
        series = await book_series_service.get_book_series_by_id(series_id)

        if not series:
            raise NotFoundException(
                detail=f"Không tìm thấy series sách với ID: {series_id}",
                code="series_not_found",
            )

        # Thêm follow
        await book_series_service.follow_series(
            user_id=current_user.id, series_id=series_id
        )

        # Ghi log
        logger.info(f"Người dùng {current_user.id} đã theo dõi series {series_id}")

        return None
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi theo dõi series sách {series_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi theo dõi series sách")


@router.post("/{series_id}/unfollow", status_code=status.HTTP_204_NO_CONTENT)
@track_request_time(endpoint="unfollow_series")
async def unfollow_series(
    series_id: int = Path(..., gt=0, description="ID của series sách"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """
    Hủy theo dõi một series sách.

    - **series_id**: ID của series sách
    """
    book_series_service = BookSeriesService(db)

    try:
        # Giới hạn số lượng action trong 1 phút
        await throttle_requests(
            "unfollow_series",
            limit=10,
            period=60,
            current_user=current_user,
            request=request,
            db=db,
        )

        # Kiểm tra series có tồn tại không
        series = await book_series_service.get_book_series_by_id(series_id)

        if not series:
            raise NotFoundException(
                detail=f"Không tìm thấy series sách với ID: {series_id}",
                code="series_not_found",
            )

        # Hủy follow
        await book_series_service.unfollow_series(
            user_id=current_user.id, series_id=series_id
        )

        # Ghi log
        logger.info(f"Người dùng {current_user.id} đã hủy theo dõi series {series_id}")

        return None
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi hủy theo dõi series sách {series_id}: {str(e)}")
        raise ServerException(detail="Lỗi khi hủy theo dõi series sách")


@router.get("/followed", response_model=Dict[str, Any])
@track_request_time(endpoint="get_followed_series")
async def get_followed_series(
    page: int = Query(1, ge=1, description="Trang hiện tại"),
    page_size: int = Query(20, ge=1, le=100, description="Số lượng series mỗi trang"),
    sort_by: str = Query(
        "followed_at", regex="^(followed_at|name)$", description="Sắp xếp theo trường"
    ),
    sort_desc: bool = Query(True, description="Sắp xếp giảm dần"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách series sách đã theo dõi.

    - **page**: Trang hiện tại
    - **page_size**: Số lượng series mỗi trang
    - **sort_by**: Sắp xếp theo trường (followed_at, name)
    - **sort_desc**: Sắp xếp giảm dần (True) hoặc tăng dần (False)
    """
    book_series_service = BookSeriesService(db)

    try:
        # Tính toán skip từ page và page_size
        skip = (page - 1) * page_size

        # Lấy danh sách series đã theo dõi
        series_list, total = await book_series_service.get_followed_series(
            user_id=current_user.id,
            skip=skip,
            limit=page_size,
            sort_by=sort_by,
            sort_desc=sort_desc,
        )

        # Đánh dấu tất cả series là đã follow
        for series in series_list:
            series.is_followed = True

        # Tính toán thông tin phân trang
        total_pages = (total + page_size - 1) // page_size

        return {
            "items": series_list,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách series sách đã theo dõi: {str(e)}")
        raise ServerException(detail="Lỗi khi lấy danh sách series sách đã theo dõi")


@router.get("/similar/{series_id}", response_model=List[BookSeriesResponse])
@track_request_time(endpoint="get_similar_series")
@cache_response(ttl=1800, vary_by=["series_id", "limit"])
async def get_similar_series(
    series_id: int = Path(..., gt=0, description="ID của series sách"),
    limit: int = Query(5, ge=1, le=20, description="Số lượng series trả về"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """
    Lấy danh sách series sách tương tự.

    - **series_id**: ID của series sách
    - **limit**: Số lượng series trả về
    """
    book_series_service = BookSeriesService(db)

    try:
        # Kiểm tra series có tồn tại không
        series = await book_series_service.get_book_series_by_id(series_id)

        if not series:
            raise NotFoundException(
                detail=f"Không tìm thấy series sách với ID: {series_id}",
                code="series_not_found",
            )

        # Lấy danh sách series tương tự
        similar_series = await book_series_service.get_similar_series(
            series_id=series_id, limit=limit
        )

        # Nếu người dùng đã đăng nhập, đánh dấu series nào đã follow
        if current_user:
            followed_series = await book_series_service.get_followed_series_ids(
                current_user.id
            )

            for series in similar_series:
                series.is_followed = series.id in followed_series

        return similar_series
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy danh sách series sách tương tự {series_id}: {str(e)}"
        )
        raise ServerException(detail="Lỗi khi lấy danh sách series sách tương tự")
