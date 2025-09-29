from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, and_, or_
from datetime import datetime, timedelta

from app.core.db import Base
from app.logs_manager.models.audit_log import AuditLog
from app.logs_manager.schemas.audit_log import AuditLogCreate, AuditLogFilter


class AuditLogRepository:
    def create_log(self, db: Session, log_data: AuditLogCreate) -> AuditLog:
        """Tạo log kiểm toán mới từ dữ liệu đầu vào"""
        db_log = AuditLog(**log_data.model_dump(exclude_unset=True))
        db.add(db_log)
        db.commit()
        db.refresh(db_log)
        return db_log

    def bulk_create_logs(
        self, db: Session, logs_data: List[AuditLogCreate]
    ) -> List[AuditLog]:
        """Tạo nhiều log kiểm toán cùng lúc để tối ưu hiệu suất"""
        db_logs = [
            AuditLog(**log_data.model_dump(exclude_unset=True)) for log_data in logs_data
        ]
        db.add_all(db_logs)
        db.commit()
        for db_log in db_logs:
            db.refresh(db_log)
        return db_logs

    def get_log_by_id(self, db: Session, log_id: int) -> Optional[AuditLog]:
        """Lấy log kiểm toán theo ID"""
        return db.query(AuditLog).filter(AuditLog.id == log_id).first()

    def get_logs(
        self,
        db: Session,
        filters: Optional[AuditLogFilter] = None,
        skip: int = 0,
        limit: int = 100,
        sort_by: str = "timestamp",
        sort_desc: bool = True,
    ) -> Dict[str, Any]:
        """Lấy danh sách log kiểm toán với các bộ lọc và phân trang"""
        query = db.query(AuditLog)

        # Áp dụng filters
        if filters:
            if filters.user_id is not None:
                query = query.filter(AuditLog.user_id == filters.user_id)

            if filters.user_type:
                query = query.filter(AuditLog.user_type == filters.user_type)

            if filters.event_type:
                query = query.filter(AuditLog.event_type == filters.event_type)

            if filters.resource_type:
                query = query.filter(AuditLog.resource_type == filters.resource_type)

            if filters.resource_id:
                query = query.filter(AuditLog.resource_id == filters.resource_id)

            if filters.action:
                query = query.filter(AuditLog.action == filters.action)

            if filters.start_date:
                query = query.filter(AuditLog.timestamp >= filters.start_date)

            if filters.end_date:
                query = query.filter(AuditLog.timestamp <= filters.end_date)

        # Tính tổng số bản ghi
        total = query.count()

        # Áp dụng sắp xếp
        if sort_by:
            column = getattr(AuditLog, sort_by, AuditLog.timestamp)
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

    def get_user_audit_logs(
        self, db: Session, user_id: int, limit: int = 100
    ) -> List[AuditLog]:
        """Lấy lịch sử các hành động kiểm toán của một người dùng"""
        return (
            db.query(AuditLog)
            .filter(AuditLog.user_id == user_id)
            .order_by(desc(AuditLog.timestamp))
            .limit(limit)
            .all()
        )

    def get_resource_audit_logs(
        self, db: Session, resource_type: str, resource_id: str, limit: int = 100
    ) -> List[AuditLog]:
        """Lấy lịch sử các thay đổi của một tài nguyên"""
        return (
            db.query(AuditLog)
            .filter(
                AuditLog.resource_type == resource_type,
                AuditLog.resource_id == resource_id,
            )
            .order_by(desc(AuditLog.timestamp))
            .limit(limit)
            .all()
        )

    def get_audit_stats(
        self, db: Session, days: int = 30, group_by: str = "daily"
    ) -> Dict[str, Any]:
        """Thống kê hoạt động kiểm toán theo thời gian"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        if group_by == "daily":
            date_trunc = func.date_trunc("day", AuditLog.timestamp)
        elif group_by == "hourly":
            date_trunc = func.date_trunc("hour", AuditLog.timestamp)
        elif group_by == "weekly":
            date_trunc = func.date_trunc("week", AuditLog.timestamp)
        else:
            date_trunc = func.date_trunc("day", AuditLog.timestamp)

        # Thống kê số lượng hoạt động theo thời gian
        stats_by_time = (
            db.query(
                date_trunc.label("time_period"),
                func.count(AuditLog.id).label("event_count"),
            )
            .filter(AuditLog.timestamp.between(start_date, end_date))
            .group_by(date_trunc)
            .order_by(date_trunc)
            .all()
        )

        # Thống kê theo loại sự kiện
        event_type_stats = (
            db.query(AuditLog.event_type, func.count(AuditLog.id).label("count"))
            .filter(AuditLog.timestamp.between(start_date, end_date))
            .group_by(AuditLog.event_type)
            .order_by(func.count(AuditLog.id).desc())
            .all()
        )

        # Thống kê theo loại tài nguyên
        resource_type_stats = (
            db.query(AuditLog.resource_type, func.count(AuditLog.id).label("count"))
            .filter(AuditLog.timestamp.between(start_date, end_date))
            .group_by(AuditLog.resource_type)
            .order_by(func.count(AuditLog.id).desc())
            .all()
        )

        # Thống kê theo hành động
        action_stats = (
            db.query(AuditLog.action, func.count(AuditLog.id).label("count"))
            .filter(AuditLog.timestamp.between(start_date, end_date))
            .group_by(AuditLog.action)
            .order_by(func.count(AuditLog.id).desc())
            .all()
        )

        return {
            "time_stats": [
                {"time_period": period.time_period, "event_count": period.event_count}
                for period in stats_by_time
            ],
            "event_type_stats": [
                {"event_type": stat.event_type, "count": stat.count}
                for stat in event_type_stats
            ],
            "resource_type_stats": [
                {"resource_type": stat.resource_type, "count": stat.count}
                for stat in resource_type_stats
            ],
            "action_stats": [
                {"action": stat.action, "count": stat.count} for stat in action_stats
            ],
        }

    def delete_log(self, db: Session, log_id: int) -> bool:
        """Xóa log kiểm toán theo ID"""
        db_log = db.query(AuditLog).filter(AuditLog.id == log_id).first()
        if not db_log:
            return False

        db.delete(db_log)
        db.commit()
        return True
