from typing import Optional, List, Dict, Any
from fastapi import (
    APIRouter,
    Depends,
    Query,
    HTTPException,
    status,
    Request,
    Body,
    Path,
)
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
from pathlib import Path as PathLib
from app.user_site.api.v1 import throttle_requests

from app.common.db.session import get_db
from app.user_site.api.deps import get_current_active_user, get_current_user
from app.user_site.models.user import User
from app.user_site.schemas.recommendation import (
    RecommendationListResponse,
    RecommendationEngineResponse,
    RecommendationSourceType,
    RecommendationPreferences,
    RecommendationFeedbackRequest,
    RecommendationExploreResponse,
    RecommendationCollectionResponse,
    RecommendationInsightResponse,
    RecommendationResponse,
    RecommendationHistoryResponse,
    RecommendationFeedbackCreate,
    RecommendationTypeEnum,
    RecommendationFilterParams,
    PersonalizedRecommendationResponse,
)
from app.user_site.services.recommendation_service import RecommendationService
from app.user_site.services.preference_service import PreferenceService
from app.logging.setup import get_logger
from app.monitoring.metrics import track_request_time, increment_counter
from app.cache.decorators import cache_response, invalidate_cache
from app.core.exceptions import (
    NotFoundException,
    BadRequestException,
    RateLimitExceededException,
    ServiceUnavailableException,
)
from app.performance.performance import query_performance_tracker
from app.security.audit.audit_trails import AuditLogger

router = APIRouter()
logger = get_logger("recommendation_api")
audit_logger = AuditLogger()


