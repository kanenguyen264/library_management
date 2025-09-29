from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, desc
from typing import List, Optional, Dict, Any
from datetime import datetime

from app.admin_site.models import ContentApprovalQueue
from app.logging.setup import get_logger

logger = get_logger(__name__)

class ContentApprovalRepository:
    """
    Repository để thao tác với ContentApprovalQueue trong cơ sở dữ liệu.
    """
    
    @staticmethod
    def get_by_id(db: Session, approval_id: int) -> Optional[ContentApprovalQueue]:
        """
        Lấy đơn phê duyệt nội dung theo ID.
        """
        return db.query(ContentApprovalQueue).filter(ContentApprovalQueue.id == approval_id).first()
    
    @staticmethod
    def count(
        db: Session, 
        content_type: Optional[str] = None,
        status: Optional[str] = None,
        submitted_by: Optional[int] = None,
        reviewer_id: Optional[int] = None
    ) -> int:
        """
        Đếm số lượng đơn phê duyệt với các điều kiện lọc.
        """
        query = db.query(func.count(ContentApprovalQueue.id))
        
        if content_type:
            query = query.filter(ContentApprovalQueue.content_type == content_type)
        
        if status:
            query = query.filter(ContentApprovalQueue.status == status)
        
        if submitted_by:
            query = query.filter(ContentApprovalQueue.submitted_by == submitted_by)
        
        if reviewer_id:
            query = query.filter(ContentApprovalQueue.reviewer_id == reviewer_id)
        
        return query.scalar()
    
    @staticmethod
    def get_all(
        db: Session, 
        skip: int = 0, 
        limit: int = 100,
        content_type: Optional[str] = None,
        status: Optional[str] = None,
        submitted_by: Optional[int] = None,
        reviewer_id: Optional[int] = None,
        order_by: str = "created_at",
        order_desc: bool = True
    ) -> List[ContentApprovalQueue]:
        """
        Lấy danh sách đơn phê duyệt nội dung với các tùy chọn lọc.
        """
        query = db.query(ContentApprovalQueue)
        
        if content_type:
            query = query.filter(ContentApprovalQueue.content_type == content_type)
        
        if status:
            query = query.filter(ContentApprovalQueue.status == status)
        
        if submitted_by:
            query = query.filter(ContentApprovalQueue.submitted_by == submitted_by)
        
        if reviewer_id:
            query = query.filter(ContentApprovalQueue.reviewer_id == reviewer_id)
        
        # Xử lý sắp xếp
        if hasattr(ContentApprovalQueue, order_by):
            if order_desc:
                query = query.order_by(desc(getattr(ContentApprovalQueue, order_by)))
            else:
                query = query.order_by(getattr(ContentApprovalQueue, order_by))
        
        return query.offset(skip).limit(limit).all()
    
    @staticmethod
    def get_by_conditions(
        db: Session,
        conditions: Dict[str, Any],
        skip: int = 0,
        limit: int = 100,
        order_by: Optional[str] = None,
        order_desc: bool = True
    ) -> List[ContentApprovalQueue]:
        """
        Lấy danh sách đơn phê duyệt theo các điều kiện tùy chỉnh.
        """
        query = db.query(ContentApprovalQueue)
        
        for field, value in conditions.items():
            if value is not None and hasattr(ContentApprovalQueue, field):
                query = query.filter(getattr(ContentApprovalQueue, field) == value)
        
        if order_by and hasattr(ContentApprovalQueue, order_by):
            if order_desc:
                query = query.order_by(desc(getattr(ContentApprovalQueue, order_by)))
            else:
                query = query.order_by(getattr(ContentApprovalQueue, order_by))
        
        return query.offset(skip).limit(limit).all()
    
    @staticmethod
    def get_by_content(db: Session, content_type: str, content_id: int) -> List[ContentApprovalQueue]:
        """
        Lấy đơn phê duyệt theo nội dung.
        """
        return (
            db.query(ContentApprovalQueue)
            .filter(
                ContentApprovalQueue.content_type == content_type,
                ContentApprovalQueue.content_id == content_id
            )
            .all()
        )
    
    @staticmethod
    def create(db: Session, approval_data: Dict[str, Any]) -> ContentApprovalQueue:
        """
        Tạo đơn phê duyệt nội dung mới.
        """
        try:
            db_approval = ContentApprovalQueue(**approval_data)
            db.add(db_approval)
            db.commit()
            db.refresh(db_approval)
            logger.info(f"Đã tạo đơn phê duyệt nội dung mới: {db_approval.content_type} - ID={db_approval.id}")
            return db_approval
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi tạo đơn phê duyệt nội dung: {str(e)}")
            raise e
    
    @staticmethod
    def update(db: Session, approval_id: int, approval_data: Dict[str, Any]) -> Optional[ContentApprovalQueue]:
        """
        Cập nhật thông tin đơn phê duyệt nội dung.
        """
        try:
            db_approval = ContentApprovalRepository.get_by_id(db, approval_id)
            if not db_approval:
                logger.warning(f"Không tìm thấy đơn phê duyệt ID={approval_id} để cập nhật")
                return None
            
            for key, value in approval_data.items():
                setattr(db_approval, key, value)
            
            db_approval.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(db_approval)
            logger.info(f"Đã cập nhật đơn phê duyệt ID={approval_id}")
            return db_approval
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi cập nhật đơn phê duyệt ID={approval_id}: {str(e)}")
            raise e
    
    @staticmethod
    def approve(db: Session, approval_id: int, admin_id: int, notes: Optional[str] = None) -> Optional[ContentApprovalQueue]:
        """
        Phê duyệt nội dung.
        """
        try:
            db_approval = ContentApprovalRepository.get_by_id(db, approval_id)
            if not db_approval:
                logger.warning(f"Không tìm thấy đơn phê duyệt ID={approval_id} để phê duyệt")
                return None
            
            if db_approval.status != "pending":
                logger.warning(f"Đơn phê duyệt ID={approval_id} không ở trạng thái chờ duyệt")
                return db_approval
            
            db_approval.status = "approved"
            db_approval.reviewer_id = admin_id
            db_approval.review_notes = notes
            db_approval.reviewed_at = datetime.now(timezone.utc)
            db_approval.updated_at = datetime.now(timezone.utc)
            
            db.commit()
            db.refresh(db_approval)
            logger.info(f"Đã phê duyệt nội dung ID={approval_id} bởi admin ID={admin_id}")
            return db_approval
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi phê duyệt nội dung ID={approval_id}: {str(e)}")
            raise e
    
    @staticmethod
    def reject(db: Session, approval_id: int, admin_id: int, notes: Optional[str] = None) -> Optional[ContentApprovalQueue]:
        """
        Từ chối nội dung.
        """
        try:
            db_approval = ContentApprovalRepository.get_by_id(db, approval_id)
            if not db_approval:
                logger.warning(f"Không tìm thấy đơn phê duyệt ID={approval_id} để từ chối")
                return None
            
            if db_approval.status != "pending":
                logger.warning(f"Đơn phê duyệt ID={approval_id} không ở trạng thái chờ duyệt")
                return db_approval
            
            db_approval.status = "rejected"
            db_approval.reviewer_id = admin_id
            db_approval.review_notes = notes
            db_approval.reviewed_at = datetime.now(timezone.utc)
            db_approval.updated_at = datetime.now(timezone.utc)
            
            db.commit()
            db.refresh(db_approval)
            logger.info(f"Đã từ chối nội dung ID={approval_id} bởi admin ID={admin_id}")
            return db_approval
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi từ chối nội dung ID={approval_id}: {str(e)}")
            raise e
    
    @staticmethod
    def delete(db: Session, approval_id: int) -> bool:
        """
        Xóa đơn phê duyệt nội dung.
        """
        try:
            db_approval = ContentApprovalRepository.get_by_id(db, approval_id)
            if not db_approval:
                logger.warning(f"Không tìm thấy đơn phê duyệt ID={approval_id} để xóa")
                return False
            
            db.delete(db_approval)
            db.commit()
            logger.info(f"Đã xóa đơn phê duyệt ID={approval_id}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi xóa đơn phê duyệt ID={approval_id}: {str(e)}")
            raise e
