from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, desc
from typing import List, Optional, Dict, Any
from datetime import datetime

from app.admin_site.models import AdminSession
from app.logging.setup import get_logger

logger = get_logger(__name__)

class AdminSessionRepository:
    """
    Repository để thao tác với AdminSession trong cơ sở dữ liệu.
    """
    
    @staticmethod
    def get_by_id(db: Session, session_id: int) -> Optional[AdminSession]:
        """
        Lấy phiên đăng nhập theo ID.
        
        Args:
            db: Database session
            session_id: ID của phiên đăng nhập
            
        Returns:
            AdminSession object nếu tìm thấy, None nếu không
        """
        return db.query(AdminSession).filter(AdminSession.id == session_id).first()
    
    @staticmethod
    def get_by_token(db: Session, token: str, active_only: bool = True) -> Optional[AdminSession]:
        """
        Lấy phiên đăng nhập theo token.
        
        Args:
            db: Database session
            token: Token của phiên đăng nhập
            active_only: Chỉ lấy phiên đang hoạt động
            
        Returns:
            AdminSession object nếu tìm thấy, None nếu không
        """
        query = db.query(AdminSession).filter(AdminSession.token == token)
        
        if active_only:
            query = query.filter(AdminSession.status == "active")
        
        return query.first()
    
    @staticmethod
    def count(
        db: Session, 
        admin_id: Optional[int] = None,
        status: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> int:
        """
        Đếm số lượng phiên đăng nhập admin.
        """
        query = db.query(func.count(AdminSession.id))
        
        if admin_id:
            query = query.filter(AdminSession.admin_id == admin_id)
        
        if status:
            query = query.filter(AdminSession.status == status)
        
        if ip_address:
            query = query.filter(AdminSession.ip_address == ip_address)
        
        return query.scalar()
    
    @staticmethod
    def get_all(
        db: Session, 
        skip: int = 0, 
        limit: int = 100,
        admin_id: Optional[int] = None,
        status: Optional[str] = None,
        ip_address: Optional[str] = None,
        order_by: str = "login_time",
        order_desc: bool = True
    ) -> List[AdminSession]:
        """
        Lấy danh sách phiên đăng nhập admin.
        """
        query = db.query(AdminSession)
        
        if admin_id:
            query = query.filter(AdminSession.admin_id == admin_id)
        
        if status:
            query = query.filter(AdminSession.status == status)
        
        if ip_address:
            query = query.filter(AdminSession.ip_address == ip_address)
        
        # Xử lý sắp xếp
        if hasattr(AdminSession, order_by):
            if order_desc:
                query = query.order_by(desc(getattr(AdminSession, order_by)))
            else:
                query = query.order_by(getattr(AdminSession, order_by))
        
        return query.offset(skip).limit(limit).all()
    
    @staticmethod
    def get_by_conditions(
        db: Session,
        conditions: Dict[str, Any],
        skip: int = 0,
        limit: int = 100,
        order_by: Optional[str] = None,
        order_desc: bool = False
    ) -> List[AdminSession]:
        """
        Lấy danh sách phiên đăng nhập admin theo các điều kiện tùy chỉnh.
        """
        query = db.query(AdminSession)
        
        for field, value in conditions.items():
            if value is not None and hasattr(AdminSession, field):
                query = query.filter(getattr(AdminSession, field) == value)
        
        if order_by and hasattr(AdminSession, order_by):
            if order_desc:
                query = query.order_by(desc(getattr(AdminSession, order_by)))
            else:
                query = query.order_by(getattr(AdminSession, order_by))
        
        return query.offset(skip).limit(limit).all()
    
    @staticmethod
    def create(db: Session, session_data: Dict[str, Any]) -> AdminSession:
        """
        Tạo phiên đăng nhập mới.
        
        Args:
            db: Database session
            session_data: Dữ liệu phiên đăng nhập
            
        Returns:
            AdminSession object đã tạo
        """
        try:
            db_session = AdminSession(**session_data)
            db.add(db_session)
            db.commit()
            db.refresh(db_session)
            logger.info(f"Đã tạo phiên đăng nhập mới cho admin ID={db_session.admin_id}")
            return db_session
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi tạo phiên đăng nhập: {str(e)}")
            raise e
    
    @staticmethod
    def update(db: Session, session_id: int, session_data: Dict[str, Any]) -> Optional[AdminSession]:
        """
        Cập nhật thông tin phiên đăng nhập.
        
        Args:
            db: Database session
            session_id: ID của phiên đăng nhập
            session_data: Dữ liệu cập nhật
            
        Returns:
            AdminSession object đã cập nhật hoặc None nếu không tìm thấy
        """
        try:
            db_session = AdminSessionRepository.get_by_id(db, session_id)
            if not db_session:
                logger.warning(f"Không tìm thấy phiên đăng nhập ID={session_id} để cập nhật")
                return None
            
            for key, value in session_data.items():
                setattr(db_session, key, value)
            
            db_session.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(db_session)
            logger.info(f"Đã cập nhật phiên đăng nhập ID={session_id}")
            return db_session
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi cập nhật phiên đăng nhập ID={session_id}: {str(e)}")
            raise e
    
    @staticmethod
    def update_status(db: Session, session_id: int, status: str) -> Optional[AdminSession]:
        """
        Cập nhật trạng thái phiên đăng nhập.
        """
        try:
            db_session = AdminSessionRepository.get_by_id(db, session_id)
            if not db_session:
                logger.warning(f"Không tìm thấy phiên đăng nhập ID={session_id} để cập nhật trạng thái")
                return None
            
            db_session.status = status
            if status == "inactive":
                db_session.logout_time = datetime.now(timezone.utc)
                
            db.commit()
            db.refresh(db_session)
            logger.info(f"Đã cập nhật trạng thái phiên đăng nhập ID={session_id} thành {status}")
            return db_session
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi cập nhật trạng thái phiên đăng nhập ID={session_id}: {str(e)}")
            raise e
    
    @staticmethod
    def invalidate(db: Session, token: str) -> bool:
        """
        Vô hiệu hóa phiên đăng nhập.
        
        Args:
            db: Database session
            token: Token của phiên đăng nhập
            
        Returns:
            True nếu thành công, False nếu không
        """
        try:
            db_session = AdminSessionRepository.get_by_token(db, token, active_only=True)
            if not db_session:
                logger.warning(f"Không tìm thấy phiên đăng nhập active với token để vô hiệu hóa")
                return False
            
            db_session.status = "inactive"
            db_session.logout_time = datetime.now(timezone.utc)
            db.commit()
            logger.info(f"Đã vô hiệu hóa phiên đăng nhập cho admin ID={db_session.admin_id}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi vô hiệu hóa phiên đăng nhập: {str(e)}")
            raise e
    
    @staticmethod
    def invalidate_all_by_admin(db: Session, admin_id: int) -> int:
        """
        Vô hiệu hóa tất cả phiên đăng nhập của admin.
        
        Args:
            db: Database session
            admin_id: ID của admin
            
        Returns:
            Số lượng phiên đã vô hiệu hóa
        """
        try:
            active_sessions = db.query(AdminSession).filter(
                AdminSession.admin_id == admin_id,
                AdminSession.status == "active"
            ).all()
            
            count = 0
            for session in active_sessions:
                session.status = "inactive"
            
            db.commit()
            logger.info(f"Đã vô hiệu hóa {count} phiên đăng nhập của admin ID={admin_id}")
            return count
        except Exception as e:
            logger.error(f"Lỗi khi vô hiệu hóa tất cả phiên đăng nhập của admin ID={admin_id}: {str(e)}")
            raise e
    
    @staticmethod
    def clean_expired(db: Session) -> int:
        """
        Xóa các phiên đăng nhập đã hết hạn.
        
        Args:
            db: Database session
            
        Returns:
            Số lượng phiên đã xóa
        """
        now = datetime.now(timezone.utc)
        deleted = db.query(AdminSession).filter(AdminSession.expires_at < now).delete()
        db.commit()
        logger.info(f"Đã xóa {deleted} phiên đăng nhập hết hạn")
        return deleted