from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, desc
from typing import List, Optional, Dict, Any
from datetime import datetime

from app.admin_site.models import Badge
from app.logging.setup import get_logger

logger = get_logger(__name__)

class BadgeRepository:
    """
    Repository để thao tác với Badge trong cơ sở dữ liệu.
    """
    
    @staticmethod
    def get_by_id(db: Session, badge_id: int) -> Optional[Badge]:
        """
        Lấy huy hiệu theo ID.
        
        Args:
            db: Database session
            badge_id: ID của huy hiệu
            
        Returns:
            Badge object nếu tìm thấy, None nếu không
        """
        return db.query(Badge).filter(Badge.id == badge_id).first()
    
    @staticmethod
    def get_by_name(db: Session, name: str) -> Optional[Badge]:
        """
        Lấy huy hiệu theo tên.
        
        Args:
            db: Database session
            name: Tên của huy hiệu
            
        Returns:
            Badge object nếu tìm thấy, None nếu không
        """
        return db.query(Badge).filter(Badge.name == name).first()
    
    @staticmethod
    def count(
        db: Session, 
        search: Optional[str] = None,
        badge_type: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> int:
        """
        Đếm số lượng huy hiệu với các điều kiện lọc.
        """
        query = db.query(func.count(Badge.id))
        
        if search:
            query = query.filter(
                or_(
                    Badge.name.ilike(f"%{search}%"),
                    Badge.description.ilike(f"%{search}%")
                )
            )
        
        if badge_type:
            query = query.filter(Badge.badge_type == badge_type)
        
        if is_active is not None:
            query = query.filter(Badge.is_active == is_active)
        
        return query.scalar()
    
    @staticmethod
    def get_all(
        db: Session, 
        skip: int = 0, 
        limit: int = 100,
        search: Optional[str] = None,
        badge_type: Optional[str] = None,
        is_active: Optional[bool] = None,
        order_by: str = "name",
        order_desc: bool = False
    ) -> List[Badge]:
        """
        Lấy danh sách huy hiệu với các tùy chọn lọc.
        
        Args:
            db: Database session
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa
            search: Tìm kiếm theo tên, mô tả
            badge_type: Loại huy hiệu
            is_active: Trạng thái kích hoạt
            
        Returns:
            Danh sách huy hiệu
        """
        query = db.query(Badge)
        
        if search:
            query = query.filter(
                or_(
                    Badge.name.ilike(f"%{search}%"),
                    Badge.description.ilike(f"%{search}%")
                )
            )
        
        if badge_type:
            query = query.filter(Badge.badge_type == badge_type)
        
        if is_active is not None:
            query = query.filter(Badge.is_active == is_active)
        
        # Xử lý sắp xếp
        if hasattr(Badge, order_by):
            if order_desc:
                query = query.order_by(desc(getattr(Badge, order_by)))
            else:
                query = query.order_by(getattr(Badge, order_by))
        
        return query.offset(skip).limit(limit).all()
    
    @staticmethod
    def get_by_conditions(
        db: Session,
        conditions: Dict[str, Any],
        skip: int = 0,
        limit: int = 100,
        order_by: Optional[str] = None,
        order_desc: bool = False
    ) -> List[Badge]:
        """
        Lấy danh sách huy hiệu theo các điều kiện tùy chỉnh.
        """
        query = db.query(Badge)
        
        for field, value in conditions.items():
            if value is not None:
                if field == 'search':
                    query = query.filter(
                        or_(
                            Badge.name.ilike(f"%{value}%"),
                            Badge.description.ilike(f"%{value}%")
                        )
                    )
                elif hasattr(Badge, field):
                    query = query.filter(getattr(Badge, field) == value)
        
        if order_by and hasattr(Badge, order_by):
            if order_desc:
                query = query.order_by(desc(getattr(Badge, order_by)))
            else:
                query = query.order_by(getattr(Badge, order_by))
        
        return query.offset(skip).limit(limit).all()
    
    @staticmethod
    def create(db: Session, badge_data: Dict[str, Any]) -> Badge:
        """
        Tạo huy hiệu mới.
        
        Args:
            db: Database session
            badge_data: Dữ liệu huy hiệu
            
        Returns:
            Badge object đã tạo
        """
        try:
            db_badge = Badge(**badge_data)
            db.add(db_badge)
            db.commit()
            db.refresh(db_badge)
            logger.info(f"Đã tạo huy hiệu mới: {db_badge.name}")
            return db_badge
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi tạo huy hiệu: {str(e)}")
            raise e
    
    @staticmethod
    def update(db: Session, badge_id: int, badge_data: Dict[str, Any]) -> Optional[Badge]:
        """
        Cập nhật thông tin huy hiệu.
        
        Args:
            db: Database session
            badge_id: ID của huy hiệu
            badge_data: Dữ liệu cập nhật
            
        Returns:
            Badge object đã cập nhật hoặc None nếu không tìm thấy
        """
        try:
            db_badge = BadgeRepository.get_by_id(db, badge_id)
            if not db_badge:
                logger.warning(f"Không tìm thấy huy hiệu ID={badge_id} để cập nhật")
                return None
            
            for key, value in badge_data.items():
                setattr(db_badge, key, value)
            
            db_badge.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(db_badge)
            logger.info(f"Đã cập nhật huy hiệu ID={badge_id}")
            return db_badge
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi cập nhật huy hiệu ID={badge_id}: {str(e)}")
            raise e
    
    @staticmethod
    def delete(db: Session, badge_id: int) -> bool:
        """
        Xóa huy hiệu.
        
        Args:
            db: Database session
            badge_id: ID của huy hiệu
            
        Returns:
            True nếu xóa thành công, False nếu không
        """
        try:
            db_badge = BadgeRepository.get_by_id(db, badge_id)
            if not db_badge:
                logger.warning(f"Không tìm thấy huy hiệu ID={badge_id} để xóa")
                return False
            
            db.delete(db_badge)
            db.commit()
            logger.info(f"Đã xóa huy hiệu ID={badge_id}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi xóa huy hiệu ID={badge_id}: {str(e)}")
            raise e
    
    @staticmethod
    def toggle_status(db: Session, badge_id: int) -> Optional[Badge]:
        """
        Bật/tắt trạng thái của huy hiệu.
        
        Args:
            db: Database session
            badge_id: ID của huy hiệu
            
        Returns:
            Badge object đã cập nhật hoặc None nếu không tìm thấy
        """
        try:
            db_badge = BadgeRepository.get_by_id(db, badge_id)
            if not db_badge:
                logger.warning(f"Không tìm thấy huy hiệu ID={badge_id} để thay đổi trạng thái")
                return None
            
            db_badge.is_active = not db_badge.is_active
            db_badge.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(db_badge)
            logger.info(f"Đã thay đổi trạng thái huy hiệu ID={badge_id} thành {db_badge.is_active}")
            return db_badge
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi thay đổi trạng thái huy hiệu ID={badge_id}: {str(e)}")
            raise e
