from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, desc
from typing import List, Optional, Dict, Any
from datetime import datetime

from app.admin_site.models import Achievement
from app.logging.setup import get_logger

logger = get_logger(__name__)

class AchievementRepository:
    """
    Repository để thao tác với Achievement trong cơ sở dữ liệu.
    """
    
    @staticmethod
    def get_by_id(db: Session, achievement_id: int) -> Optional[Achievement]:
        """
        Lấy thành tựu theo ID.
        
        Args:
            db: Database session
            achievement_id: ID của thành tựu
            
        Returns:
            Achievement object nếu tìm thấy, None nếu không
        """
        return db.query(Achievement).filter(Achievement.id == achievement_id).first()
    
    @staticmethod
    def get_by_name(db: Session, name: str) -> Optional[Achievement]:
        """
        Lấy thành tựu theo tên.
        
        Args:
            db: Database session
            name: Tên của thành tựu
            
        Returns:
            Achievement object nếu tìm thấy, None nếu không
        """
        return db.query(Achievement).filter(Achievement.name == name).first()
    
    @staticmethod
    def count(
        db: Session, 
        search: Optional[str] = None,
        difficulty_level: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> int:
        """
        Đếm số lượng thành tựu với các điều kiện lọc.
        
        Args:
            db: Database session
            search: Tìm kiếm theo tên, mô tả
            difficulty_level: Mức độ khó
            is_active: Trạng thái kích hoạt
            
        Returns:
            Số lượng thành tựu
        """
        query = db.query(func.count(Achievement.id))
        
        if search:
            query = query.filter(
                or_(
                    Achievement.name.ilike(f"%{search}%"),
                    Achievement.description.ilike(f"%{search}%")
                )
            )
        
        if difficulty_level:
            query = query.filter(Achievement.difficulty_level == difficulty_level)
        
        if is_active is not None:
            query = query.filter(Achievement.is_active == is_active)
        
        return query.scalar()
    
    @staticmethod
    def get_all(
        db: Session, 
        skip: int = 0, 
        limit: int = 100,
        search: Optional[str] = None,
        difficulty_level: Optional[str] = None,
        is_active: Optional[bool] = None,
        order_by: str = "name",
        order_desc: bool = False
    ) -> List[Achievement]:
        """
        Lấy danh sách thành tựu với các tùy chọn lọc.
        
        Args:
            db: Database session
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa
            search: Tìm kiếm theo tên, mô tả
            difficulty_level: Mức độ khó
            is_active: Trạng thái kích hoạt
            order_by: Trường sắp xếp
            order_desc: Sắp xếp theo thứ tự giảm dần
            
        Returns:
            Danh sách thành tựu
        """
        query = db.query(Achievement)
        
        if search:
            query = query.filter(
                or_(
                    Achievement.name.ilike(f"%{search}%"),
                    Achievement.description.ilike(f"%{search}%")
                )
            )
        
        if difficulty_level:
            query = query.filter(Achievement.difficulty_level == difficulty_level)
        
        if is_active is not None:
            query = query.filter(Achievement.is_active == is_active)
        
        # Xử lý sắp xếp
        if hasattr(Achievement, order_by):
            if order_desc:
                query = query.order_by(desc(getattr(Achievement, order_by)))
            else:
                query = query.order_by(getattr(Achievement, order_by))
        
        return query.offset(skip).limit(limit).all()
    
    @staticmethod
    def get_by_conditions(
        db: Session,
        conditions: Dict[str, Any],
        skip: int = 0,
        limit: int = 100,
        order_by: Optional[str] = None,
        order_desc: bool = False
    ) -> List[Achievement]:
        """
        Lấy danh sách thành tựu theo các điều kiện tùy chỉnh.
        
        Args:
            db: Database session
            conditions: Các điều kiện tùy chỉnh
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa
            order_by: Trường sắp xếp
            order_desc: Sắp xếp theo thứ tự giảm dần
            
        Returns:
            Danh sách thành tựu
        """
        query = db.query(Achievement)
        
        for field, value in conditions.items():
            if value is not None:
                if field == 'search':
                    query = query.filter(
                        or_(
                            Achievement.name.ilike(f"%{value}%"),
                            Achievement.description.ilike(f"%{value}%")
                        )
                    )
                elif hasattr(Achievement, field):
                    query = query.filter(getattr(Achievement, field) == value)
        
        if order_by and hasattr(Achievement, order_by):
            if order_desc:
                query = query.order_by(desc(getattr(Achievement, order_by)))
            else:
                query = query.order_by(getattr(Achievement, order_by))
        
        return query.offset(skip).limit(limit).all()
    
    @staticmethod
    def create(db: Session, achievement_data: Dict[str, Any]) -> Achievement:
        """
        Tạo thành tựu mới.
        
        Args:
            db: Database session
            achievement_data: Dữ liệu thành tựu
            
        Returns:
            Achievement object đã tạo
        """
        try:
            db_achievement = Achievement(**achievement_data)
            db.add(db_achievement)
            db.commit()
            db.refresh(db_achievement)
            logger.info(f"Đã tạo thành tựu mới: {db_achievement.name}")
            return db_achievement
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi tạo thành tựu: {str(e)}")
            raise e
    
    @staticmethod
    def update(db: Session, achievement_id: int, achievement_data: Dict[str, Any]) -> Optional[Achievement]:
        """
        Cập nhật thông tin thành tựu.
        
        Args:
            db: Database session
            achievement_id: ID của thành tựu
            achievement_data: Dữ liệu cập nhật
            
        Returns:
            Achievement object đã cập nhật hoặc None nếu không tìm thấy
        """
        try:
            db_achievement = AchievementRepository.get_by_id(db, achievement_id)
            if not db_achievement:
                logger.warning(f"Không tìm thấy thành tựu ID={achievement_id} để cập nhật")
                return None
            
            for key, value in achievement_data.items():
                setattr(db_achievement, key, value)
            
            db_achievement.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(db_achievement)
            logger.info(f"Đã cập nhật thành tựu ID={achievement_id}")
            return db_achievement
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi cập nhật thành tựu ID={achievement_id}: {str(e)}")
            raise e
    
    @staticmethod
    def delete(db: Session, achievement_id: int) -> bool:
        """
        Xóa thành tựu.
        
        Args:
            db: Database session
            achievement_id: ID của thành tựu
            
        Returns:
            True nếu xóa thành công, False nếu không
        """
        try:
            db_achievement = AchievementRepository.get_by_id(db, achievement_id)
            if not db_achievement:
                logger.warning(f"Không tìm thấy thành tựu ID={achievement_id} để xóa")
                return False
            
            db.delete(db_achievement)
            db.commit()
            logger.info(f"Đã xóa thành tựu ID={achievement_id}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi xóa thành tựu ID={achievement_id}: {str(e)}")
            raise e
    
    @staticmethod
    def toggle_status(db: Session, achievement_id: int) -> Optional[Achievement]:
        """
        Bật/tắt trạng thái của thành tựu.
        
        Args:
            db: Database session
            achievement_id: ID của thành tựu
            
        Returns:
            Achievement object đã cập nhật hoặc None nếu không tìm thấy
        """
        try:
            db_achievement = AchievementRepository.get_by_id(db, achievement_id)
            if not db_achievement:
                logger.warning(f"Không tìm thấy thành tựu ID={achievement_id} để thay đổi trạng thái")
                return None
            
            db_achievement.is_active = not db_achievement.is_active
            db_achievement.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(db_achievement)
            logger.info(f"Đã thay đổi trạng thái thành tựu ID={achievement_id} thành {db_achievement.is_active}")
            return db_achievement
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi thay đổi trạng thái thành tựu ID={achievement_id}: {str(e)}")
            raise e
