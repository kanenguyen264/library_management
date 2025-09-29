from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, func
from datetime import datetime, timezone, timedelta

from app.core.db import Base
from app.logs_manager.models.admin_activity_log import AdminActivityLog
from app.logs_manager.schemas.admin_activity_log import (
    AdminActivityLogCreate,
    AdminActivityLogFilter,
)


class AdminActivityLogRepository:
    def create_log(
        self, db: Session, log_data: AdminActivityLogCreate
    ) -> AdminActivityLog:
        """Tạo log hoạt động admin mới từ dữ liệu đầu vào"""
        db_log = AdminActivityLog(**log_data.model_dump(exclude_unset=True))
        db.add(db_log)
        db.commit()
        db.refresh(db_log)
        return db_log

    def get_by_id(self, db: Session, log_id: int) -> Optional[AdminActivityLog]:
        """Lấy log hoạt động admin theo ID"""
        return db.query(AdminActivityLog).filter(AdminActivityLog.id == log_id).first()

    def get_all(
        self,
        db: Session,
        filters: Optional[AdminActivityLogFilter] = None,
        skip: int = 0,
        limit: int = 100,
        sort_by: str = "timestamp",
        sort_desc: bool = True,
    ) -> Dict[str, Any]:
        """Lấy danh sách log hoạt động admin với các bộ lọc và phân trang"""
        query = db.query(AdminActivityLog)

        # Áp dụng filters
        if filters:
            if filters.admin_id is not None:
                query = query.filter(AdminActivityLog.admin_id == filters.admin_id)

            if filters.activity_type:
                query = query.filter(
                    AdminActivityLog.activity_type == filters.activity_type
                )

            if filters.resource_type:
                query = query.filter(
                    AdminActivityLog.resource_type == filters.resource_type
                )

            if filters.success is not None:
                query = query.filter(AdminActivityLog.success == filters.success)

            if filters.start_date:
                query = query.filter(AdminActivityLog.timestamp >= filters.start_date)

            if filters.end_date:
                query = query.filter(AdminActivityLog.timestamp <= filters.end_date)

        # Tính tổng số bản ghi
        total = query.count()

        # Áp dụng sắp xếp
        if sort_by:
            column = getattr(AdminActivityLog, sort_by, AdminActivityLog.timestamp)
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
        admin_id: Optional[int] = None,
        activity_type: Optional[str] = None,
        affected_resource: Optional[str] = None,
        resource_id: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> int:
        """
        Count admin activity logs with optional filtering
        """
        query = db.query(func.count(AdminActivityLog.id))

        # Apply filters
        if admin_id is not None:
            query = query.filter(AdminActivityLog.admin_id == admin_id)
        if activity_type:
            query = query.filter(AdminActivityLog.activity_type == activity_type)
        if affected_resource:
            query = query.filter(
                AdminActivityLog.affected_resource == affected_resource
            )
        if resource_id is not None:
            query = query.filter(AdminActivityLog.resource_id == resource_id)
        if start_date:
            query = query.filter(AdminActivityLog.created_at >= start_date)
        if end_date:
            query = query.filter(AdminActivityLog.created_at <= end_date)

        return query.scalar() or 0

    @staticmethod
    def update(
        db: Session, log_id: int, log_data: Dict[str, Any]
    ) -> Optional[AdminActivityLog]:
        """
        Update an admin activity log
        """
        db_log = AdminActivityLogRepository.get_by_id(db, log_id)
        if db_log:
            for key, value in log_data.items():
                setattr(db_log, key, value)
            db.commit()
            db.refresh(db_log)
        return db_log

    @staticmethod
    def delete(db: Session, log_id: int) -> bool:
        """
        Delete an admin activity log
        """
        db_log = AdminActivityLogRepository.get_by_id(db, log_id)
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
            db.query(AdminActivityLog)
            .filter(AdminActivityLog.created_at < cutoff_date)
            .delete(synchronize_session=False)
        )
        db.commit()
        return result
