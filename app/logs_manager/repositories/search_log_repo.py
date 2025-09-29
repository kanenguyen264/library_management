from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, func, text
from datetime import datetime, timezone, timedelta

from app.core.db import Base
from app.logs_manager.models.search_log import SearchLog
from app.logs_manager.schemas.search_log import SearchLogCreate, SearchLogFilter


class SearchLogRepository:
    def create_log(self, db: Session, log_data: SearchLogCreate) -> SearchLog:
        """Tạo log tìm kiếm mới từ dữ liệu đầu vào"""
        db_log = SearchLog(**log_data.model_dump(exclude_unset=True))
        db.add(db_log)
        db.commit()
        db.refresh(db_log)
        return db_log

    def get_by_id(self, db: Session, log_id: int) -> Optional[SearchLog]:
        """Lấy log tìm kiếm theo ID"""
        return db.query(SearchLog).filter(SearchLog.id == log_id).first()

    def get_all(
        self,
        db: Session,
        filters: Optional[SearchLogFilter] = None,
        skip: int = 0,
        limit: int = 100,
        sort_by: str = "timestamp",
        sort_desc: bool = True,
    ) -> Dict[str, Any]:
        """Lấy danh sách log tìm kiếm với các bộ lọc và phân trang"""
        query = db.query(SearchLog)

        # Áp dụng filters
        if filters:
            if filters.user_id is not None:
                query = query.filter(SearchLog.user_id == filters.user_id)

            if filters.query:
                query = query.filter(SearchLog.query.ilike(f"%{filters.query}%"))

            if filters.category:
                query = query.filter(SearchLog.category == filters.category)

            if filters.source:
                query = query.filter(SearchLog.source == filters.source)

            if filters.start_date:
                query = query.filter(SearchLog.timestamp >= filters.start_date)

            if filters.end_date:
                query = query.filter(SearchLog.timestamp <= filters.end_date)

            if filters.min_results is not None:
                query = query.filter(SearchLog.results_count >= filters.min_results)

            if filters.max_results is not None:
                query = query.filter(SearchLog.results_count <= filters.max_results)

        # Tính tổng số bản ghi
        total = query.count()

        # Áp dụng sắp xếp
        if sort_by:
            column = getattr(SearchLog, sort_by, SearchLog.timestamp)
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

    def count(self, db: Session, filters: Optional[SearchLogFilter] = None) -> int:
        """Đếm số log tìm kiếm với các điều kiện lọc"""
        query = db.query(func.count(SearchLog.id))

        # Áp dụng filters
        if filters:
            if filters.user_id is not None:
                query = query.filter(SearchLog.user_id == filters.user_id)

            if filters.query:
                query = query.filter(SearchLog.query.ilike(f"%{filters.query}%"))

            if filters.category:
                query = query.filter(SearchLog.category == filters.category)

            if filters.source:
                query = query.filter(SearchLog.source == filters.source)

            if filters.start_date:
                query = query.filter(SearchLog.timestamp >= filters.start_date)

            if filters.end_date:
                query = query.filter(SearchLog.timestamp <= filters.end_date)

            if filters.min_results is not None:
                query = query.filter(SearchLog.results_count >= filters.min_results)

            if filters.max_results is not None:
                query = query.filter(SearchLog.results_count <= filters.max_results)

        return query.scalar() or 0

    @staticmethod
    def update(
        db: Session, log_id: int, log_data: Dict[str, Any]
    ) -> Optional[SearchLog]:
        """
        Update a search log
        """
        db_log = SearchLogRepository.get_by_id(db, log_id)
        if db_log:
            for key, value in log_data.items():
                setattr(db_log, key, value)
            db.commit()
            db.refresh(db_log)
        return db_log

    @staticmethod
    def delete(db: Session, log_id: int) -> bool:
        """
        Delete a search log
        """
        db_log = SearchLogRepository.get_by_id(db, log_id)
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
            db.query(SearchLog)
            .filter(SearchLog.created_at < cutoff_date)
            .delete(synchronize_session=False)
        )
        db.commit()
        return result

    @staticmethod
    def get_popular_search_terms(
        db: Session, days: int = 30, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get most popular search terms
        """
        start_date = datetime.now(timezone.utc) - timedelta(days=days)
        terms = (
            db.query(
                SearchLog.query,
                func.count(SearchLog.id).label("count"),
                func.avg(SearchLog.results_count).label("avg_results"),
            )
            .filter(SearchLog.created_at >= start_date)
            .group_by(SearchLog.query)
            .order_by(desc("count"))
            .limit(limit)
            .all()
        )

        return [
            {
                "term": term,
                "count": count,
                "avg_results": float(avg_results) if avg_results else 0,
            }
            for term, count, avg_results in terms
        ]

    @staticmethod
    def get_zero_results_searches(
        db: Session, days: int = 30, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get search terms that return zero results
        """
        start_date = datetime.now(timezone.utc) - timedelta(days=days)
        terms = (
            db.query(SearchLog.query, func.count(SearchLog.id).label("count"))
            .filter(SearchLog.created_at >= start_date, SearchLog.results_count == 0)
            .group_by(SearchLog.query)
            .order_by(desc("count"))
            .limit(limit)
            .all()
        )

        return [{"term": term, "count": count} for term, count in terms]

    @staticmethod
    def update_clicked_results(
        db: Session, log_id: int, clicked_results: List[Dict[str, Any]]
    ) -> Optional[SearchLog]:
        """
        Update the clicked results for a search log
        """
        db_log = SearchLogRepository.get_by_id(db, log_id)
        if db_log:
            db_log.clicked_results = clicked_results
            db.commit()
            db.refresh(db_log)
            return db_log
        return None
