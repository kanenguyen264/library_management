from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, desc
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta

from app.admin_site.models import SystemMetric
from app.logging.setup import get_logger

logger = get_logger(__name__)

class SystemMetricRepository:
    """
    Repository để thao tác với SystemMetric trong cơ sở dữ liệu.
    """
    
    @staticmethod
    def get_by_id(db: Session, metric_id: int) -> Optional[SystemMetric]:
        """
        Lấy số liệu hệ thống theo ID.
        
        Args:
            db: Database session
            metric_id: ID của số liệu
            
        Returns:
            SystemMetric object nếu tìm thấy, None nếu không
        """
        return db.query(SystemMetric).filter(SystemMetric.id == metric_id).first()
    
    @staticmethod
    def count(
        db: Session, 
        metric_name: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> int:
        """
        Đếm số lượng số liệu hệ thống với các điều kiện lọc.
        """
        query = db.query(func.count(SystemMetric.id))
        
        if metric_name:
            query = query.filter(SystemMetric.metric_type == metric_name)
        
        if start_time:
            query = query.filter(SystemMetric.created_at >= start_time)
        
        if end_time:
            query = query.filter(SystemMetric.created_at <= end_time)
        
        return query.scalar()
    
    @staticmethod
    def get_all(
        db: Session, 
        skip: int = 0, 
        limit: int = 100,
        metric_name: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        order_by: str = "timestamp",
        order_desc: bool = True
    ) -> List[SystemMetric]:
        """
        Lấy danh sách số liệu hệ thống với các tùy chọn lọc.
        
        Args:
            db: Database session
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa
            metric_name: Loại số liệu
            start_time: Thời điểm bắt đầu
            end_time: Thời điểm kết thúc
            
        Returns:
            Danh sách số liệu hệ thống
        """
        query = db.query(SystemMetric)
        
        if metric_name:
            query = query.filter(SystemMetric.metric_type == metric_name)
        
        if start_time:
            query = query.filter(SystemMetric.created_at >= start_time)
        
        if end_time:
            query = query.filter(SystemMetric.created_at <= end_time)
        
        # Xử lý sắp xếp
        if hasattr(SystemMetric, order_by):
            if order_desc:
                query = query.order_by(desc(getattr(SystemMetric, order_by)))
            else:
                query = query.order_by(getattr(SystemMetric, order_by))
        
        return query.offset(skip).limit(limit).all()
    
    @staticmethod
    def get_by_conditions(
        db: Session,
        conditions: Dict[str, Any],
        skip: int = 0,
        limit: int = 100,
        order_by: Optional[str] = None,
        order_desc: bool = True
    ) -> List[SystemMetric]:
        """
        Lấy danh sách số liệu hệ thống theo các điều kiện tùy chỉnh.
        """
        query = db.query(SystemMetric)
        
        for field, value in conditions.items():
            if value is not None:
                if field == 'metric_name':
                    query = query.filter(SystemMetric.metric_type == value)
                elif field == 'start_time':
                    query = query.filter(SystemMetric.created_at >= value)
                elif field == 'end_time':
                    query = query.filter(SystemMetric.created_at <= value)
                elif hasattr(SystemMetric, field):
                    query = query.filter(getattr(SystemMetric, field) == value)
        
        if order_by and hasattr(SystemMetric, order_by):
            if order_desc:
                query = query.order_by(desc(getattr(SystemMetric, order_by)))
            else:
                query = query.order_by(getattr(SystemMetric, order_by))
        
        return query.offset(skip).limit(limit).all()
    
    @staticmethod
    def create(db: Session, metric_data: Dict[str, Any]) -> SystemMetric:
        """
        Tạo số liệu hệ thống mới.
        
        Args:
            db: Database session
            metric_data: Dữ liệu số liệu
            
        Returns:
            SystemMetric object đã tạo
        """
        try:
            db_metric = SystemMetric(**metric_data)
            db.add(db_metric)
            db.commit()
            db.refresh(db_metric)
            logger.info(f"Đã tạo số liệu hệ thống mới: {db_metric.metric_type}")
            return db_metric
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi tạo số liệu hệ thống: {str(e)}")
            raise e
    
    @staticmethod
    def update(db: Session, metric_id: int, metric_data: Dict[str, Any]) -> Optional[SystemMetric]:
        """
        Cập nhật thông tin số liệu hệ thống.
        """
        try:
            db_metric = SystemMetricRepository.get_by_id(db, metric_id)
            if not db_metric:
                logger.warning(f"Không tìm thấy số liệu hệ thống ID={metric_id} để cập nhật")
                return None
            
            for key, value in metric_data.items():
                setattr(db_metric, key, value)
            
            db_metric.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(db_metric)
            logger.info(f"Đã cập nhật số liệu hệ thống ID={metric_id}")
            return db_metric
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi cập nhật số liệu hệ thống ID={metric_id}: {str(e)}")
            raise e
    
    @staticmethod
    def get_average(
        db: Session, 
        metric_name: str, 
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> float:
        """
        Lấy giá trị trung bình của số liệu hệ thống.
        
        Args:
            db: Database session
            metric_name: Loại số liệu
            start_time: Thời điểm bắt đầu
            end_time: Thời điểm kết thúc
            
        Returns:
            Giá trị trung bình
        """
        query = db.query(func.avg(SystemMetric.value).label('average'))
        query = query.filter(SystemMetric.metric_type == metric_name)
        
        if start_time:
            query = query.filter(SystemMetric.created_at >= start_time)
        
        if end_time:
            query = query.filter(SystemMetric.created_at <= end_time)
        
        result = query.first()
        return result.average if result.average is not None else 0.0
    
    @staticmethod
    def get_aggregation(
        db: Session,
        metric_name: str,
        interval: str,  # 'hour', 'day', 'week', 'month'
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Tổng hợp số liệu theo khoảng thời gian.
        
        Args:
            db: Database session
            metric_name: Loại số liệu
            interval: Khoảng thời gian ('hour', 'day', 'week', 'month')
            start_time: Thời điểm bắt đầu
            end_time: Thời điểm kết thúc
            
        Returns:
            Danh sách kết quả tổng hợp
        """
        # Xác định trường ngày tháng dựa trên khoảng thời gian
        if interval == 'hour':
            date_trunc = func.date_trunc('hour', SystemMetric.created_at)
        elif interval == 'day':
            date_trunc = func.date_trunc('day', SystemMetric.created_at)
        elif interval == 'week':
            date_trunc = func.date_trunc('week', SystemMetric.created_at)
        elif interval == 'month':
            date_trunc = func.date_trunc('month', SystemMetric.created_at)
        else:
            raise ValueError("Invalid interval. Must be 'hour', 'day', 'week', or 'month'")
        
        # Xây dựng truy vấn
        query = db.query(
            date_trunc.label('time_period'),
            func.avg(SystemMetric.value).label('average'),
            func.min(SystemMetric.value).label('minimum'),
            func.max(SystemMetric.value).label('maximum'),
            func.count(SystemMetric.id).label('count')
        )
        
        query = query.filter(SystemMetric.metric_type == metric_name)
        
        if start_time:
            query = query.filter(SystemMetric.created_at >= start_time)
        
        if end_time:
            query = query.filter(SystemMetric.created_at <= end_time)
        
        query = query.group_by('time_period').order_by('time_period')
        
        results = query.all()
        
        return [
            {
                "time_period": result.time_period,
                "average": result.average,
                "minimum": result.minimum,
                "maximum": result.maximum,
                "count": result.count
            }
            for result in results
        ]
    
    @staticmethod
    def delete_old_metrics(db: Session, days: int = 30) -> int:
        """
        Xóa số liệu cũ hơn một số ngày nhất định.
        
        Args:
            db: Database session
            days: Số ngày
            
        Returns:
            Số lượng bản ghi đã xóa
        """
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
            deleted = db.query(SystemMetric).filter(SystemMetric.created_at < cutoff_date).delete()
            db.commit()
            logger.info(f"Đã xóa {deleted} số liệu hệ thống cũ hơn {days} ngày")
            return deleted
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi xóa số liệu hệ thống cũ: {str(e)}")
            raise e
    
    @staticmethod
    def delete(db: Session, metric_id: int) -> bool:
        """
        Xóa số liệu hệ thống.
        """
        try:
            db_metric = SystemMetricRepository.get_by_id(db, metric_id)
            if not db_metric:
                logger.warning(f"Không tìm thấy số liệu hệ thống ID={metric_id} để xóa")
                return False
            
            db.delete(db_metric)
            db.commit()
            logger.info(f"Đã xóa số liệu hệ thống ID={metric_id}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi xóa số liệu hệ thống ID={metric_id}: {str(e)}")
            raise e
