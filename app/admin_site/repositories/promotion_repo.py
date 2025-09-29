from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, desc
from typing import List, Optional, Dict, Any
from datetime import datetime

from app.admin_site.models import Promotion
from app.logging.setup import get_logger

logger = get_logger(__name__)

class PromotionRepository:
    """
    Repository để thao tác với Promotion trong cơ sở dữ liệu.
    """
    
    @staticmethod
    def get_by_id(db: Session, promotion_id: int) -> Optional[Promotion]:
        """
        Lấy khuyến mãi theo ID.
        """
        return db.query(Promotion).filter(Promotion.id == promotion_id).first()
    
    @staticmethod
    def get_by_code(db: Session, code: str) -> Optional[Promotion]:
        """
        Lấy khuyến mãi theo mã code.
        """
        return db.query(Promotion).filter(Promotion.coupon_code == code).first()
    
    @staticmethod
    def count(
        db: Session, 
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
        is_expired: Optional[bool] = None
    ) -> int:
        """
        Đếm số lượng khuyến mãi với các điều kiện lọc.
        """
        query = db.query(func.count(Promotion.id))
        now = datetime.now(timezone.utc)
        
        if search:
            query = query.filter(
                or_(
                    Promotion.name.ilike(f"%{search}%"),
                    Promotion.description.ilike(f"%{search}%"),
                    Promotion.coupon_code.ilike(f"%{search}%")
                )
            )
        
        if is_active is not None:
            query = query.filter(Promotion.is_active == is_active)
        
        if is_expired is not None:
            if is_expired:
                query = query.filter(Promotion.end_date < now)
            else:
                query = query.filter(or_(
                    Promotion.end_date >= now,
                    Promotion.end_date == None
                ))
        
        return query.scalar()
    
    @staticmethod
    def get_all(
        db: Session, 
        skip: int = 0, 
        limit: int = 100,
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
        is_expired: Optional[bool] = None,
        order_by: str = "created_at",
        order_desc: bool = True
    ) -> List[Promotion]:
        """
        Lấy danh sách khuyến mãi với các tùy chọn lọc.
        """
        query = db.query(Promotion)
        now = datetime.now(timezone.utc)
        
        if search:
            query = query.filter(
                or_(
                    Promotion.name.ilike(f"%{search}%"),
                    Promotion.description.ilike(f"%{search}%"),
                    Promotion.coupon_code.ilike(f"%{search}%")
                )
            )
        
        if is_active is not None:
            query = query.filter(Promotion.is_active == is_active)
        
        if is_expired is not None:
            if is_expired:
                query = query.filter(Promotion.end_date < now)
            else:
                query = query.filter(or_(
                    Promotion.end_date >= now,
                    Promotion.end_date == None
                ))
        
        # Xử lý sắp xếp
        if hasattr(Promotion, order_by):
            if order_desc:
                query = query.order_by(desc(getattr(Promotion, order_by)))
            else:
                query = query.order_by(getattr(Promotion, order_by))
        
        return query.offset(skip).limit(limit).all()
    
    @staticmethod
    def get_by_conditions(
        db: Session,
        conditions: Dict[str, Any],
        skip: int = 0,
        limit: int = 100,
        order_by: Optional[str] = None,
        order_desc: bool = True
    ) -> List[Promotion]:
        """
        Lấy danh sách khuyến mãi theo các điều kiện tùy chỉnh.
        """
        query = db.query(Promotion)
        now = datetime.now(timezone.utc)
        
        for field, value in conditions.items():
            if value is not None:
                if field == 'search':
                    query = query.filter(
                        or_(
                            Promotion.name.ilike(f"%{value}%"),
                            Promotion.description.ilike(f"%{value}%"),
                            Promotion.coupon_code.ilike(f"%{value}%")
                        )
                    )
                elif field == 'is_expired':
                    if value:
                        query = query.filter(Promotion.end_date < now)
                    else:
                        query = query.filter(or_(
                            Promotion.end_date >= now,
                            Promotion.end_date == None
                        ))
                elif hasattr(Promotion, field):
                    query = query.filter(getattr(Promotion, field) == value)
        
        if order_by and hasattr(Promotion, order_by):
            if order_desc:
                query = query.order_by(desc(getattr(Promotion, order_by)))
            else:
                query = query.order_by(getattr(Promotion, order_by))
        
        return query.offset(skip).limit(limit).all()
    
    @staticmethod
    def create(db: Session, promotion_data: Dict[str, Any]) -> Promotion:
        """
        Tạo khuyến mãi mới.
        """
        try:
            db_promotion = Promotion(**promotion_data)
            db.add(db_promotion)
            db.commit()
            db.refresh(db_promotion)
            logger.info(f"Đã tạo khuyến mãi mới: {db_promotion.name} (Code: {db_promotion.coupon_code})")
            return db_promotion
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi tạo khuyến mãi: {str(e)}")
            raise e
    
    @staticmethod
    def update(db: Session, promotion_id: int, promotion_data: Dict[str, Any]) -> Optional[Promotion]:
        """
        Cập nhật thông tin khuyến mãi.
        """
        try:
            db_promotion = PromotionRepository.get_by_id(db, promotion_id)
            if not db_promotion:
                logger.warning(f"Không tìm thấy khuyến mãi ID={promotion_id} để cập nhật")
                return None
            
            for key, value in promotion_data.items():
                setattr(db_promotion, key, value)
            
            db_promotion.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(db_promotion)
            logger.info(f"Đã cập nhật khuyến mãi ID={promotion_id}")
            return db_promotion
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi cập nhật khuyến mãi ID={promotion_id}: {str(e)}")
            raise e
    
    @staticmethod
    def delete(db: Session, promotion_id: int) -> bool:
        """
        Xóa khuyến mãi.
        """
        try:
            db_promotion = PromotionRepository.get_by_id(db, promotion_id)
            if not db_promotion:
                logger.warning(f"Không tìm thấy khuyến mãi ID={promotion_id} để xóa")
                return False
            
            db.delete(db_promotion)
            db.commit()
            logger.info(f"Đã xóa khuyến mãi ID={promotion_id}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi xóa khuyến mãi ID={promotion_id}: {str(e)}")
            raise e
    
    @staticmethod
    def increment_usage(db: Session, promotion_id: int) -> Optional[Promotion]:
        """
        Tăng số lượt sử dụng khuyến mãi.
        """
        try:
            db_promotion = PromotionRepository.get_by_id(db, promotion_id)
            if not db_promotion:
                logger.warning(f"Không tìm thấy khuyến mãi ID={promotion_id} để tăng lượt sử dụng")
                return None
            
            db_promotion.usage_count += 1
            db_promotion.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(db_promotion)
            logger.info(f"Đã tăng lượt sử dụng khuyến mãi ID={promotion_id} lên {db_promotion.usage_count}")
            return db_promotion
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi tăng lượt sử dụng khuyến mãi ID={promotion_id}: {str(e)}")
            raise e
    
    @staticmethod
    def toggle_status(db: Session, promotion_id: int) -> Optional[Promotion]:
        """
        Bật/tắt trạng thái của khuyến mãi.
        """
        try:
            db_promotion = PromotionRepository.get_by_id(db, promotion_id)
            if not db_promotion:
                logger.warning(f"Không tìm thấy khuyến mãi ID={promotion_id} để thay đổi trạng thái")
                return None
            
            db_promotion.is_active = not db_promotion.is_active
            db_promotion.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(db_promotion)
            logger.info(f"Đã thay đổi trạng thái khuyến mãi ID={promotion_id} thành {db_promotion.is_active}")
            return db_promotion
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi thay đổi trạng thái khuyến mãi ID={promotion_id}: {str(e)}")
            raise e
    
    @staticmethod
    def get_valid(db: Session, skip: int = 0, limit: int = 100) -> List[Promotion]:
        """
        Lấy danh sách khuyến mãi còn hiệu lực.
        """
        now = datetime.now(timezone.utc)
        query = (
            db.query(Promotion)
            .filter(
                Promotion.is_active == True,
                Promotion.start_date <= now,
                or_(
                    Promotion.end_date >= now,
                    Promotion.end_date == None
                )
            )
            .order_by(desc(Promotion.created_at))
        )
        
        return query.offset(skip).limit(limit).all()
