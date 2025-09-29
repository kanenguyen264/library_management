from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Query, HTTPException, status, Request, Body
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
from app.user_site.api.v1 import throttle_requests

from app.common.db.session import get_db
from app.user_site.api.deps import get_current_user
from app.user_site.models.user import User
from app.user_site.schemas.search import (
    SearchResponse,
    SearchAllResponse,
    SearchFilter,
    SearchSuggestionResponse,
    AdvancedSearchParams,
    SearchHistoryResponse,
    SearchHistoryCreate,
)
from app.user_site.services.search_service import SearchService
from app.monitoring.metrics import track_request_time, increment_counter
from app.cache.decorators import cache_response, cache_with_query_hash
from app.security.input_validation.sanitizers import sanitize_search_query
from app.core.exceptions import BadRequestException, RateLimitExceededException
from app.logging.setup import get_logger
from app.performance.performance import query_performance_tracker

router = APIRouter()
logger = get_logger("search_api")


@router.get("/", response_model=SearchResponse)
@track_request_time(endpoint="search")
@throttle_requests(max_requests=30, per_seconds=60)
@cache_response(
    ttl=300,
    vary_by=[
        "query",
        "type",
        "category_id",
        "author_id",
        "publisher_id",
        "min_rating",
        "max_rating",
        "tag_ids",
        "skip",
        "limit",
        "user_id",
    ],
)
async def search(
    query: str = Query(
        ..., min_length=2, max_length=100, description="Từ khóa tìm kiếm"
    ),
    type: Optional[str] = Query(
        None,
        description="Loại tìm kiếm: books, authors, categories, tags, publishers, users, all",
    ),
    category_id: Optional[int] = Query(None, gt=0, description="ID danh mục"),
    author_id: Optional[int] = Query(None, gt=0, description="ID tác giả"),
    publisher_id: Optional[int] = Query(None, gt=0, description="ID nhà xuất bản"),
    min_rating: Optional[float] = Query(
        None, ge=0, le=5, description="Đánh giá tối thiểu"
    ),
    max_rating: Optional[float] = Query(
        None, ge=0, le=5, description="Đánh giá tối đa"
    ),
    tag_ids: Optional[str] = Query(
        None, description="Danh sách ID thẻ, phân cách bởi dấu phẩy"
    ),
    skip: int = Query(0, ge=0, description="Số lượng kết quả bỏ qua"),
    limit: int = Query(20, ge=1, le=100, description="Số lượng kết quả tối đa trả về"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
    request: Request = None,
) -> SearchResponse:
    """
    Tìm kiếm sách, tác giả, danh mục, thẻ, nhà xuất bản, người dùng.

    - Tối ưu hóa: Sử dụng cache cho kết quả tìm kiếm phổ biến
    - Bảo mật: Làm sạch dữ liệu đầu vào, giới hạn độ dài truy vấn
    - Hiệu suất: Theo dõi thời gian xử lý để phát hiện bottleneck
    - Rate limiting: Giới hạn 30 request/phút để ngăn chặn tấn công DoS
    """
    # Làm sạch truy vấn tìm kiếm để tránh SQL injection và XSS
    clean_query = sanitize_search_query(query)

    if clean_query != query:
        logger.warning(f"Potential malicious search query sanitized. Original: {query}")

    # Log search query for analytics
    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(f"Search query: '{clean_query}', Type: {type}, IP: {client_ip}")
    increment_counter("search_queries_total")

    # Lưu lịch sử tìm kiếm nếu người dùng đã đăng nhập
    if current_user:
        await _save_search_history(db, current_user.id, clean_query, type)

    # Chuyển đổi tag_ids từ chuỗi thành list số nguyên
    tag_id_list = None
    if tag_ids:
        try:
            tag_id_list = [int(id.strip()) for id in tag_ids.split(",") if id.strip()]
        except ValueError:
            raise BadRequestException(
                detail="Định dạng tag_ids không hợp lệ. Vui lòng sử dụng danh sách ID phân cách bởi dấu phẩy."
            )

    # Khởi tạo dịch vụ tìm kiếm
    search_service = SearchService(db)

    # Lấy ID người dùng hiện tại nếu có
    user_id = current_user.id if current_user else None

    # Sử dụng performance tracking
    with query_performance_tracker("search", {"query": clean_query, "type": type}):
        # Xử lý các loại tìm kiếm khác nhau
        try:
            if type == "books" or type is None:
                return await search_service.search_books(
                    query=clean_query,
                    category_id=category_id,
                    author_id=author_id,
                    publisher_id=publisher_id,
                    min_rating=min_rating,
                    max_rating=max_rating,
                    tag_ids=tag_id_list,
                    skip=skip,
                    limit=limit,
                    user_id=user_id,
                )
            elif type == "authors":
                return await search_service.search_authors(
                    query=clean_query, skip=skip, limit=limit
                )
            elif type == "categories":
                return await search_service.search_categories(
                    query=clean_query, skip=skip, limit=limit
                )
            elif type == "tags":
                return await search_service.search_tags(
                    query=clean_query, skip=skip, limit=limit
                )
            elif type == "publishers":
                return await search_service.search_publishers(
                    query=clean_query, skip=skip, limit=limit
                )
            elif type == "users":
                # Chỉ cho phép tìm kiếm người dùng nếu đã đăng nhập
                if not user_id:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Bạn cần đăng nhập để tìm kiếm người dùng",
                    )
                return await search_service.search_users(
                    query=clean_query, skip=skip, limit=limit
                )
            elif type == "all":
                return await search_service.search_all(query=clean_query, limit=limit)
            else:
                raise BadRequestException(detail=f"Loại tìm kiếm '{type}' không hợp lệ")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Search error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Đã xảy ra lỗi trong quá trình tìm kiếm",
            )


