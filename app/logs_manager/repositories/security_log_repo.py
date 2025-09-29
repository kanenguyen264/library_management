from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, and_, or_
from datetime import datetime, timedelta

from app.core.db import Base
from app.logs_manager.models.security_log import SecurityLog
from app.logs_manager.schemas.security_log import SecurityLogCreate, SecurityLogFilter


class SecurityLogRepository:
    def create_log(self, db: Session, log_data: SecurityLogCreate) -> SecurityLog:
        """Tạo log bảo mật mới từ dữ liệu đầu vào"""
        db_log = SecurityLog(**log_data.model_dump(exclude_unset=True))
        db.add(db_log)
        db.commit()
        db.refresh(db_log)
        return db_log

    def bulk_create_logs(
        self, db: Session, logs_data: List[SecurityLogCreate]
    ) -> List[SecurityLog]:
        """Tạo nhiều log bảo mật cùng lúc để tối ưu hiệu suất"""
        db_logs = [
            SecurityLog(**log_data.model_dump(exclude_unset=True)) for log_data in logs_data
        ]
        db.add_all(db_logs)
        db.commit()
        for db_log in db_logs:
            db.refresh(db_log)
        return db_logs

    def get_log_by_id(self, db: Session, log_id: int) -> Optional[SecurityLog]:
        """Lấy log bảo mật theo ID"""
        return db.query(SecurityLog).filter(SecurityLog.id == log_id).first()

    def get_logs(
        self,
        db: Session,
        filters: Optional[SecurityLogFilter] = None,
        skip: int = 0,
        limit: int = 100,
        sort_by: str = "timestamp",
        sort_desc: bool = True,
    ) -> Dict[str, Any]:
        """Lấy danh sách log bảo mật với các bộ lọc và phân trang"""
        query = db.query(SecurityLog)

        # Áp dụng filters
        if filters:
            if filters.event_type:
                query = query.filter(SecurityLog.event_type == filters.event_type)

            if filters.severity:
                query = query.filter(SecurityLog.severity == filters.severity)

            if filters.user_id is not None:
                query = query.filter(SecurityLog.user_id == filters.user_id)

            if filters.is_resolved is not None:
                query = query.filter(SecurityLog.is_resolved == filters.is_resolved)

            if filters.start_date:
                query = query.filter(SecurityLog.timestamp >= filters.start_date)

            if filters.end_date:
                query = query.filter(SecurityLog.timestamp <= filters.end_date)

        # Tính tổng số bản ghi
        total = query.count()

        # Áp dụng sắp xếp
        if sort_by:
            column = getattr(SecurityLog, sort_by, SecurityLog.timestamp)
            if sort_desc:
                query = query.order_by(desc(column))
            else:
                query = query.order_by(column)

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

    def update_log(
        self, db: Session, log_id: int, update_data: Dict[str, Any]
    ) -> Optional[SecurityLog]:
        """Cập nhật thông tin log bảo mật"""
        db_log = db.query(SecurityLog).filter(SecurityLog.id == log_id).first()
        if not db_log:
            return None

        for key, value in update_data.items():
            if hasattr(db_log, key):
                setattr(db_log, key, value)

        db.commit()
        db.refresh(db_log)
        return db_log

    def mark_as_resolved(
        self, db: Session, log_id: int, resolution_notes: Optional[str] = None
    ) -> Optional[SecurityLog]:
        """Đánh dấu log bảo mật đã được giải quyết"""
        update_data = {"is_resolved": True, "resolution_notes": resolution_notes}
        return self.update_log(db, log_id, update_data)

    def delete_log(self, db: Session, log_id: int) -> bool:
        """Xóa log bảo mật theo ID"""
        db_log = db.query(SecurityLog).filter(SecurityLog.id == log_id).first()
        if not db_log:
            return False

        db.delete(db_log)
        db.commit()
        return True

    def get_security_stats(
        self,
        db: Session,
        days: int = 30,
        group_by: str = "daily",
    ) -> Dict[str, Any]:
        """Thống kê các sự kiện bảo mật theo thời gian"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        if group_by == "daily":
            date_trunc = func.date_trunc("day", SecurityLog.timestamp)
        elif group_by == "hourly":
            date_trunc = func.date_trunc("hour", SecurityLog.timestamp)
        elif group_by == "weekly":
            date_trunc = func.date_trunc("week", SecurityLog.timestamp)
        else:
            date_trunc = func.date_trunc("day", SecurityLog.timestamp)

        # Thống kê số lượng sự kiện theo thời gian
        stats_by_time = (
            db.query(
                date_trunc.label("time_period"),
                func.count(SecurityLog.id).label("event_count"),
                func.count(func.case([(SecurityLog.severity == "critical", 1)])).label(
                    "critical_count"
                ),
                func.count(func.case([(SecurityLog.severity == "high", 1)])).label(
                    "high_count"
                ),
                func.count(func.case([(SecurityLog.severity == "medium", 1)])).label(
                    "medium_count"
                ),
                func.count(func.case([(SecurityLog.severity == "low", 1)])).label(
                    "low_count"
                ),
            )
            .filter(SecurityLog.timestamp.between(start_date, end_date))
            .group_by(date_trunc)
            .order_by(date_trunc)
            .all()
        )

        # Thống kê theo loại sự kiện
        event_type_stats = (
            db.query(SecurityLog.event_type, func.count(SecurityLog.id).label("count"))
            .filter(SecurityLog.timestamp.between(start_date, end_date))
            .group_by(SecurityLog.event_type)
            .order_by(func.count(SecurityLog.id).desc())
            .all()
        )

        # Thống kê theo mức độ nghiêm trọng
        severity_stats = (
            db.query(SecurityLog.severity, func.count(SecurityLog.id).label("count"))
            .filter(SecurityLog.timestamp.between(start_date, end_date))
            .group_by(SecurityLog.severity)
            .order_by(func.count(SecurityLog.id).desc())
            .all()
        )

        return {
            "time_stats": [
                {
                    "time_period": period.time_period,
                    "event_count": period.event_count,
                    "critical_count": period.critical_count,
                    "high_count": period.high_count,
                    "medium_count": period.medium_count,
                    "low_count": period.low_count,
                }
                for period in stats_by_time
            ],
            "event_type_stats": [
                {"event_type": stat.event_type, "count": stat.count}
                for stat in event_type_stats
            ],
            "severity_stats": [
                {"severity": stat.severity, "count": stat.count}
                for stat in severity_stats
            ],
        }
