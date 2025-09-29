from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, func
from datetime import datetime, timezone, timedelta

from app.core.db import Base
from app.logs_manager.models.error_log import ErrorLog
from app.logs_manager.schemas.error_log import ErrorLogCreate, ErrorLogFilter


class ErrorLogRepository:
    def create_log(self, db: Session, log_data: ErrorLogCreate) -> ErrorLog:
        """Tạo log lỗi mới từ dữ liệu đầu vào"""
        db_log = ErrorLog(**log_data.model_dump(exclude_unset=True))
        db.add(db_log)
        db.commit()
        db.refresh(db_log)
        return db_log

    def get_by_id(self, db: Session, log_id: int) -> Optional[ErrorLog]:
        """Lấy log lỗi theo ID"""
        return db.query(ErrorLog).filter(ErrorLog.id == log_id).first()

    def get_all(
        self,
        db: Session,
        filters: Optional[ErrorLogFilter] = None,
        skip: int = 0,
        limit: int = 100,
        sort_by: str = "timestamp",
        sort_desc: bool = True,
    ) -> Dict[str, Any]:
        """Lấy danh sách log lỗi với các bộ lọc và phân trang"""
        query = db.query(ErrorLog)

        # Áp dụng filters
        if filters:
            if filters.error_level:
                query = query.filter(ErrorLog.error_type == filters.error_level)

            if filters.error_code:
                query = query.filter(ErrorLog.error_code == filters.error_code)

            if filters.source:
                query = query.filter(ErrorLog.component == filters.source)

            if filters.user_id is not None:
                query = query.filter(ErrorLog.user_id == filters.user_id)

            if filters.start_date:
                query = query.filter(ErrorLog.timestamp >= filters.start_date)

            if filters.end_date:
                query = query.filter(ErrorLog.timestamp <= filters.end_date)

        # Tính tổng số bản ghi
        total = query.count()

        # Áp dụng sắp xếp
        if sort_by:
            column = getattr(ErrorLog, sort_by, ErrorLog.timestamp)
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
        error_level: Optional[str] = None,
        error_code: Optional[str] = None,
        source: Optional[str] = None,
        user_id: Optional[int] = None,
        admin_id: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> int:
        """
        Count error logs with optional filtering
        """
        query = db.query(func.count(ErrorLog.id))

        # Apply filters
        if error_level:
            query = query.filter(ErrorLog.error_level == error_level)
        if error_code:
            query = query.filter(ErrorLog.error_code == error_code)
        if source:
            query = query.filter(ErrorLog.source == source)
        if user_id is not None:
            query = query.filter(ErrorLog.user_id == user_id)
        if admin_id is not None:
            query = query.filter(ErrorLog.admin_id == admin_id)
        if start_date:
            query = query.filter(ErrorLog.created_at >= start_date)
        if end_date:
            query = query.filter(ErrorLog.created_at <= end_date)

        return query.scalar() or 0

    @staticmethod
    def update(
        db: Session, log_id: int, log_data: Dict[str, Any]
    ) -> Optional[ErrorLog]:
        """
        Update an error log
        """
        db_log = ErrorLogRepository.get_by_id(db, log_id)
        if db_log:
            for key, value in log_data.items():
                setattr(db_log, key, value)
            db.commit()
            db.refresh(db_log)
        return db_log

    @staticmethod
    def delete(db: Session, log_id: int) -> bool:
        """
        Delete an error log
        """
        db_log = ErrorLogRepository.get_by_id(db, log_id)
        if db_log:
            db.delete(db_log)
            db.commit()
            return True
        return False

    @staticmethod
    def delete_old_logs(db: Session, days: int = 90) -> int:
        """
        Delete logs older than specified days
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        result = (
            db.query(ErrorLog)
            .filter(ErrorLog.created_at < cutoff_date)
            .delete(synchronize_session=False)
        )
        db.commit()
        return result
