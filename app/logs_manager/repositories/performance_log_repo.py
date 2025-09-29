from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, func
from datetime import datetime, timezone, timedelta

from app.core.db import Base
from app.logs_manager.models.performance_log import PerformanceLog
from app.logs_manager.schemas.performance_log import (
    PerformanceLogCreate,
    PerformanceLogFilter,
)


class PerformanceLogRepository:
    def create_log(self, db: Session, log_data: PerformanceLogCreate) -> PerformanceLog:
        """Tạo log hiệu suất mới từ dữ liệu đầu vào"""
        db_log = PerformanceLog(**log_data.model_dump(exclude_unset=True))
        db.add(db_log)
        db.commit()
        db.refresh(db_log)
        return db_log

    def get_by_id(self, db: Session, log_id: int) -> Optional[PerformanceLog]:
        """Lấy log hiệu suất theo ID"""
        return db.query(PerformanceLog).filter(PerformanceLog.id == log_id).first()

    def get_all(
        self,
        db: Session,
        filters: Optional[PerformanceLogFilter] = None,
        skip: int = 0,
        limit: int = 100,
        sort_by: str = "timestamp",
        sort_desc: bool = True,
    ) -> Dict[str, Any]:
        """Lấy danh sách log hiệu suất với các bộ lọc và phân trang"""
        query = db.query(PerformanceLog)

        # Áp dụng filters
        if filters:
            if filters.operation_type:
                query = query.filter(
                    PerformanceLog.operation_type == filters.operation_type
                )

            if filters.component:
                query = query.filter(PerformanceLog.component == filters.component)

            if filters.min_duration_ms is not None:
                query = query.filter(
                    PerformanceLog.duration_ms >= filters.min_duration_ms
                )

            if filters.max_duration_ms is not None:
                query = query.filter(
                    PerformanceLog.duration_ms <= filters.max_duration_ms
                )

            if filters.start_date:
                query = query.filter(PerformanceLog.timestamp >= filters.start_date)

            if filters.end_date:
                query = query.filter(PerformanceLog.timestamp <= filters.end_date)

        # Tính tổng số bản ghi
        total = query.count()

        # Áp dụng sắp xếp
        if sort_by:
            column = getattr(PerformanceLog, sort_by, PerformanceLog.timestamp)
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
        request_path: Optional[str] = None,
        method: Optional[str] = None,
        status_code: Optional[int] = None,
        min_response_time: Optional[float] = None,
        max_response_time: Optional[float] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> int:
        """
        Count performance logs with optional filtering
        """
        query = db.query(func.count(PerformanceLog.id))

        # Apply filters
        if request_path:
            query = query.filter(PerformanceLog.request_path.like(f"%{request_path}%"))
        if method:
            query = query.filter(PerformanceLog.method == method)
        if status_code is not None:
            query = query.filter(PerformanceLog.status_code == status_code)
        if min_response_time is not None:
            query = query.filter(PerformanceLog.response_time >= min_response_time)
        if max_response_time is not None:
            query = query.filter(PerformanceLog.response_time <= max_response_time)
        if start_date:
            query = query.filter(PerformanceLog.created_at >= start_date)
        if end_date:
            query = query.filter(PerformanceLog.created_at <= end_date)

        return query.scalar() or 0

    @staticmethod
    def update(
        db: Session, log_id: int, log_data: Dict[str, Any]
    ) -> Optional[PerformanceLog]:
        """
        Update a performance log
        """
        db_log = PerformanceLogRepository.get_by_id(db, log_id)
        if db_log:
            for key, value in log_data.items():
                setattr(db_log, key, value)
            db.commit()
            db.refresh(db_log)
        return db_log

    @staticmethod
    def delete(db: Session, log_id: int) -> bool:
        """
        Delete a performance log
        """
        db_log = PerformanceLogRepository.get_by_id(db, log_id)
        if db_log:
            db.delete(db_log)
            db.commit()
            return True
        return False

    @staticmethod
    def delete_old_logs(db: Session, days: int = 30) -> int:
        """
        Delete logs older than specified days
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        result = (
            db.query(PerformanceLog)
            .filter(PerformanceLog.created_at < cutoff_date)
            .delete(synchronize_session=False)
        )
        db.commit()
        return result

    @staticmethod
    def get_slow_endpoints(
        db: Session, threshold_ms: float = 500, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get endpoints with high average response times
        """
        stats = (
            db.query(
                PerformanceLog.request_path,
                PerformanceLog.method,
                func.avg(PerformanceLog.response_time).label("avg_response_time"),
                func.count(PerformanceLog.id).label("count"),
            )
            .filter(PerformanceLog.response_time >= threshold_ms)
            .group_by(PerformanceLog.request_path, PerformanceLog.method)
            .order_by(desc("avg_response_time"))
            .limit(limit)
            .all()
        )

        return [
            {
                "request_path": path,
                "method": method,
                "avg_response_time": float(avg_time),
                "count": count,
            }
            for path, method, avg_time, count in stats
        ]

    @staticmethod
    def get_performance_stats(db: Session, days: int = 30) -> Dict[str, Any]:
        """
        Get performance statistics
        """
        start_date = datetime.now(timezone.utc) - timedelta(days=days)

        # Overall stats
        overall = (
            db.query(
                func.avg(PerformanceLog.response_time).label("avg_response_time"),
                func.min(PerformanceLog.response_time).label("min_response_time"),
                func.max(PerformanceLog.response_time).label("max_response_time"),
                func.count(PerformanceLog.id).label("count"),
            )
            .filter(PerformanceLog.created_at >= start_date)
            .first()
        )

        # Stats by method
        method_stats = (
            db.query(
                PerformanceLog.method,
                func.avg(PerformanceLog.response_time).label("avg_response_time"),
                func.count(PerformanceLog.id).label("count"),
            )
            .filter(PerformanceLog.created_at >= start_date)
            .group_by(PerformanceLog.method)
            .all()
        )

        # Stats by status code
        status_stats = (
            db.query(
                PerformanceLog.status_code,
                func.avg(PerformanceLog.response_time).label("avg_response_time"),
                func.count(PerformanceLog.id).label("count"),
            )
            .filter(PerformanceLog.created_at >= start_date)
            .group_by(PerformanceLog.status_code)
            .all()
        )

        return {
            "overall": {
                "avg_response_time": (
                    float(overall.avg_response_time) if overall.avg_response_time else 0
                ),
                "min_response_time": (
                    float(overall.min_response_time) if overall.min_response_time else 0
                ),
                "max_response_time": (
                    float(overall.max_response_time) if overall.max_response_time else 0
                ),
                "count": overall.count,
            },
            "method_stats": [
                {
                    "method": method,
                    "avg_response_time": float(avg_time) if avg_time else 0,
                    "count": count,
                }
                for method, avg_time, count in method_stats
            ],
            "status_stats": [
                {
                    "status_code": status,
                    "avg_response_time": float(avg_time) if avg_time else 0,
                    "count": count,
                }
                for status, avg_time, count in status_stats
            ],
        }
