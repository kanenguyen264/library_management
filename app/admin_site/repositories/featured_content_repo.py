from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, desc
from typing import List, Optional, Dict, Any
from datetime import datetime

from app.admin_site.models import FeaturedContent
from app.logging.setup import get_logger

logger = get_logger(__name__)

class FeaturedContentRepository:
    """
    Repository để thao tác với FeaturedContent trong cơ sở dữ liệu.
    """
    
    @staticmethod
    def get_by_id(db: Session, content_id: int) -> Optional[FeaturedContent]:
        """
        Lấy nội dung nổi bật theo ID.
        
        Args:
            db: Database session
            content_id: ID của nội dung nổi bật
            
        Returns:
            FeaturedContent object nếu tìm thấy, None nếu không
        """
        return db.query(FeaturedContent).filter(FeaturedContent.id == content_id).first()
    
    @staticmethod
    def count(
        db: Session, 
        content_type: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> int:
        """
        Đếm số lượng nội dung nổi bật với các điều kiện lọc.
        """
        query = db.query(func.count(FeaturedContent.id))
        
        if content_type:
            query = query.filter(FeaturedContent.content_type == content_type)
        
        if is_active is not None:
            query = query.filter(FeaturedContent.is_active == is_active)
        
        return query.scalar()
    
    @staticmethod
    def get_all(
        db: Session, 
        skip: int = 0, 
        limit: int = 100,
        content_type: Optional[str] = None,
        is_active: Optional[bool] = None,
        order_by: str = "position",
        order_desc: bool = False
    ) -> List[FeaturedContent]:
        """
        Lấy danh sách nội dung nổi bật với các tùy chọn lọc.
        
        Args:
            db: Database session
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa
            content_type: Loại nội dung
            is_active: Chỉ lấy nội dung đang active
            
        Returns:
            Danh sách nội dung nổi bật
        """
        query = db.query(FeaturedContent)
        
        if content_type:
            query = query.filter(FeaturedContent.content_type == content_type)
        
        if is_active is not None:
            query = query.filter(FeaturedContent.is_active == is_active)
        
        # Xử lý sắp xếp
        if hasattr(FeaturedContent, order_by):
            if order_desc:
                query = query.order_by(desc(getattr(FeaturedContent, order_by)))
            else:
                query = query.order_by(getattr(FeaturedContent, order_by))
        
        return query.offset(skip).limit(limit).all()
    
    @staticmethod
    def get_by_conditions(
        db: Session,
        conditions: Dict[str, Any],
        skip: int = 0,
        limit: int = 100,
        order_by: Optional[str] = None,
        order_desc: bool = False
    ) -> List[FeaturedContent]:
        """
        Lấy danh sách nội dung nổi bật theo các điều kiện tùy chỉnh.
        """
        query = db.query(FeaturedContent)
        
        for field, value in conditions.items():
            if value is not None and hasattr(FeaturedContent, field):
                query = query.filter(getattr(FeaturedContent, field) == value)
        
        if order_by and hasattr(FeaturedContent, order_by):
            if order_desc:
                query = query.order_by(desc(getattr(FeaturedContent, order_by)))
            else:
                query = query.order_by(getattr(FeaturedContent, order_by))
        
        return query.offset(skip).limit(limit).all()
    
    @staticmethod
    def get_by_content(db: Session, content_type: str, content_id: int) -> Optional[FeaturedContent]:
        """
        Lấy nội dung nổi bật theo nội dung gốc.
        
        Args:
            db: Database session
            content_type: Loại nội dung
            content_id: ID nội dung gốc
            
        Returns:
            FeaturedContent object nếu tìm thấy, None nếu không
        """
        return (
            db.query(FeaturedContent)
            .filter(
                FeaturedContent.content_type == content_type,
                FeaturedContent.content_id == content_id
            )
            .first()
        )
    
    @staticmethod
    def create(db: Session, content_data: Dict[str, Any]) -> FeaturedContent:
        """
        Tạo nội dung nổi bật mới.
        
        Args:
            db: Database session
            content_data: Dữ liệu nội dung
            
        Returns:
            FeaturedContent object đã tạo
        """
        try:
            db_content = FeaturedContent(**content_data)
            db.add(db_content)
            db.commit()
            db.refresh(db_content)
            logger.info(f"Đã tạo nội dung nổi bật mới: {db_content.title}")
            return db_content
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi tạo nội dung nổi bật: {str(e)}")
            raise e
    
    @staticmethod
    def update(db: Session, content_id: int, content_data: Dict[str, Any]) -> Optional[FeaturedContent]:
        """
        Cập nhật thông tin nội dung nổi bật.
        
        Args:
            db: Database session
            content_id: ID của nội dung nổi bật
            content_data: Dữ liệu cập nhật
            
        Returns:
            FeaturedContent object đã cập nhật hoặc None nếu không tìm thấy
        """
        try:
            db_content = FeaturedContentRepository.get_by_id(db, content_id)
            if not db_content:
                logger.warning(f"Không tìm thấy nội dung nổi bật ID={content_id} để cập nhật")
                return None
            
            for key, value in content_data.items():
                setattr(db_content, key, value)
            
            db_content.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(db_content)
            logger.info(f"Đã cập nhật nội dung nổi bật ID={content_id}")
            return db_content
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi cập nhật nội dung nổi bật ID={content_id}: {str(e)}")
            raise e
    
    @staticmethod
    def delete(db: Session, content_id: int) -> bool:
        """
        Xóa nội dung nổi bật.
        
        Args:
            db: Database session
            content_id: ID của nội dung nổi bật
            
        Returns:
            True nếu xóa thành công, False nếu không
        """
        try:
            db_content = FeaturedContentRepository.get_by_id(db, content_id)
            if not db_content:
                logger.warning(f"Không tìm thấy nội dung nổi bật ID={content_id} để xóa")
                return False
            
            db.delete(db_content)
            db.commit()
            logger.info(f"Đã xóa nội dung nổi bật ID={content_id}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi xóa nội dung nổi bật ID={content_id}: {str(e)}")
            raise e
    
    @staticmethod
    def toggle_status(db: Session, content_id: int) -> Optional[FeaturedContent]:
        """
        Bật/tắt trạng thái của nội dung nổi bật.
        
        Args:
            db: Database session
            content_id: ID của nội dung nổi bật
            
        Returns:
            FeaturedContent object đã cập nhật hoặc None nếu không tìm thấy
        """
        try:
            db_content = FeaturedContentRepository.get_by_id(db, content_id)
            if not db_content:
                logger.warning(f"Không tìm thấy nội dung nổi bật ID={content_id} để thay đổi trạng thái")
                return None
            
            db_content.is_active = not db_content.is_active
            db_content.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(db_content)
            logger.info(f"Đã thay đổi trạng thái nội dung nổi bật ID={content_id} thành {db_content.is_active}")
            return db_content
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi thay đổi trạng thái nội dung nổi bật ID={content_id}: {str(e)}")
            raise e
    
    @staticmethod
    def reorder(db: Session, content_type: str, position_updates: Dict[int, int]) -> bool:
        """
        Sắp xếp lại thứ tự nội dung nổi bật.
        """
        try:
            for content_id, position in position_updates.items():
                db_content = FeaturedContentRepository.get_by_id(db, content_id)
                if db_content and db_content.content_type == content_type:
                    db_content.position = position
                    db_content.updated_at = datetime.now(timezone.utc)
            
            db.commit()
            logger.info(f"Đã sắp xếp lại thứ tự nội dung nổi bật loại {content_type}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi sắp xếp lại thứ tự nội dung nổi bật: {str(e)}")
            raise e
    
    @staticmethod
    def get_active(db: Session, content_type: Optional[str] = None) -> List[FeaturedContent]:
        """
        Lấy danh sách nội dung nổi bật đang kích hoạt.
        """
        now = datetime.now(timezone.utc)
        query = db.query(FeaturedContent).filter(
            FeaturedContent.is_active == True,
            FeaturedContent.start_date <= now,
            or_(
                FeaturedContent.end_date >= now,
                FeaturedContent.end_date == None
            )
        )
        
        if content_type:
            query = query.filter(FeaturedContent.content_type == content_type)
            
        return query.order_by(FeaturedContent.position).all()