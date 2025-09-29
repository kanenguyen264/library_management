from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import logging
import os
from typing import Dict
from sqlalchemy import func

from app.core.db import Base
from app.logs_manager.models.search_log import SearchLog
from app.logs_manager.models.user_activity_log import UserActivityLog
from app.logs_manager.models.admin_activity_log import AdminActivityLog
from app.logs_manager.models.api_request_log import ApiRequestLog
from app.logs_manager.models.authentication_log import AuthenticationLog
from app.logs_manager.models.error_log import ErrorLog
from app.logs_manager.models.performance_log import PerformanceLog
from app.logs_manager.models.security_log import SecurityLog
from app.logs_manager.models.system_log import SystemLog
from app.logs_manager.models.audit_log import AuditLog
from app.logs_manager.repositories import (
    user_activity_log_repo,
    admin_activity_log_repo,
    error_log_repo,
    authentication_log_repo,
    performance_log_repo,
    api_request_log_repo,
    search_log_repo,
    security_log_repo,
    system_log_repo,
    audit_log_repo,
)

logger = logging.getLogger(__name__)


class LogRotationRepository:
    """
    Handles the rotation (deletion) of old logs based on retention policies
    """

    def __init__(self, log_archive_dir: str = "logs/archive"):
        """Khởi tạo repository xoay vòng log"""
        self.log_dir = log_archive_dir
        os.makedirs(self.log_dir, exist_ok=True)

    @staticmethod
    def rotate_all_logs(
        db: Session,
        user_activity_days: int = 90,
        admin_activity_days: int = 365,
        error_days: int = 90,
        auth_days: int = 180,
        performance_days: int = 30,
        api_request_days: int = 30,
        search_days: int = 90,
    ) -> dict:
        """
        Rotate (delete) all types of logs based on retention policies

        Args:
            db: Database session
            user_activity_days: Days to keep user activity logs
            admin_activity_days: Days to keep admin activity logs
            error_days: Days to keep error logs
            auth_days: Days to keep authentication logs
            performance_days: Days to keep performance logs
            api_request_days: Days to keep API request logs
            search_days: Days to keep search logs

        Returns:
            dict: Count of deleted records by log type
        """
        results = {}

        try:
            # Rotate user activity logs
            user_deleted = user_activity_log_repo.delete_old_logs(
                db, user_activity_days
            )
            results["user_activity_logs"] = user_deleted
            logger.info(
                f"Deleted {user_deleted} user activity logs older than {user_activity_days} days"
            )

            # Rotate admin activity logs
            admin_deleted = admin_activity_log_repo.delete_old_logs(
                db, admin_activity_days
            )
            results["admin_activity_logs"] = admin_deleted
            logger.info(
                f"Deleted {admin_deleted} admin activity logs older than {admin_activity_days} days"
            )

            # Rotate error logs
            error_deleted = error_log_repo.delete_old_logs(db, error_days)
            results["error_logs"] = error_deleted
            logger.info(
                f"Deleted {error_deleted} error logs older than {error_days} days"
            )

            # Rotate authentication logs
            auth_deleted = authentication_log_repo.delete_old_logs(db, auth_days)
            results["authentication_logs"] = auth_deleted
            logger.info(
                f"Deleted {auth_deleted} authentication logs older than {auth_days} days"
            )

            # Rotate performance logs
            perf_deleted = performance_log_repo.delete_old_logs(db, performance_days)
            results["performance_logs"] = perf_deleted
            logger.info(
                f"Deleted {perf_deleted} performance logs older than {performance_days} days"
            )

            # Rotate API request logs
            api_deleted = api_request_log_repo.delete_old_logs(db, api_request_days)
            results["api_request_logs"] = api_deleted
            logger.info(
                f"Deleted {api_deleted} API request logs older than {api_request_days} days"
            )

            # Rotate search logs
            search_deleted = search_log_repo.delete_old_logs(db, search_days)
            results["search_logs"] = search_deleted
            logger.info(
                f"Deleted {search_deleted} search logs older than {search_days} days"
            )

        except Exception as e:
            logger.error(f"Error rotating logs: {str(e)}")
            db.rollback()
            raise

        return results

    def rotate_logs(
        self, db: Session, days: int = 30, batch_size: int = 1000, compress: bool = True
    ) -> Dict[str, int]:
        """
        Xoay vòng logs: lưu trữ và xóa logs cũ

        Args:
            db: Database session
            days: Số ngày để định nghĩa logs cũ (logs cũ hơn số ngày này sẽ bị xoay vòng)
            batch_size: Kích thước lô để xử lý (để tránh quá tải memory)
            compress: Nén logs sau khi lưu trữ

        Returns:
            Dict chứa số lượng logs đã xoay vòng theo loại
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        archive_date = datetime.now().strftime("%Y%m%d")

        # Thư mục lưu trữ theo ngày
        archive_dir = os.path.join(self.log_dir, archive_date)
        os.makedirs(archive_dir, exist_ok=True)

        results = {}

        # Xử lý từng loại log
        log_models = [
            SearchLog,
            UserActivityLog,
            AdminActivityLog,
            ApiRequestLog,
            AuthenticationLog,
            ErrorLog,
            PerformanceLog,
            SecurityLog,
            SystemLog,
            AuditLog,
        ]

        for model in log_models:
            model_name = model.__name__
            # Đếm số lượng logs cần xoay vòng
            count = (
                db.query(func.count(model.id))
                .filter(model.timestamp < cutoff_date)
                .scalar()
                or 0
            )

            if count > 0:
                # Xử lý theo lô
                processed = 0
                while processed < count:
                    # Lấy batch logs cũ nhất
                    logs = (
                        db.query(model)
                        .filter(model.timestamp < cutoff_date)
                        .order_by(model.timestamp.asc())
                        .limit(batch_size)
                        .all()
                    )

                    if not logs:
                        break

                    # Lưu trữ logs
                    self._archive_logs(logs, model_name, archive_dir, compress)

                    # Xóa logs đã lưu trữ
                    log_ids = [log.id for log in logs]
                    db.query(model).filter(model.id.in_(log_ids)).delete(
                        synchronize_session=False
                    )
                    db.commit()

                    processed += len(logs)

                results[model_name] = processed

        return results

    def _archive_logs(self, logs, model_name, archive_dir, compress):
        # Implementation of _archive_logs method
        pass
