from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, func
from datetime import datetime, timedelta, timezone

from app.core.db import Base
from app.logs_manager.models.user_activity_log import UserActivityLog
from app.logs_manager.schemas.user_activity_log import (
    UserActivityLogCreate,
    UserActivityLogFilter,
)


class UserActivityLogRepository:
    def create_log(
        self, db: Session, log_data: UserActivityLogCreate
    ) -> UserActivityLog:
        """Tạo log hoạt động người dùng mới từ dữ liệu đầu vào"""
        # Convert to dict with field aliases for DB model
        data_dict = log_data.model_dump(by_alias=True, exclude_unset=True)

        # Ensure default timestamp if not provided
        if "timestamp" not in data_dict:
            data_dict["timestamp"] = datetime.now(timezone.utc)

        db_log = UserActivityLog(**data_dict)
        db.add(db_log)
        db.commit()
        db.refresh(db_log)
        return db_log

    def get_by_id(self, db: Session, log_id: int) -> Optional[UserActivityLog]:
        """Lấy log hoạt động người dùng theo ID"""
        return db.query(UserActivityLog).filter(UserActivityLog.id == log_id).first()

    def get_all(
        self,
        db: Session,
        filters: Optional[UserActivityLogFilter] = None,
        skip: int = 0,
        limit: int = 100,
        sort_by: str = "timestamp",
        sort_desc: bool = True,
    ) -> Dict[str, Any]:
        """Lấy danh sách log hoạt động người dùng với các bộ lọc và phân trang"""
        query = db.query(UserActivityLog)

        # Áp dụng filters
        if filters:
            if filters.user_id is not None:
                query = query.filter(UserActivityLog.user_id == filters.user_id)

            if filters.activity_type:
                query = query.filter(
                    UserActivityLog.activity_type == filters.activity_type
                )

            if filters.entity_type:
                query = query.filter(
                    UserActivityLog.resource_type == filters.entity_type
                )

            if filters.entity_id:
                query = query.filter(UserActivityLog.resource_id == filters.entity_id)

            if filters.start_date:
                query = query.filter(UserActivityLog.timestamp >= filters.start_date)

            if filters.end_date:
                query = query.filter(UserActivityLog.timestamp <= filters.end_date)

        # Tính tổng số bản ghi
        total = query.count()

        # Áp dụng sắp xếp
        if sort_by:
            column = getattr(UserActivityLog, sort_by, UserActivityLog.timestamp)
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

    def count(
        self,
        db: Session,
        user_id: Optional[int] = None,
        activity_type: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> int:
        """Đếm số log hoạt động người dùng với các điều kiện lọc"""
        query = db.query(func.count(UserActivityLog.id))

        # Áp dụng filters
        if user_id is not None:
            query = query.filter(UserActivityLog.user_id == user_id)
        if activity_type:
            query = query.filter(UserActivityLog.activity_type == activity_type)
        if resource_type:
            query = query.filter(UserActivityLog.resource_type == resource_type)
        if resource_id:
            query = query.filter(UserActivityLog.resource_id == resource_id)
        if start_date:
            query = query.filter(UserActivityLog.timestamp >= start_date)
        if end_date:
            query = query.filter(UserActivityLog.timestamp <= end_date)

        return query.scalar() or 0

    def update(
        self, db: Session, log_id: int, log_data: Dict[str, Any]
    ) -> Optional[UserActivityLog]:
        """Cập nhật log hoạt động người dùng"""
        db_log = self.get_by_id(db, log_id)
        if db_log:
            for key, value in log_data.items():
                setattr(db_log, key, value)
            db.commit()
            db.refresh(db_log)
        return db_log

    def delete(self, db: Session, log_id: int) -> bool:
        """Xóa log hoạt động người dùng"""
        db_log = self.get_by_id(db, log_id)
        if db_log:
            db.delete(db_log)
            db.commit()
            return True
        return False

    def delete_old_logs(self, db: Session, days: int = 90) -> int:
        """Xóa logs cũ hơn số ngày chỉ định"""
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        result = (
            db.query(UserActivityLog)
            .filter(UserActivityLog.timestamp < cutoff_date)
            .delete(synchronize_session=False)
        )
        db.commit()
        return result
