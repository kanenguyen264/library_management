from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, desc
from typing import List, Optional, Dict, Any
from datetime import datetime

from app.admin_site.models import SystemHealth
from app.logging.setup import get_logger

logger = get_logger(__name__)

class SystemHealthRepository:
    """
    Repository để thao tác với SystemHealth trong cơ sở dữ liệu.
    """
    
    @staticmethod
    def get_by_id(db: Session, health_id: int) -> Optional[SystemHealth]:
        """
        Lấy trạng thái sức khỏe hệ thống theo ID.
        
        Args:
            db: Database session
            health_id: ID của trạng thái
            
        Returns:
            SystemHealth object nếu tìm thấy, None nếu không
        """
        return db.query(SystemHealth).filter(SystemHealth.id == health_id).first()
    
    @staticmethod
    def get_by_component(db: Session, component: str) -> Optional[SystemHealth]:
        """
        Lấy trạng thái sức khỏe hệ thống theo tên thành phần.
        """
        return (
            db.query(SystemHealth)
            .filter(SystemHealth.component == component)
            .order_by(desc(SystemHealth.created_at))
            .first()
        )
    
    @staticmethod
    def count(
        db: Session, 
        component: Optional[str] = None,
        status: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> int:
        """
        Đếm số lượng báo cáo sức khỏe hệ thống với các điều kiện lọc.
        """
        query = db.query(func.count(SystemHealth.id))
        
        if component:
            query = query.filter(SystemHealth.component == component)
        
        if status:
            query = query.filter(SystemHealth.status == status)
        
        if start_date:
            query = query.filter(SystemHealth.created_at >= start_date)
        
        if end_date:
            query = query.filter(SystemHealth.created_at <= end_date)
        
        return query.scalar()
    
    @staticmethod
    def get_all(
        db: Session, 
        skip: int = 0, 
        limit: int = 100,
        component: Optional[str] = None,
        status: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        order_by: str = "last_updated",
        order_desc: bool = True
    ) -> List[SystemHealth]:
        """
        Lấy danh sách báo cáo sức khỏe hệ thống với các tùy chọn lọc.
        """
        query = db.query(SystemHealth)
        
        if component:
            query = query.filter(SystemHealth.component == component)
        
        if status:
            query = query.filter(SystemHealth.status == status)
        
        if start_date:
            query = query.filter(SystemHealth.created_at >= start_date)
        
        if end_date:
            query = query.filter(SystemHealth.created_at <= end_date)
        
        # Xử lý sắp xếp
        if hasattr(SystemHealth, order_by):
            if order_desc:
                query = query.order_by(desc(getattr(SystemHealth, order_by)))
            else:
                query = query.order_by(getattr(SystemHealth, order_by))
        
        return query.offset(skip).limit(limit).all()
    
    @staticmethod
    def get_by_conditions(
        db: Session,
        conditions: Dict[str, Any],
        skip: int = 0,
        limit: int = 100,
        order_by: Optional[str] = None,
        order_desc: bool = True
    ) -> List[SystemHealth]:
        """
        Lấy danh sách báo cáo sức khỏe hệ thống theo các điều kiện tùy chỉnh.
        """
        query = db.query(SystemHealth)
        
        for field, value in conditions.items():
            if value is not None and hasattr(SystemHealth, field):
                if field == 'start_date':
                    query = query.filter(SystemHealth.created_at >= value)
                elif field == 'end_date':
                    query = query.filter(SystemHealth.created_at <= value)
                else:
                    query = query.filter(getattr(SystemHealth, field) == value)
        
        if order_by and hasattr(SystemHealth, order_by):
            if order_desc:
                query = query.order_by(desc(getattr(SystemHealth, order_by)))
            else:
                query = query.order_by(getattr(SystemHealth, order_by))
        
        return query.offset(skip).limit(limit).all()
    
    @staticmethod
    def create(db: Session, health_data: Dict[str, Any]) -> SystemHealth:
        """
        Tạo báo cáo sức khỏe hệ thống mới.
        
        Args:
            db: Database session
            health_data: Dữ liệu trạng thái
            
        Returns:
            SystemHealth object đã tạo
        """
        try:
            db_health = SystemHealth(**health_data)
            db.add(db_health)
            db.commit()
            db.refresh(db_health)
            logger.info(f"Đã tạo báo cáo sức khỏe hệ thống mới: {db_health.component} - {db_health.status}")
            return db_health
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi tạo báo cáo sức khỏe hệ thống: {str(e)}")
            raise e
    
    @staticmethod
    def update(db: Session, health_id: int, health_data: Dict[str, Any]) -> Optional[SystemHealth]:
        """
        Cập nhật thông tin báo cáo sức khỏe hệ thống.
        
        Args:
            db: Database session
            health_id: ID của trạng thái
            health_data: Dữ liệu cập nhật
            
        Returns:
            SystemHealth object đã cập nhật hoặc None nếu không tìm thấy
        """
        try:
            db_health = SystemHealthRepository.get_by_id(db, health_id)
            if not db_health:
                logger.warning(f"Không tìm thấy báo cáo sức khỏe hệ thống ID={health_id} để cập nhật")
                return None
            
            for key, value in health_data.items():
                setattr(db_health, key, value)
            
            db_health.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(db_health)
            logger.info(f"Đã cập nhật báo cáo sức khỏe hệ thống ID={health_id}")
            return db_health
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi cập nhật báo cáo sức khỏe hệ thống ID={health_id}: {str(e)}")
            raise e
    
    @staticmethod
    def delete(db: Session, health_id: int) -> bool:
        """
        Xóa báo cáo sức khỏe hệ thống.
        
        Args:
            db: Database session
            health_id: ID của trạng thái
            
        Returns:
            True nếu xóa thành công, False nếu không
        """
        try:
            db_health = SystemHealthRepository.get_by_id(db, health_id)
            if not db_health:
                logger.warning(f"Không tìm thấy báo cáo sức khỏe hệ thống ID={health_id} để xóa")
                return False
            
            db.delete(db_health)
            db.commit()
            logger.info(f"Đã xóa báo cáo sức khỏe hệ thống ID={health_id}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi xóa báo cáo sức khỏe hệ thống ID={health_id}: {str(e)}")
            raise e
    
    @staticmethod
    def get_latest(db: Session, component: Optional[str] = None) -> List[SystemHealth]:
        """
        Lấy trạng thái sức khỏe mới nhất của các thành phần hệ thống.
        """
        subquery = (
            db.query(
                SystemHealth.component,
                func.max(SystemHealth.created_at).label('max_created_at')
            )
            .group_by(SystemHealth.component)
        )
        
        if component:
            subquery = subquery.filter(SystemHealth.component == component)
        
        subquery = subquery.subquery('latest')
        
        query = (
            db.query(SystemHealth)
            .join(
                subquery,
                and_(
                    SystemHealth.component == subquery.c.component,
                    SystemHealth.created_at == subquery.c.max_created_at
                )
            )
        )
        
        return query.all()
