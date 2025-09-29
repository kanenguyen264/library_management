from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, desc
from typing import List, Optional, Dict, Any
from datetime import datetime

from app.admin_site.models import SystemSetting
from app.logging.setup import get_logger

logger = get_logger(__name__)

class SystemSettingRepository:
    """
    Repository để thao tác với SystemSetting trong cơ sở dữ liệu.
    """
    
    @staticmethod
    def get_by_id(db: Session, setting_id: int) -> Optional[SystemSetting]:
        """
        Lấy cài đặt hệ thống theo ID.
        
        Args:
            db: Database session
            setting_id: ID của cài đặt
            
        Returns:
            SystemSetting object nếu tìm thấy, None nếu không
        """
        return db.query(SystemSetting).filter(SystemSetting.id == setting_id).first()
    
    @staticmethod
    def get_by_key(db: Session, key: str) -> Optional[SystemSetting]:
        """
        Lấy cài đặt hệ thống theo khóa.
        
        Args:
            db: Database session
            key: Khóa của cài đặt
            
        Returns:
            SystemSetting object nếu tìm thấy, None nếu không
        """
        return db.query(SystemSetting).filter(SystemSetting.key == key).first()
    
    @staticmethod
    def count(
        db: Session, 
        search: Optional[str] = None,
        group: Optional[str] = None,
        is_public: Optional[bool] = None
    ) -> int:
        """
        Đếm số lượng cài đặt hệ thống với các điều kiện lọc.
        """
        query = db.query(func.count(SystemSetting.id))
        
        if search:
            query = query.filter(
                or_(
                    SystemSetting.key.ilike(f"%{search}%"),
                    SystemSetting.description.ilike(f"%{search}%"),
                    SystemSetting.value.ilike(f"%{search}%")
                )
            )
        
        if group:
            query = query.filter(SystemSetting.group == group)
            
        if is_public is not None:
            query = query.filter(SystemSetting.is_public == is_public)
        
        return query.scalar()
    
    @staticmethod
    def get_all(
        db: Session, 
        skip: int = 0, 
        limit: int = 100,
        search: Optional[str] = None,
        group: Optional[str] = None,
        is_public: Optional[bool] = None,
        order_by: str = "key",
        order_desc: bool = False
    ) -> List[SystemSetting]:
        """
        Lấy danh sách cài đặt hệ thống với các tùy chọn lọc.
        """
        query = db.query(SystemSetting)
        
        if search:
            query = query.filter(
                or_(
                    SystemSetting.key.ilike(f"%{search}%"),
                    SystemSetting.description.ilike(f"%{search}%"),
                    SystemSetting.value.ilike(f"%{search}%")
                )
            )
        
        if group:
            query = query.filter(SystemSetting.group == group)
            
        if is_public is not None:
            query = query.filter(SystemSetting.is_public == is_public)
        
        # Xử lý sắp xếp
        if hasattr(SystemSetting, order_by):
            if order_desc:
                query = query.order_by(desc(getattr(SystemSetting, order_by)))
            else:
                query = query.order_by(getattr(SystemSetting, order_by))
        
        return query.offset(skip).limit(limit).all()
    
    @staticmethod
    def get_by_conditions(
        db: Session,
        conditions: Dict[str, Any],
        skip: int = 0,
        limit: int = 100,
        order_by: Optional[str] = None,
        order_desc: bool = False
    ) -> List[SystemSetting]:
        """
        Lấy danh sách cài đặt hệ thống theo các điều kiện tùy chỉnh.
        """
        query = db.query(SystemSetting)
        
        for field, value in conditions.items():
            if value is not None:
                if field == 'search':
                    query = query.filter(
                        or_(
                            SystemSetting.key.ilike(f"%{value}%"),
                            SystemSetting.description.ilike(f"%{value}%"),
                            SystemSetting.value.ilike(f"%{value}%")
                        )
                    )
                elif hasattr(SystemSetting, field):
                    query = query.filter(getattr(SystemSetting, field) == value)
        
        if order_by and hasattr(SystemSetting, order_by):
            if order_desc:
                query = query.order_by(desc(getattr(SystemSetting, order_by)))
            else:
                query = query.order_by(getattr(SystemSetting, order_by))
        
        return query.offset(skip).limit(limit).all()
    
    @staticmethod
    def get_by_group(db: Session, group: str) -> List[SystemSetting]:
        """
        Lấy danh sách cài đặt hệ thống theo nhóm.
        
        Args:
            db: Database session
            group: Nhóm cài đặt
            
        Returns:
            Danh sách cài đặt hệ thống
        """
        return db.query(SystemSetting).filter(SystemSetting.group == group).all()
    
    @staticmethod
    def create(db: Session, setting_data: Dict[str, Any]) -> SystemSetting:
        """
        Tạo cài đặt hệ thống mới.
        
        Args:
            db: Database session
            setting_data: Dữ liệu cài đặt
            
        Returns:
            SystemSetting object đã tạo
        """
        try:
            db_setting = SystemSetting(**setting_data)
            db.add(db_setting)
            db.commit()
            db.refresh(db_setting)
            logger.info(f"Đã tạo cài đặt hệ thống mới: {db_setting.key}")
            return db_setting
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi tạo cài đặt hệ thống: {str(e)}")
            raise e
    
    @staticmethod
    def update(db: Session, setting_id: int, setting_data: Dict[str, Any]) -> Optional[SystemSetting]:
        """
        Cập nhật thông tin cài đặt hệ thống.
        
        Args:
            db: Database session
            setting_id: ID của cài đặt
            setting_data: Dữ liệu cập nhật
            
        Returns:
            SystemSetting object đã cập nhật hoặc None nếu không tìm thấy
        """
        try:
            db_setting = SystemSettingRepository.get_by_id(db, setting_id)
            if not db_setting:
                logger.warning(f"Không tìm thấy cài đặt hệ thống ID={setting_id} để cập nhật")
                return None
            
            for key, value in setting_data.items():
                setattr(db_setting, key, value)
            
            db_setting.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(db_setting)
            logger.info(f"Đã cập nhật cài đặt hệ thống ID={setting_id}")
            return db_setting
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi cập nhật cài đặt hệ thống ID={setting_id}: {str(e)}")
            raise e
    
    @staticmethod
    def update_by_key(db: Session, key: str, value: str) -> Optional[SystemSetting]:
        """
        Cập nhật giá trị cài đặt hệ thống theo khóa.
        
        Args:
            db: Database session
            key: Khóa của cài đặt
            value: Giá trị mới
            
        Returns:
            SystemSetting object đã cập nhật hoặc None nếu không tìm thấy
        """
        try:
            db_setting = SystemSettingRepository.get_by_key(db, key)
            if not db_setting:
                logger.warning(f"Không tìm thấy cài đặt hệ thống key={key} để cập nhật")
                return None
            
            db_setting.value = value
            db_setting.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(db_setting)
            logger.info(f"Đã cập nhật cài đặt hệ thống key={key}")
            return db_setting
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi cập nhật cài đặt hệ thống key={key}: {str(e)}")
            raise e
    
    @staticmethod
    def delete(db: Session, setting_id: int) -> bool:
        """
        Xóa cài đặt hệ thống.
        
        Args:
            db: Database session
            setting_id: ID của cài đặt
            
        Returns:
            True nếu xóa thành công, False nếu không
        """
        try:
            db_setting = SystemSettingRepository.get_by_id(db, setting_id)
            if not db_setting:
                logger.warning(f"Không tìm thấy cài đặt hệ thống ID={setting_id} để xóa")
                return False
            
            db.delete(db_setting)
            db.commit()
            logger.info(f"Đã xóa cài đặt hệ thống ID={setting_id}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi xóa cài đặt hệ thống ID={setting_id}: {str(e)}")
            raise e
    
    @staticmethod
    def get_groups(db: Session) -> List[str]:
        """
        Lấy danh sách các nhóm cài đặt hệ thống.
        """
        try:
            results = db.query(SystemSetting.group).distinct().order_by(SystemSetting.group).all()
            return [result[0] for result in results if result[0] is not None]
        except Exception as e:
            logger.error(f"Lỗi khi lấy danh sách nhóm cài đặt: {str(e)}")
            raise e