@router.get("", response_model=RecommendationListResponse)
@track_request_time(endpoint="get_recommendations")
@cache_response(
    ttl=3600,
    vary_by=[
        "user_id",
        "type",
        "category_id",
        "min_rating",
        "age_group",
        "skip",
        "limit",
    ],
)
async def get_recommendations(
    type: Optional[RecommendationTypeEnum] = Query(None, description="Loại đề xuất"),
    category_id: Optional[int] = Query(None, gt=0, description="ID của danh mục sách"),
    min_rating: Optional[float] = Query(
        None, ge=0, le=5, description="Đánh giá tối thiểu"
    ),
    age_group: Optional[str] = Query(
        None, description="Nhóm tuổi (vd: '6-12', '13-17', '18+'"
    ),
    skip: int = Query(0, ge=0, description="Số lượng bản ghi bỏ qua"),
    limit: int = Query(20, ge=1, le=100, description="Số lượng bản ghi lấy"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """
    Lấy danh sách đề xuất sách dựa trên các tiêu chí khác nhau.

    - Hỗ trợ lọc theo loại đề xuất, danh mục, đánh giá và nhóm tuổi
    - Phân trang với skip/limit
    - Có thể sử dụng với hoặc không có xác thực người dùng
    """
    recommendation_service = RecommendationService(db)
    user_id = current_user.id if current_user else None

    try:
        filters = RecommendationFilterParams(
            type=type,
            category_id=category_id,
            min_rating=min_rating,
            age_group=age_group,
        )

        recommendations, total = await recommendation_service.get_recommendations(
            user_id=user_id, filters=filters, skip=skip, limit=limit
        )

        return {"items": recommendations, "total": total}
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách đề xuất: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy danh sách đề xuất",
        )


@router.get("/personalized", response_model=PersonalizedRecommendationResponse)
@track_request_time(endpoint="get_personalized_recommendations")
@throttle_requests(max_requests=20, per_seconds=3600)
async def get_personalized_recommendations(
    refresh: bool = Query(False, description="Làm mới đề xuất thay vì sử dụng cache"),
    limit: int = Query(20, ge=1, le=50, description="Số lượng đề xuất trả về"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Lấy đề xuất sách được cá nhân hóa cho người dùng.

    - Dựa trên lịch sử đọc, đánh giá, danh mục ưa thích của người dùng
    - Sử dụng học máy để tạo đề xuất chính xác hơn
    - Tuỳ chọn làm mới đề xuất hoặc sử dụng cache
    """
    recommendation_service = RecommendationService(db)
    preferences_service = PreferenceService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Lấy đề xuất cá nhân hóa - User: {current_user.id}, Refresh: {refresh}, IP: {client_ip}"
    )

    try:
        # Nếu yêu cầu làm mới, xóa cache đề xuất hiện tại
        if refresh:
            await invalidate_cache(f"personalized_recommendations:{current_user.id}")

        # Lấy thông tin sở thích người dùng
        user_preferences = await preferences_service.get_user_preferences(
            current_user.id
        )

        # Lấy đề xuất cá nhân hóa
        recommendations = await recommendation_service.get_personalized_recommendations(
            user_id=current_user.id, preferences=user_preferences, limit=limit
        )

        # Ghi lại lịch sử đề xuất
        await recommendation_service.log_recommendation_history(
            user_id=current_user.id,
            recommendation_ids=[rec.id for rec in recommendations.books],
            timestamp=datetime.now(timezone.utc),
        )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "view_personalized_recommendations",
            f"Người dùng đã xem đề xuất cá nhân hóa",
            metadata={
                "user_id": current_user.id,
                "refresh": refresh,
                "recommendation_count": len(recommendations.books),
            },
        )

        return recommendations
    except ServiceUnavailableException:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dịch vụ đề xuất tạm thời không khả dụng",
        )
    except Exception as e:
        logger.error(f"Lỗi khi lấy đề xuất cá nhân hóa: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy đề xuất cá nhân hóa",
        )


@router.post("/{recommendation_id}/feedback", status_code=status.HTTP_201_CREATED)
@track_request_time(endpoint="create_recommendation_feedback")
@throttle_requests(max_requests=50, per_seconds=3600)
async def create_recommendation_feedback(
    feedback: RecommendationFeedbackCreate,
    recommendation_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    request: Request = None,
):
    """
    Gửi phản hồi về một đề xuất.

    - Cho phép người dùng đánh giá chất lượng của đề xuất
    - Sử dụng phản hồi để cải thiện hệ thống đề xuất trong tương lai
    - Giới hạn tốc độ gửi phản hồi để tránh lạm dụng
    """
    recommendation_service = RecommendationService(db)

    client_ip = request.client.host if request and request.client else "unknown"
    logger.info(
        f"Phản hồi đề xuất - ID: {recommendation_id}, User: {current_user.id}, Rating: {feedback.rating}, IP: {client_ip}"
    )

    try:
        # Kiểm tra đề xuất có tồn tại không
        recommendation = await recommendation_service.get_recommendation_by_id(
            recommendation_id
        )

        if not recommendation:
            raise NotFoundException(
                detail=f"Không tìm thấy đề xuất với ID: {recommendation_id}"
            )

        result = await recommendation_service.create_feedback(
            user_id=current_user.id,
            recommendation_id=recommendation_id,
            rating=feedback.rating,
            comment=feedback.comment,
            is_relevant=feedback.is_relevant,
        )

        # Ghi nhật ký audit
        audit_logger.log_activity(
            current_user.id,
            "recommendation_feedback",
            f"Người dùng đã gửi phản hồi cho đề xuất {recommendation_id}",
            metadata={
                "user_id": current_user.id,
                "recommendation_id": recommendation_id,
                "rating": feedback.rating,
                "is_relevant": feedback.is_relevant,
            },
        )

        # Nếu đánh giá thấp, làm mới đề xuất cho người dùng này
        if feedback.rating < 3 or not feedback.is_relevant:
            await invalidate_cache(f"personalized_recommendations:{current_user.id}")

        return {"success": True, "feedback_id": result["feedback_id"]}
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi gửi phản hồi đề xuất {recommendation_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi gửi phản hồi đề xuất",
        )


@router.get("/history", response_model=RecommendationHistoryResponse)
@track_request_time(endpoint="get_recommendation_history")
async def get_recommendation_history(
    from_date: Optional[datetime] = Query(None, description="Lấy từ ngày"),
    to_date: Optional[datetime] = Query(None, description="Lấy đến ngày"),
    skip: int = Query(0, ge=0, description="Số lượng bản ghi bỏ qua"),
    limit: int = Query(20, ge=1, le=100, description="Số lượng bản ghi lấy"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy lịch sử đề xuất của người dùng.

    - Lọc theo khoảng thời gian
    - Phân trang với skip/limit
    - Chỉ hiển thị đề xuất cho người dùng hiện tại
    """
    recommendation_service = RecommendationService(db)

    try:
        history, total = await recommendation_service.get_recommendation_history(
            user_id=current_user.id,
            from_date=from_date,
            to_date=to_date,
            skip=skip,
            limit=limit,
        )

        return {"items": history, "total": total}
    except Exception as e:
        logger.error(f"Lỗi khi lấy lịch sử đề xuất: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy lịch sử đề xuất",
        )


@router.get("/books/{book_id}/similar", response_model=List[RecommendationResponse])
@track_request_time(endpoint="get_similar_books")
@cache_response(ttl=86400, vary_by=["book_id", "limit"])
async def get_similar_books(
    book_id: int = Path(..., gt=0, description="ID của sách"),
    limit: int = Query(10, ge=1, le=50, description="Số lượng đề xuất trả về"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách sách tương tự với một sách cụ thể.

    - Dựa trên nội dung, thể loại, tác giả và xu hướng đọc từ người dùng khác
    - Không yêu cầu xác thực người dùng
    - Kết quả được lưu cache để tăng hiệu suất
    """
    recommendation_service = RecommendationService(db)

    try:
        similar_books = await recommendation_service.get_similar_books(
            book_id=book_id, limit=limit
        )

        return similar_books
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Lỗi khi lấy sách tương tự với sách {book_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy sách tương tự",
        )


@router.get("/trending", response_model=List[RecommendationResponse])
@track_request_time(endpoint="get_trending_books")
@cache_response(ttl=3600)
async def get_trending_books(
    time_period: str = Query(
        "day", description="Khoảng thời gian ('day', 'week', 'month')"
    ),
    category_id: Optional[int] = Query(None, gt=0, description="ID của danh mục sách"),
    limit: int = Query(10, ge=1, le=50, description="Số lượng đề xuất trả về"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách sách thịnh hành.

    - Dựa trên số lượt đọc, đánh giá, và chia sẻ trong khoảng thời gian
    - Có thể lọc theo danh mục
    - Không yêu cầu xác thực người dùng
    """
    recommendation_service = RecommendationService(db)

    try:
        if time_period not in ["day", "week", "month"]:
            raise BadRequestException(
                detail="Khoảng thời gian không hợp lệ. Chỉ hỗ trợ 'day', 'week', 'month'"
            )

        trending_books = await recommendation_service.get_trending_books(
            time_period=time_period, category_id=category_id, limit=limit
        )

        return trending_books
    except BadRequestException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách sách thịnh hành: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy danh sách sách thịnh hành",
        )


@router.get("/engines", response_model=list[RecommendationEngineResponse])
@track_request_time(endpoint="get_recommendation_engines")
@cache_response(ttl=86400)  # Cache 24h
async def get_recommendation_engines(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy danh sách các công cụ đề xuất sẵn có.

    - Caching: Cache kết quả lâu dài vì ít thay đổi
    - UI: Cho phép UI hiển thị các loại đề xuất có sẵn
    """
    recommendation_service = RecommendationService(db)

    try:
        engines = await recommendation_service.get_recommendation_engines()
        return engines
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách công cụ đề xuất: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy danh sách công cụ đề xuất",
        )


@router.get("/for-you/categories", response_model=RecommendationListResponse)
@track_request_time(endpoint="get_category_recommendations")
@cache_response(
    ttl=3600,
    key_prefix="recommendations:categories:{current_user.id}",
    vary_by=["limit"],
)
async def get_category_recommendations(
    limit: int = Query(5, ge=1, le=20, description="Số lượng danh mục trả về"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy danh sách các danh mục được đề xuất cho người dùng dựa trên hành vi đọc.

    - Caching: Cache kết quả với thời gian sống 1 giờ
    - Personalization: Đề xuất được điều chỉnh theo hành vi đọc
    """
    recommendation_service = RecommendationService(db)

    try:
        categories, total = await recommendation_service.get_recommended_categories(
            user_id=current_user.id, limit=limit
        )

        return {"items": categories, "total": total}
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy danh sách danh mục đề xuất cho người dùng {current_user.id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy danh sách danh mục đề xuất",
        )


@router.get("/new-releases", response_model=RecommendationListResponse)
@track_request_time(endpoint="get_new_releases")
@cache_response(ttl=86400, vary_by=["category_id", "days", "limit"])
async def get_new_releases(
    category_id: Optional[int] = Query(None, gt=0, description="ID của danh mục"),
    days: int = Query(30, ge=1, le=90, description="Số ngày gần nhất"),
    limit: int = Query(10, ge=1, le=50, description="Số lượng sách trả về"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách sách mới phát hành.

    - Caching: Cache kết quả với thời gian sống 1 ngày
    - Filtering: Hỗ trợ lọc theo danh mục và khoảng thời gian
    """
    recommendation_service = RecommendationService(db)

    try:
        new_releases, total = await recommendation_service.get_new_releases(
            category_id=category_id, days=days, limit=limit
        )

        return {"items": new_releases, "total": total}
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách sách mới phát hành: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy danh sách sách mới phát hành",
        )


@router.get("/popular-in-location", response_model=RecommendationListResponse)
@track_request_time(endpoint="get_popular_in_location")
@cache_response(ttl=3600, vary_by=["location_id", "limit", "current_user.id"])
async def get_popular_in_location(
    location_id: Optional[str] = Query(None, description="Mã định danh khu vực"),
    limit: int = Query(10, ge=1, le=50, description="Số lượng sách trả về"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """
    Lấy danh sách sách phổ biến trong khu vực địa lý.

    - Geo-based: Đề xuất dựa trên vị trí địa lý
    - Caching: Cache kết quả với thời gian sống 1 giờ
    - Localization: Tự động xác định vị trí nếu không cung cấp
    """
    recommendation_service = RecommendationService(db)

    try:
        # Nếu không có location_id và có người dùng, lấy location từ profile
        if location_id is None and current_user:
            location_id = await recommendation_service.get_user_location(
                current_user.id
            )

        popular_books, total = await recommendation_service.get_popular_in_location(
            location_id=location_id, limit=limit
        )

        return {"items": popular_books, "total": total}
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách sách phổ biến trong khu vực: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy danh sách sách phổ biến trong khu vực",
        )


@router.get("/explore", response_model=RecommendationExploreResponse)
@track_request_time(endpoint="explore_recommendations")
@cache_response(ttl=1800, key_prefix="recommendations:explore:{current_user.id}")
async def explore_recommendations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy kết hợp của nhiều loại đề xuất để khám phá.

    - Trang chủ: Lý tưởng cho trang chủ hoặc trang khám phá
    - Caching: Cache kết quả với thời gian sống 30 phút
    - Diverse: Kết hợp nhiều loại đề xuất khác nhau
    """
    recommendation_service = RecommendationService(db)

    try:
        explore_data = await recommendation_service.get_explore_recommendations(
            user_id=current_user.id
        )

        return explore_data
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy đề xuất khám phá cho người dùng {current_user.id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy đề xuất khám phá",
        )


@router.get("/collections", response_model=List[RecommendationCollectionResponse])
@track_request_time(endpoint="get_recommendation_collections")
@cache_response(ttl=86400, vary_by=["include_books"])
async def get_recommendation_collections(
    include_books: bool = Query(False, description="Bao gồm sách trong mỗi bộ sưu tập"),
    limit_books: int = Query(
        5, ge=1, le=20, description="Số lượng sách tối đa cho mỗi bộ sưu tập"
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Lấy danh sách các bộ sưu tập đề xuất được biên tập.

    - Curated: Các bộ sưu tập được biên tập bởi đội ngũ biên tập
    - Caching: Cache kết quả với thời gian sống 1 ngày
    - Content: Bao gồm "Được giới thiệu", "Giải thưởng", "Xu hướng", v.v.
    """
    recommendation_service = RecommendationService(db)

    try:
        collections = await recommendation_service.get_recommendation_collections(
            include_books=include_books, limit_books=limit_books
        )

        return collections
    except Exception as e:
        logger.error(f"Lỗi khi lấy bộ sưu tập đề xuất: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy bộ sưu tập đề xuất",
        )


@router.get("/insights", response_model=RecommendationInsightResponse)
@track_request_time(endpoint="get_reading_insights")
@cache_response(ttl=86400, key_prefix="recommendations:insights:{current_user.id}")
async def get_reading_insights(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy thông tin chi tiết về thói quen đọc sách và đề xuất cá nhân hóa.

    - Insights: Cung cấp thông tin chi tiết về hành vi đọc
    - Caching: Cache kết quả với thời gian sống 1 ngày
    - Analysis: Phân tích thói quen đọc sách của người dùng
    """
    recommendation_service = RecommendationService(db)

    try:
        insights = await recommendation_service.get_reading_insights(
            user_id=current_user.id
        )

        return insights
    except Exception as e:
        logger.error(
            f"Lỗi khi lấy thông tin chi tiết về đọc sách cho người dùng {current_user.id}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy thông tin chi tiết về đọc sách",
        )


@router.get("/seasonal", response_model=RecommendationListResponse)
@track_request_time(endpoint="get_seasonal_recommendations")
@cache_response(ttl=86400)  # Cache 1 ngày
async def get_seasonal_recommendations(
    limit: int = Query(10, ge=1, le=50, description="Số lượng sách trả về"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """
    Lấy đề xuất sách theo mùa hoặc sự kiện đặc biệt.

    - Seasonal: Sách liên quan đến các mùa, ngày lễ, hoặc sự kiện đặc biệt
    - Caching: Cache kết quả với thời gian sống 1 ngày
    - Automatic: Tự động cập nhật theo mùa và sự kiện hiện tại
    """
    recommendation_service = RecommendationService(db)

    try:
        seasonal_books, total = (
            await recommendation_service.get_seasonal_recommendations(
                limit=limit, current_user_id=current_user.id if current_user else None
            )
        )

        return {"items": seasonal_books, "total": total}
    except Exception as e:
        logger.error(f"Lỗi khi lấy đề xuất sách theo mùa: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đã xảy ra lỗi khi lấy đề xuất sách theo mùa",
        )