@router.post("/advanced", response_model=SearchResponse)
@track_request_time(endpoint="advanced_search")
@throttle_requests(max_requests=15, per_seconds=60)
@cache_with_query_hash(ttl=300)
async def advanced_search(
    params: AdvancedSearchParams = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
    request: Request = None,
) -> SearchResponse:
    """
    Tìm kiếm nâng cao với nhiều tùy chọn và bộ lọc phức tạp.

    - Hỗ trợ nhiều tiêu chí tìm kiếm cùng lúc
    - Tìm kiếm theo khoảng thời gian, đánh giá
    - Hỗ trợ sắp xếp và phân trang
    - Rate limiting: Giới hạn 15 request/phút vì đây là tìm kiếm nặng
    """
    search_service = SearchService(db)

    # Làm sạch chuỗi tìm kiếm
    if params.query:
        params.query = sanitize_search_query(params.query)

    # Log tìm kiếm nâng cao
    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(f"Advanced search: {params.model_dump()}, IP: {client_ip}")
    increment_counter("advanced_search_queries_total")

    # Lưu lịch sử tìm kiếm nếu người dùng đã đăng nhập
    if current_user and params.query:
        await _save_search_history(db, current_user.id, params.query, "advanced")

    # Thêm user_id cho tìm kiếm cá nhân hóa
    user_id = current_user.id if current_user else None

    try:
        results = await search_service.advanced_search(params=params, user_id=user_id)
        return results
    except Exception as e:
        logger.error(f"Advanced search error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi trong quá trình tìm kiếm nâng cao",
        )


