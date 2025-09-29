from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
import logging

from app.logs_manager.repositories.search_log_repo import SearchLogRepository
from app.logs_manager.schemas.search_log import (
    SearchLogCreate,
    SearchLog,
    SearchLogList,
)
from app.core.exceptions import NotFoundException, BadRequestException

logger = logging.getLogger(__name__)


def create_search_log(db: Session, log_data: SearchLogCreate) -> SearchLog:
    """
    Create a new search log entry

    Args:
        db: Database session
        log_data: Search log data

    Returns:
        Created search log
    """
    try:
        log_dict = log_data.model_dump()
        db_log = SearchLogRepository.create(db, log_dict)
        return SearchLog.model_validate(db_log)
    except Exception as e:
        logger.error(f"Error creating search log: {str(e)}")
        raise


def get_search_log(db: Session, log_id: int) -> SearchLog:
    """
    Get search log by ID

    Args:
        db: Database session
        log_id: ID of the log entry

    Returns:
        Search log

    Raises:
        NotFoundException: If log not found
    """
    db_log = SearchLogRepository.get_by_id(db, log_id)
    if not db_log:
        raise NotFoundException(detail=f"Search log with ID {log_id} not found")
    return SearchLog.model_validate(db_log)


def get_search_logs(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    user_id: Optional[int] = None,
    query_term: Optional[str] = None,
    session_id: Optional[str] = None,
    min_results: Optional[int] = None,
    max_results: Optional[int] = None,
    has_clicked_results: Optional[bool] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    sort_by: str = "timestamp",
    sort_desc: bool = True,
) -> SearchLogList:
    """
    Get search logs with optional filtering

    Args:
        db: Database session
        skip: Number of records to skip
        limit: Maximum number of records to return
        user_id: Filter by user ID
        query_term: Filter by search query term
        session_id: Filter by session ID
        min_results: Minimum number of results
        max_results: Maximum number of results
        has_clicked_results: Filter by whether results were clicked
        start_date: Filter by start date
        end_date: Filter by end date
        sort_by: Sort by field
        sort_desc: Sort in descending order if True

    Returns:
        List of search logs
    """
    logs = SearchLogRepository.get_all(
        db=db,
        skip=skip,
        limit=limit,
        user_id=user_id,
        query_term=query_term,
        session_id=session_id,
        min_results=min_results,
        max_results=max_results,
        has_clicked_results=has_clicked_results,
        start_date=start_date,
        end_date=end_date,
        sort_by=sort_by,
        sort_desc=sort_desc,
    )

    total = SearchLogRepository.count(
        db=db,
        user_id=user_id,
        query_term=query_term,
        session_id=session_id,
        min_results=min_results,
        max_results=max_results,
        has_clicked_results=has_clicked_results,
        start_date=start_date,
        end_date=end_date,
    )

    # Calculate pagination info
    pages = (total + limit - 1) // limit if limit > 0 else 1
    page = (skip // limit) + 1 if limit > 0 else 1

    # Return in list schema
    return SearchLogList(
        items=[SearchLog.model_validate(log) for log in logs],
        total=total,
        page=page,
        size=limit,
        pages=pages,
    )


def get_user_searches(
    db: Session,
    user_id: int,
    skip: int = 0,
    limit: int = 20,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> SearchLogList:
    """
    Get search logs for a specific user

    Args:
        db: Database session
        user_id: User ID
        skip: Number of records to skip
        limit: Maximum number of records to return
        start_date: Filter by start date
        end_date: Filter by end date

    Returns:
        List of search logs for the user
    """
    if not start_date:
        start_date = datetime.now(timezone.utc) - timedelta(days=30)

    return get_search_logs(
        db=db,
        skip=skip,
        limit=limit,
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        sort_by="timestamp",
        sort_desc=True,
    )


def get_session_searches(
    db: Session, session_id: str, skip: int = 0, limit: int = 20
) -> SearchLogList:
    """
    Get search logs for a specific session

    Args:
        db: Database session
        session_id: Session ID
        skip: Number of records to skip
        limit: Maximum number of records to return

    Returns:
        List of search logs for the session
    """
    return get_search_logs(
        db=db,
        skip=skip,
        limit=limit,
        session_id=session_id,
        sort_by="timestamp",
        sort_desc=True,
    )


def get_popular_search_terms(
    db: Session, days: int = 7, limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Get most popular search terms

    Args:
        db: Database session
        days: Number of days to look back
        limit: Maximum number of terms to return

    Returns:
        List of popular search terms with count
    """
    start_date = datetime.now(timezone.utc) - timedelta(days=days)
    return SearchLogRepository.get_popular_search_terms(
        db, start_date=start_date, limit=limit
    )


def get_zero_results_searches(
    db: Session, days: int = 7, limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Get search terms that returned zero results

    Args:
        db: Database session
        days: Number of days to look back
        limit: Maximum number of terms to return

    Returns:
        List of search terms with zero results
    """
    start_date = datetime.now(timezone.utc) - timedelta(days=days)
    return SearchLogRepository.get_zero_results_searches(
        db, start_date=start_date, limit=limit
    )


def update_clicked_results(
    db: Session, log_id: int, clicked_results: List[str]
) -> SearchLog:
    """
    Update clicked results for a search log

    Args:
        db: Database session
        log_id: ID of the log entry
        clicked_results: List of clicked result IDs or references

    Returns:
        Updated search log

    Raises:
        NotFoundException: If log not found
    """
    db_log = SearchLogRepository.get_by_id(db, log_id)
    if not db_log:
        raise NotFoundException(detail=f"Search log with ID {log_id} not found")

    # Update the log
    update_data = {"clicked_results": clicked_results}
    updated_log = SearchLogRepository.update(db, log_id, update_data)

    return SearchLog.model_validate(updated_log)


def delete_search_log(db: Session, log_id: int) -> bool:
    """
    Delete search log by ID

    Args:
        db: Database session
        log_id: ID of the log entry

    Returns:
        True if log was deleted successfully

    Raises:
        NotFoundException: If log not found
    """
    db_log = SearchLogRepository.get_by_id(db, log_id)
    if not db_log:
        raise NotFoundException(detail=f"Search log with ID {log_id} not found")

    return SearchLogRepository.delete(db, log_id)


def cleanup_old_logs(db: Session, days: int = 90) -> int:
    """
    Delete search logs older than the specified number of days

    Args:
        db: Database session
        days: Number of days to keep logs for

    Returns:
        Number of logs deleted
    """
    return SearchLogRepository.delete_old_logs(db, days)


class SearchLogService:
    """
    Service xử lý nghiệp vụ liên quan đến log tìm kiếm
    """

    def __init__(self):
        self.repository = SearchLogRepository()

    async def log_search(
        self,
        db: Session,
        query: str,
        results_count: int,
        user_id: Optional[int] = None,
        session_id: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        category: Optional[str] = None,
        source: Optional[str] = None,
        search_duration: Optional[float] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> SearchLog:
        """
        Ghi log tìm kiếm

        Args:
            db: Phiên làm việc với database
            query: Từ khóa tìm kiếm
            results_count: Số lượng kết quả
            user_id: ID của người dùng
            session_id: ID phiên làm việc
            filters: Các bộ lọc được áp dụng
            category: Danh mục tìm kiếm
            source: Nguồn tìm kiếm
            search_duration: Thời gian tìm kiếm (ms)
            ip_address: Địa chỉ IP
            user_agent: User agent của người dùng

        Returns:
            Log tìm kiếm đã được tạo
        """
        log_data = SearchLogCreate(
            query=query,
            results_count=results_count,
            user_id=user_id,
            session_id=session_id,
            filters=filters,
            category=category,
            source=source,
            search_duration=search_duration,
            ip_address=ip_address,
            user_agent=user_agent,
            clicked_results=[],
        )

        log_dict = log_data.model_dump()
        db_log = self.repository.create(db, log_dict)
        return SearchLog.model_validate(db_log)

    async def update_search_results_click(
        self, db: Session, log_id: int, clicked_result: str
    ) -> SearchLog:
        """
        Cập nhật thông tin kết quả tìm kiếm được click

        Args:
            db: Phiên làm việc với database
            log_id: ID của log tìm kiếm
            clicked_result: ID hoặc tham chiếu của kết quả được click

        Returns:
            Log tìm kiếm đã được cập nhật

        Raises:
            NotFoundException: Nếu không tìm thấy log tìm kiếm
        """
        db_log = self.repository.get_by_id(db, log_id)
        if not db_log:
            raise NotFoundException(detail=f"Search log with ID {log_id} not found")

        # Get current clicked results and append new one
        current_clicks = db_log.clicked_results or []
        if clicked_result not in current_clicks:
            current_clicks.append(clicked_result)

        # Update the log
        update_data = {"clicked_results": current_clicks}
        updated_log = self.repository.update(db, log_id, update_data)

        return SearchLog.model_validate(updated_log)

    async def get_user_search_history(
        self,
        db: Session,
        user_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> SearchLogList:
        """
        Lấy lịch sử tìm kiếm của người dùng

        Args:
            db: Phiên làm việc với database
            user_id: ID của người dùng
            start_date: Thời gian bắt đầu
            end_date: Thời gian kết thúc
            page: Trang hiện tại
            page_size: Số lượng bản ghi mỗi trang

        Returns:
            Danh sách log tìm kiếm và thông tin phân trang
        """
        if not start_date:
            start_date = datetime.now(timezone.utc) - timedelta(days=30)

        skip = (page - 1) * page_size

        logs = self.repository.get_all(
            db=db,
            skip=skip,
            limit=page_size,
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            sort_by="timestamp",
            sort_desc=True,
        )

        total = self.repository.count(
            db=db,
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
        )

        # Calculate pagination info
        pages = (total + page_size - 1) // page_size if page_size > 0 else 1

        return SearchLogList(
            items=[SearchLog.model_validate(log) for log in logs],
            total=total,
            page=page,
            size=page_size,
            pages=pages,
        )

    async def get_search_analytics(
        self, db: Session, days: int = 30, limit: int = 20
    ) -> Dict[str, Any]:
        """
        Lấy phân tích dữ liệu tìm kiếm

        Args:
            db: Phiên làm việc với database
            days: Số ngày để phân tích
            limit: Số lượng tối đa từ khóa phổ biến

        Returns:
            Dict với dữ liệu phân tích tìm kiếm
        """
        start_date = datetime.now(timezone.utc) - timedelta(days=days)

        popular_terms = self.repository.get_popular_search_terms(
            db, start_date=start_date, limit=limit
        )

        zero_results = self.repository.get_zero_results_searches(
            db, start_date=start_date, limit=limit
        )

        # Calculate average results per search
        average_results = self.repository.get_average_results(db, start_date=start_date)

        return {
            "period_days": days,
            "start_date": start_date,
            "end_date": datetime.now(timezone.utc),
            "popular_terms": popular_terms,
            "zero_results_terms": zero_results,
            "average_results": average_results,
        }
