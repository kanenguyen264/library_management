from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, and_, or_
from datetime import datetime, timedelta

from app.core.db import Base
from app.logs_manager.models.system_log import SystemLog
from app.logs_manager.schemas.system_log import SystemLogCreate, SystemLogFilter


class SystemLogRepository:
    def create_log(self, db: Session, log_data: SystemLogCreate) -> SystemLog:
        """Tạo log hệ thống mới từ dữ liệu đầu vào"""
        db_log = SystemLog(**log_data.model_dump(exclude_unset=True))
        db.add(db_log)
        db.commit()
        db.refresh(db_log)
        return db_log

    def bulk_create_logs(
        self, db: Session, logs_data: List[SystemLogCreate]
    ) -> List[SystemLog]:
        """Tạo nhiều log hệ thống cùng lúc để tối ưu hiệu suất"""
        db_logs = [
            SystemLog(**log_data.model_dump(exclude_unset=True)) for log_data in logs_data
        ]
        db.add_all(db_logs)
        db.commit()
        for db_log in db_logs:
            db.refresh(db_log)
        return db_logs

    def get_log_by_id(self, db: Session, log_id: int) -> Optional[SystemLog]:
        """Lấy log hệ thống theo ID"""
        return db.query(SystemLog).filter(SystemLog.id == log_id).first()

    def get_logs(
        self,
        db: Session,
        filters: Optional[SystemLogFilter] = None,
        skip: int = 0,
        limit: int = 100,
        sort_by: str = "timestamp",
        sort_desc: bool = True,
    ) -> Dict[str, Any]:
        """Lấy danh sách log hệ thống với các bộ lọc và phân trang"""
        query = db.query(SystemLog)

        # Áp dụng filters
        if filters:
            if filters.event_type:
                query = query.filter(SystemLog.event_type == filters.event_type)

            if filters.component:
                query = query.filter(SystemLog.component == filters.component)

            if filters.environment:
                query = query.filter(SystemLog.environment == filters.environment)

            if filters.success is not None:
                query = query.filter(SystemLog.success == filters.success)

            if filters.start_date:
                query = query.filter(SystemLog.timestamp >= filters.start_date)

            if filters.end_date:
                query = query.filter(SystemLog.timestamp <= filters.end_date)

        # Tính tổng số bản ghi
        total = query.count()

        # Áp dụng sắp xếp
        if sort_by:
            column = getattr(SystemLog, sort_by, SystemLog.timestamp)
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

    def get_system_events(
        self,
        db: Session,
        event_type: Optional[str] = None,
        component: Optional[str] = None,
        days: int = 7,
    ) -> List[SystemLog]:
        """Lấy các sự kiện hệ thống trong khoảng thời gian"""
        query = db.query(SystemLog)

        if event_type:
            query = query.filter(SystemLog.event_type == event_type)

        if component:
            query = query.filter(SystemLog.component == component)

        start_date = datetime.now() - timedelta(days=days)
        query = query.filter(SystemLog.timestamp >= start_date)

        return query.order_by(desc(SystemLog.timestamp)).all()

    def get_system_stats(
        self, db: Session, days: int = 30, group_by: str = "daily"
    ) -> Dict[str, Any]:
        """Thống kê sự kiện hệ thống theo thời gian"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        if group_by == "daily":
            date_trunc = func.date_trunc("day", SystemLog.timestamp)
        elif group_by == "hourly":
            date_trunc = func.date_trunc("hour", SystemLog.timestamp)
        elif group_by == "weekly":
            date_trunc = func.date_trunc("week", SystemLog.timestamp)
        else:
            date_trunc = func.date_trunc("day", SystemLog.timestamp)

        # Thống kê số lượng sự kiện theo thời gian và trạng thái
        stats_by_time = (
            db.query(
                date_trunc.label("time_period"),
                func.count(SystemLog.id).label("event_count"),
                func.count(func.case([(SystemLog.success == True, 1)])).label(
                    "success_count"
                ),
                func.count(func.case([(SystemLog.success == False, 1)])).label(
                    "failure_count"
                ),
            )
            .filter(SystemLog.timestamp.between(start_date, end_date))
            .group_by(date_trunc)
            .order_by(date_trunc)
            .all()
        )

        # Thống kê theo loại sự kiện
        event_type_stats = (
            db.query(SystemLog.event_type, func.count(SystemLog.id).label("count"))
            .filter(SystemLog.timestamp.between(start_date, end_date))
            .group_by(SystemLog.event_type)
            .order_by(func.count(SystemLog.id).desc())
            .all()
        )

        # Thống kê theo component
        component_stats = (
            db.query(SystemLog.component, func.count(SystemLog.id).label("count"))
            .filter(SystemLog.timestamp.between(start_date, end_date))
            .group_by(SystemLog.component)
            .order_by(func.count(SystemLog.id).desc())
            .all()
        )

        return {
            "time_stats": [
                {
                    "time_period": period.time_period,
                    "event_count": period.event_count,
                    "success_count": period.success_count,
                    "failure_count": period.failure_count,
                }
                for period in stats_by_time
            ],
            "event_type_stats": [
                {"event_type": stat.event_type, "count": stat.count}
                for stat in event_type_stats
            ],
            "component_stats": [
                {"component": stat.component, "count": stat.count}
                for stat in component_stats
            ],
        }

    def delete_log(self, db: Session, log_id: int) -> bool:
        """Xóa log hệ thống theo ID"""
        db_log = db.query(SystemLog).filter(SystemLog.id == log_id).first()
        if not db_log:
            return False

        db.delete(db_log)
        db.commit()
        return True