@router.get("/suggestions", response_model=SearchSuggestionResponse)
@track_request_time(endpoint="search_suggestions")
@throttle_requests(max_requests=50, per_seconds=60)
@cache_response(ttl=300, vary_by=["query"])
async def get_search_suggestions(
    query: str = Query(
        ..., min_length=2, max_length=100, description="Từ khóa tìm kiếm"
    ),
    limit: int = Query(10, ge=1, le=20, description="Số lượng gợi ý trả về"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
) -> SearchSuggestionResponse:
    """
    Lấy gợi ý tìm kiếm dựa trên từ khóa.

    - Tối ưu hóa: Cache kết quả gợi ý phổ biến
    - Bảo mật: Làm sạch dữ liệu đầu vào
    - Hiệu suất: Giới hạn số lượng gợi ý trả về
    - Rate limiting: Giới hạn 50 request/phút do đây là API gọi thường xuyên
    """
    # Làm sạch truy vấn
    clean_query = sanitize_search_query(query)

    # Khởi tạo dịch vụ tìm kiếm
    search_service = SearchService(db)

    # Cá nhân hóa gợi ý nếu có user_id
    user_id = current_user.id if current_user else None

    try:
        # Lấy gợi ý tìm kiếm
        return await search_service.get_search_suggestions(
            query=clean_query, limit=limit, user_id=user_id
        )
    except Exception as e:
        logger.error(f"Search suggestion error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy gợi ý tìm kiếm",
        )


@router.get("/filters", response_model=List[SearchFilter])
@track_request_time(endpoint="search_filters")
@cache_response(ttl=3600)  # Cache 1 giờ vì dữ liệu này ít thay đổi
async def get_advanced_search_filters(
    type: str = Query(
        ...,
        description="Loại bộ lọc: categories, authors, publishers, tags, ratings, years",
    ),
    db: AsyncSession = Depends(get_db),
) -> List[SearchFilter]:
    """
    Lấy danh sách các bộ lọc cho tìm kiếm nâng cao.

    - Tối ưu hóa: Cache kết quả lâu hơn vì dữ liệu ít thay đổi
    - Hỗ trợ nhiều loại bộ lọc khác nhau
    """
    # Khởi tạo dịch vụ tìm kiếm
    search_service = SearchService(db)

    try:
        # Lấy các bộ lọc tìm kiếm
        return await search_service.get_search_filters(filter_type=type)
    except Exception as e:
        logger.error(f"Get search filters error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy bộ lọc tìm kiếm",
        )


@router.get("/popular", response_model=List[str])
@track_request_time(endpoint="popular_searches")
@cache_response(ttl=1800)  # Cache 30 phút
async def get_popular_searches(
    limit: int = Query(10, ge=1, le=50, description="Số lượng từ khóa phổ biến trả về"),
    days: int = Query(7, ge=1, le=30, description="Khoảng thời gian (ngày)"),
    db: AsyncSession = Depends(get_db),
) -> List[str]:
    """
    Lấy danh sách từ khóa tìm kiếm phổ biến trong khoảng thời gian gần đây.

    - Giúp người dùng khám phá nội dung phổ biến
    - Thống kê dựa trên dữ liệu thực tế
    """
    search_service = SearchService(db)

    try:
        return await search_service.get_popular_searches(limit=limit, days=days)
    except Exception as e:
        logger.error(f"Get popular searches error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy từ khóa tìm kiếm phổ biến",
        )


@router.get("/history", response_model=List[SearchHistoryResponse])
@track_request_time(endpoint="search_history")
async def get_search_history(
    limit: int = Query(
        20, ge=1, le=100, description="Số lượng lịch sử tìm kiếm trả về"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[SearchHistoryResponse]:
    """
    Lấy lịch sử tìm kiếm của người dùng hiện tại.

    - Chỉ người dùng đã đăng nhập mới có thể xem lịch sử tìm kiếm của họ
    - Hỗ trợ giới hạn số lượng kết quả
    """
    search_service = SearchService(db)

    try:
        return await search_service.get_user_search_history(
            user_id=current_user.id, limit=limit
        )
    except Exception as e:
        logger.error(f"Get search history error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy lịch sử tìm kiếm",
        )


@router.delete("/history", status_code=status.HTTP_204_NO_CONTENT)
@track_request_time(endpoint="clear_search_history")
async def clear_search_history(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """
    Xóa toàn bộ lịch sử tìm kiếm của người dùng hiện tại.

    - Quyền riêng tư: Cho phép người dùng xóa lịch sử của họ
    """
    search_service = SearchService(db)

    try:
        await search_service.clear_user_search_history(current_user.id)
    except Exception as e:
        logger.error(f"Clear search history error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi xóa lịch sử tìm kiếm",
        )


@router.get("/trending", response_model=Dict[str, List[Any]])
@track_request_time(endpoint="trending_content")
@cache_response(ttl=1800)  # Cache 30 phút
async def get_trending_content(
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
) -> Dict[str, List[Any]]:
    """
    Lấy nội dung thịnh hành dựa trên dữ liệu tìm kiếm và hoạt động của người dùng.

    - Tổng hợp từ nhiều nguồn dữ liệu
    - Cung cấp đề xuất khám phá cho người dùng
    """
    search_service = SearchService(db)

    # Cá nhân hóa nếu có người dùng
    user_id = current_user.id if current_user else None

    try:
        trending = await search_service.get_trending_content(user_id=user_id)
        return trending
    except Exception as e:
        logger.error(f"Get trending content error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy nội dung thịnh hành",
        )


async def _save_search_history(
    db: AsyncSession, user_id: int, query: str, search_type: str
):
    """Hàm phụ trợ để lưu lịch sử tìm kiếm của người dùng"""
    try:
        search_service = SearchService(db)
        history_data = {
            "user_id": user_id,
            "query": query,
            "search_type": search_type,
            "created_at": datetime.now(timezone.utc),
        }
        await search_service.save_search_history(SearchHistoryCreate(**history_data))
    except Exception as e:
        # Chỉ log lỗi, không dừng luồng chính
        logger.error(f"Failed to save search history: {str(e)}")
