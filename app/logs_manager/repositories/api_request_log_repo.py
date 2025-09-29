from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, func, and_
from datetime import datetime, timezone, timedelta

from app.core.db import Base
from app.logs_manager.models.api_request_log import ApiRequestLog
from app.logs_manager.schemas.api_request_log import (
    ApiRequestLogCreate,
    ApiRequestLogFilter,
)


class ApiRequestLogRepository:
    """Repository cho logs của API request"""

    def create_log(self, db: Session, log_data: ApiRequestLogCreate) -> ApiRequestLog:
        """Tạo log request API mới từ dữ liệu đầu vào"""
        db_log = ApiRequestLog(**log_data.model_dump(exclude_unset=True))
        db.add(db_log)
        db.commit()
        db.refresh(db_log)
        return db_log

    def get_by_id(self, db: Session, log_id: int) -> Optional[ApiRequestLog]:
        """Lấy log request API theo ID"""
        return db.query(ApiRequestLog).filter(ApiRequestLog.id == log_id).first()

    def get_all(
        self,
        db: Session,
        filters: Optional[ApiRequestLogFilter] = None,
        skip: int = 0,
        limit: int = 100,
        sort_by: str = "timestamp",
        sort_desc: bool = True,
    ) -> Dict[str, Any]:
        """Lấy danh sách log request API với các bộ lọc và phân trang"""
        query = db.query(ApiRequestLog)

        # Áp dụng filters
        if filters:
            if filters.endpoint:
                query = query.filter(
                    ApiRequestLog.endpoint.like(f"%{filters.endpoint}%")
                )

            if filters.method:
                query = query.filter(ApiRequestLog.method == filters.method)

            if filters.status_code is not None:
                query = query.filter(ApiRequestLog.status_code == filters.status_code)

            if filters.user_id is not None:
                query = query.filter(ApiRequestLog.user_id == filters.user_id)

            if filters.start_date:
                query = query.filter(ApiRequestLog.timestamp >= filters.start_date)

            if filters.end_date:
                query = query.filter(ApiRequestLog.timestamp <= filters.end_date)

        # Tính tổng số bản ghi
        total = query.count()

        # Áp dụng sắp xếp
        if sort_by:
            column = getattr(ApiRequestLog, sort_by, ApiRequestLog.timestamp)
            if sort_desc:
                query = query.order_by(desc(column))
            else:
                query = query.order_by(asc(column))

        # Áp dụng phân trang
        query = query.offset(skip).limit(limit)

        # Lấy kết quả
        items = query.all()

        # Tính số trang
        pages = (total + limit - 1) // limit if limit > 0 else 1
        page = (skip // limit) + 1 if limit > 0 else 1

        return {
            "items": items,
            "total": total,
            "page": page,
            "size": limit,
            "pages": pages,
        }

    @staticmethod
    def count(
        db: Session,
        endpoint: Optional[str] = None,
        method: Optional[str] = None,
        status_code: Optional[int] = None,
        min_status_code: Optional[int] = None,
        max_status_code: Optional[int] = None,
        user_id: Optional[int] = None,
        admin_id: Optional[int] = None,
        client_ip: Optional[str] = None,
        min_duration: Optional[float] = None,
        max_duration: Optional[float] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> int:
        """
        Count API request logs with optional filtering

        Args:
            db: Database session
            endpoint: Filter by API endpoint
            method: Filter by HTTP method
            status_code: Filter by status code
            min_status_code: Filter by minimum status code
            max_status_code: Filter by maximum status code
            user_id: Filter by user ID
            admin_id: Filter by admin ID
            client_ip: Filter by client IP address
            min_duration: Minimum request duration in ms
            max_duration: Maximum request duration in ms
            start_date: Filter by start date
            end_date: Filter by end date

        Returns:
            Count of API request logs
        """
        query = db.query(func.count(ApiRequestLog.id))

        # Apply filters
        if endpoint:
            query = query.filter(ApiRequestLog.endpoint.like(f"%{endpoint}%"))
        if method:
            query = query.filter(ApiRequestLog.method == method)
        if status_code:
            query = query.filter(ApiRequestLog.status_code == status_code)
        if min_status_code:
            query = query.filter(ApiRequestLog.status_code >= min_status_code)
        if max_status_code:
            query = query.filter(ApiRequestLog.status_code <= max_status_code)
        if user_id:
            query = query.filter(ApiRequestLog.user_id == user_id)
        if admin_id:
            query = query.filter(ApiRequestLog.admin_id == admin_id)
        if client_ip:
            query = query.filter(ApiRequestLog.client_ip == client_ip)
        if min_duration is not None:
            query = query.filter(ApiRequestLog.duration_ms >= min_duration)
        if max_duration is not None:
            query = query.filter(ApiRequestLog.duration_ms <= max_duration)
        if start_date:
            query = query.filter(ApiRequestLog.timestamp >= start_date)
        if end_date:
            query = query.filter(ApiRequestLog.timestamp <= end_date)

        return query.scalar() or 0

    @staticmethod
    def update(
        db: Session, log_id: int, update_data: Dict[str, Any]
    ) -> Optional[ApiRequestLog]:
        """
        Update API request log

        Args:
            db: Database session
            log_id: ID of the log entry
            update_data: Updated data

        Returns:
            Updated API request log if found, None otherwise
        """
        db_log = ApiRequestLogRepository.get_by_id(db, log_id)
        if db_log:
            for key, value in update_data.items():
                if hasattr(db_log, key):
                    setattr(db_log, key, value)
            db.commit()
            db.refresh(db_log)
        return db_log

    @staticmethod
    def delete(db: Session, log_id: int) -> bool:
        """
        Delete API request log by ID

        Args:
            db: Database session
            log_id: ID of the log entry

        Returns:
            True if log was deleted, False otherwise
        """
        db_log = ApiRequestLogRepository.get_by_id(db, log_id)
        if db_log:
            db.delete(db_log)
            db.commit()
            return True
        return False

    @staticmethod
    def delete_old_logs(db: Session, days: int = 90) -> int:
        """
        Delete logs older than the specified number of days

        Args:
            db: Database session
            days: Number of days to keep logs for

        Returns:
            Number of logs deleted
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        deleted_count = (
            db.query(ApiRequestLog)
            .filter(ApiRequestLog.timestamp < cutoff_date)
            .delete(synchronize_session=False)
        )
        db.commit()
        return deleted_count

    @staticmethod
    def get_endpoint_stats(
        db: Session,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Get statistics for each API endpoint

        Args:
            db: Database session
            start_date: Filter by start date
            end_date: Filter by end date
            limit: Maximum number of endpoints to return

        Returns:
            List of dictionaries with endpoint statistics
        """
        # Prepare query filters
        filters = []
        if start_date:
            filters.append(ApiRequestLog.timestamp >= start_date)
        if end_date:
            filters.append(ApiRequestLog.timestamp <= end_date)

        # Query for endpoint stats
        query = db.query(
            ApiRequestLog.endpoint,
            func.count(ApiRequestLog.id).label("request_count"),
            func.avg(ApiRequestLog.duration_ms).label("avg_duration_ms"),
            func.min(ApiRequestLog.duration_ms).label("min_duration_ms"),
            func.max(ApiRequestLog.duration_ms).label("max_duration_ms"),
            func.sum(func.case([(ApiRequestLog.status_code >= 400, 1)], else_=0)).label(
                "error_count"
            ),
        )

        # Apply filters
        if filters:
            query = query.filter(and_(*filters))

        # Group by endpoint and get top results
        query = query.group_by(ApiRequestLog.endpoint)
        query = query.order_by(desc("request_count"))
        query = query.limit(limit)

        # Convert to list of dictionaries
        result = []
        for row in query.all():
            result.append(
                {
                    "endpoint": row.endpoint,
                    "request_count": row.request_count,
                    "avg_duration_ms": (
                        float(row.avg_duration_ms) if row.avg_duration_ms else 0
                    ),
                    "min_duration_ms": (
                        float(row.min_duration_ms) if row.min_duration_ms else 0
                    ),
                    "max_duration_ms": (
                        float(row.max_duration_ms) if row.max_duration_ms else 0
                    ),
                    "error_count": row.error_count,
                    "error_rate": (
                        (row.error_count / row.request_count)
                        if row.request_count > 0
                        else 0
                    ),
                }
            )

        return result
