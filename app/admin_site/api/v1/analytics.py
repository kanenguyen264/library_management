from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from app.core.db import get_session
from app.security.access_control.rbac import get_current_admin, check_permission
from app.admin_site.services.analytics_service import AnalyticsService
from app.logging.setup import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("/dashboard", summary="Get dashboard analytics")
async def get_dashboard_analytics(
    current_admin=Depends(get_current_admin),
    db: Session = Depends(get_session),
    period: str = Query(
        "month", description="Time period for analytics: day, week, month, year"
    ),
) -> Dict[str, Any]:
    """
    Get basic analytics for the admin dashboard
    """
    try:
        # Setup time periods
        end_date = datetime.now(timezone.utc)
        if period == "day":
            start_date = end_date - timedelta(days=1)
        elif period == "week":
            start_date = end_date - timedelta(weeks=1)
        elif period == "year":
            start_date = end_date - timedelta(days=365)
        else:  # month is default
            start_date = end_date - timedelta(days=30)

        # Get analytics data
        user_stats = AnalyticsService.get_user_statistics(db, start_date, end_date)
        reading_stats = AnalyticsService.get_reading_statistics(
            db, start_date, end_date
        )
        book_stats = AnalyticsService.get_book_statistics(
            db, None, start_date, end_date
        )

        # Combine all data
        return {
            "period": period,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "user_statistics": user_stats,
            "reading_statistics": reading_stats,
            "book_statistics": book_stats,
            "service_info": AnalyticsService.get_service_info(),
        }
    except Exception as e:
        logger.error(f"Error getting dashboard analytics: {str(e)}")
        raise


@router.get("/users", summary="Get user analytics")
async def get_user_analytics(
    current_admin=Depends(get_current_admin),
    db: Session = Depends(get_session),
    start_date: Optional[datetime] = Query(
        None, description="Start date for analytics"
    ),
    end_date: Optional[datetime] = Query(None, description="End date for analytics"),
) -> Dict[str, Any]:
    """
    Get detailed user analytics
    """
    try:
        # Use provided dates or default to last 30 days
        if not start_date:
            start_date = datetime.now(timezone.utc) - timedelta(days=30)
        if not end_date:
            end_date = datetime.now(timezone.utc)

        # Get user analytics
        user_stats = AnalyticsService.get_user_statistics(db, start_date, end_date)

        return {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "user_statistics": user_stats,
            "service_info": AnalyticsService.get_service_info(),
        }
    except Exception as e:
        logger.error(f"Error getting user analytics: {str(e)}")
        raise


@router.get("/books", summary="Get book analytics")
async def get_book_analytics(
    current_admin=Depends(get_current_admin),
    db: Session = Depends(get_session),
    book_id: Optional[int] = Query(
        None, description="Book ID for specific book analytics"
    ),
    start_date: Optional[datetime] = Query(
        None, description="Start date for analytics"
    ),
    end_date: Optional[datetime] = Query(None, description="End date for analytics"),
) -> Dict[str, Any]:
    """
    Get detailed book analytics
    """
    try:
        # Use provided dates or default to last 30 days
        if not start_date:
            start_date = datetime.now(timezone.utc) - timedelta(days=30)
        if not end_date:
            end_date = datetime.now(timezone.utc)

        # Get book analytics
        book_stats = AnalyticsService.get_book_statistics(
            db, book_id, start_date, end_date
        )

        return {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "book_statistics": book_stats,
            "service_info": AnalyticsService.get_service_info(),
        }
    except Exception as e:
        logger.error(f"Error getting book analytics: {str(e)}")
        raise


@router.get("/reading", summary="Get reading analytics")
async def get_reading_analytics(
    current_admin=Depends(get_current_admin),
    db: Session = Depends(get_session),
    start_date: Optional[datetime] = Query(
        None, description="Start date for analytics"
    ),
    end_date: Optional[datetime] = Query(None, description="End date for analytics"),
) -> Dict[str, Any]:
    """
    Get detailed reading analytics
    """
    try:
        # Use provided dates or default to last 30 days
        if not start_date:
            start_date = datetime.now(timezone.utc) - timedelta(days=30)
        if not end_date:
            end_date = datetime.now(timezone.utc)

        # Get reading analytics
        reading_stats = AnalyticsService.get_reading_statistics(
            db, start_date, end_date
        )

        return {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "reading_statistics": reading_stats,
            "service_info": AnalyticsService.get_service_info(),
        }
    except Exception as e:
        logger.error(f"Error getting reading analytics: {str(e)}")
        raise
