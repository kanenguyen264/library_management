from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, func, delete
from datetime import datetime, timezone, timedelta
import json

from app.core.db import Base
from app.logs_manager.models.authentication_log import AuthenticationLog
from app.logs_manager.schemas.authentication_log import (
    AuthenticationLogCreate,
    AuthenticationLogFilter,
)


class AuthenticationLogRepository:
    async def create_log(
        self, db: Session, log_data: AuthenticationLogCreate
    ) -> AuthenticationLog:
        """
        Tạo log xác thực mới

        Args:
            db: Database session
            log_data: Dữ liệu log

        Returns:
            Đối tượng log đã tạo
        """
        # Extract the details field to handle separately
        log_dict = log_data.model_dump(exclude_unset=True)
        details_data = log_dict.pop("details", None)

        # Make sure action field is present in database model
        if "action" not in log_dict and details_data and "action" in details_data:
            log_dict["action"] = details_data.pop("action")

        # If we have details, convert them to JSON for failure_reason field
        if details_data:
            if "failure_reason" not in log_dict or not log_dict["failure_reason"]:
                # Convert details to string and use as failure_reason if not already set
                try:
                    log_dict["failure_reason"] = json.dumps(details_data)
                except Exception:
                    # If can't convert to JSON, use string representation
                    log_dict["failure_reason"] = str(details_data)

        # Create model instance and save to db
        db_log = AuthenticationLog(**log_dict)
        db.add(db_log)
        await db.commit()
        await db.refresh(db_log)
        return db_log

    async def get_by_id(self, db: Session, log_id: int) -> Optional[AuthenticationLog]:
        """
        Lấy log xác thực theo ID

        Args:
            db: Database session (can be AsyncSession or regular Session)
            log_id: ID of the log to retrieve

        Returns:
            AuthenticationLog or None if not found
        """
        query = db.query(AuthenticationLog).filter(AuthenticationLog.id == log_id)

        # Kiểm tra nếu có phương thức execute (AsyncSession)
        if hasattr(db, "execute") and hasattr(db.execute, "__await__"):
            result = await db.execute(query)
            return result.scalar_one_or_none()
        else:
            return query.first()

    async def get_all(
        self,
        db: Session,
        filters: Optional[AuthenticationLogFilter] = None,
        skip: int = 0,
        limit: int = 100,
        sort_by: str = "timestamp",
        sort_desc: bool = True,
    ) -> Dict[str, Any]:
        """Lấy danh sách log xác thực với các bộ lọc và phân trang"""
        query = db.query(AuthenticationLog)

        # Áp dụng filters
        if filters:
            if filters.user_id is not None:
                query = query.filter(AuthenticationLog.user_id == filters.user_id)

            if filters.action:
                query = query.filter(AuthenticationLog.event_type == filters.action)

            if filters.status:
                query = query.filter(AuthenticationLog.status == filters.status)

            if filters.start_date:
                query = query.filter(AuthenticationLog.timestamp >= filters.start_date)

            if filters.end_date:
                query = query.filter(AuthenticationLog.timestamp <= filters.end_date)

        # Tạo query đếm để lấy tổng số bản ghi
        count_query = query.statement.with_only_columns([func.count()]).order_by(None)

        # Áp dụng sắp xếp
        if sort_by:
            column = getattr(AuthenticationLog, sort_by, AuthenticationLog.timestamp)
            if sort_desc:
                query = query.order_by(desc(column))
            else:
                query = query.order_by(asc(column))

        # Áp dụng phân trang
        query = query.offset(skip).limit(limit)

        # Kiểm tra xem có phải AsyncSession không
        if hasattr(db, "execute") and hasattr(db.execute, "__await__"):
            # Async execution
            result = await db.execute(query)
            items = result.scalars().all()

            # Get total count
            total_result = await db.execute(count_query)
            total = total_result.scalar() or 0
        else:
            # Sync execution
            items = query.all()
            total = db.execute(count_query).scalar() or 0

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
    async def count(
        db: Session,
        user_id: Optional[int] = None,
        admin_id: Optional[int] = None,
        action: Optional[str] = None,
        status: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> int:
        """
        Count authentication logs with optional filtering
        """
        query = db.query(func.count(AuthenticationLog.id))

        # Apply filters
        if user_id is not None:
            query = query.filter(AuthenticationLog.user_id == user_id)
        if admin_id is not None:
            query = query.filter(AuthenticationLog.admin_id == admin_id)
        if action:
            query = query.filter(AuthenticationLog.event_type == action)
        if status:
            query = query.filter(AuthenticationLog.status == status)
        if start_date:
            query = query.filter(AuthenticationLog.timestamp >= start_date)
        if end_date:
            query = query.filter(AuthenticationLog.timestamp <= end_date)

        # Kiểm tra nếu là AsyncSession
        if hasattr(db, "execute") and hasattr(db.execute, "__await__"):
            result = await db.execute(query)
            return result.scalar() or 0
        else:
            return query.scalar() or 0

    @staticmethod
    async def delete_old_logs(db: Session, days: int = 90) -> int:
        """
        Delete logs older than specified days
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        # Kiểm tra nếu là AsyncSession
        if hasattr(db, "execute") and hasattr(db.execute, "__await__"):
            query = delete(AuthenticationLog).where(
                AuthenticationLog.timestamp < cutoff_date
            )
            result = await db.execute(query)
            await db.commit()
            return result.rowcount
        else:
            result = (
                db.query(AuthenticationLog)
                .filter(AuthenticationLog.timestamp < cutoff_date)
                .delete(synchronize_session=False)
            )
            db.commit()
            return result
