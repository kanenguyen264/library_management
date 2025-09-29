from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, desc
from typing import List, Optional, Dict, Any
from datetime import datetime

from app.admin_site.models import Permission, RolePermission
from app.logging.setup import get_logger

logger = get_logger(__name__)

class PermissionRepository:
    """
    Repository để thao tác với Permission trong cơ sở dữ liệu.
    """
    
    @staticmethod
    def get_by_id(db: Session, permission_id: int) -> Optional[Permission]:
        """
        Lấy quyền theo ID.
        
        Args:
            db: Database session
            permission_id: ID của quyền
            
        Returns:
            Permission object nếu tìm thấy, None nếu không
        """
        try:
            return db.query(Permission).filter(Permission.id == permission_id).first()
        except Exception as e:
            logger.error(f"Lỗi khi lấy quyền ID={permission_id}: {str(e)}")
            raise e
    
    @staticmethod
    def get_by_name(db: Session, name: str) -> Optional[Permission]:
        """
        Lấy quyền theo tên.
        
        Args:
            db: Database session
            name: Tên của quyền
            
        Returns:
            Permission object nếu tìm thấy, None nếu không
        """
        try:
            return db.query(Permission).filter(Permission.name == name).first()
        except Exception as e:
            logger.error(f"Lỗi khi lấy quyền theo tên '{name}': {str(e)}")
            raise e
    
    @staticmethod
    def count(
        db: Session,
        search: Optional[str] = None,
        resource: Optional[str] = None,
        action: Optional[str] = None
    ) -> int:
        """
        Đếm số lượng quyền với các điều kiện lọc.
        
        Args:
            db: Database session
            search: Tìm kiếm theo tên, mô tả
            resource: Lọc theo tài nguyên
            action: Lọc theo hành động
            
        Returns:
            Số lượng quyền thỏa mãn điều kiện
        """
        try:
            query = db.query(func.count(Permission.id))
            
            if search:
                query = query.filter(
                    or_(
                        Permission.name.ilike(f"%{search}%"),
                        Permission.description.ilike(f"%{search}%")
                    )
                )
            
            if resource:
                query = query.filter(Permission.resource == resource)
                
            if action:
                query = query.filter(Permission.action == action)
            
            return query.scalar()
        except Exception as e:
            logger.error(f"Lỗi khi đếm quyền: {str(e)}")
            raise e
    
    @staticmethod
    def get_all(
        db: Session, 
        skip: int = 0, 
        limit: int = 100,
        search: Optional[str] = None,
        resource: Optional[str] = None,
        action: Optional[str] = None,
        order_by: str = "name",
        order_desc: bool = False
    ) -> List[Permission]:
        """
        Lấy danh sách quyền với các tùy chọn lọc.
        
        Args:
            db: Database session
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa
            search: Tìm kiếm theo tên, mô tả
            resource: Lọc theo tài nguyên
            action: Lọc theo hành động
            order_by: Sắp xếp theo trường
            order_desc: Sắp xếp giảm dần nếu True
            
        Returns:
            Danh sách quyền
        """
        try:
            query = db.query(Permission)
            
            if search:
                query = query.filter(
                    or_(
                        Permission.name.ilike(f"%{search}%"),
                        Permission.description.ilike(f"%{search}%")
                    )
                )
            
            if resource:
                query = query.filter(Permission.resource == resource)
                
            if action:
                query = query.filter(Permission.action == action)
            
            # Xử lý sắp xếp
            if hasattr(Permission, order_by):
                if order_desc:
                    query = query.order_by(desc(getattr(Permission, order_by)))
                else:
                    query = query.order_by(getattr(Permission, order_by))
            
            return query.offset(skip).limit(limit).all()
        except Exception as e:
            logger.error(f"Lỗi khi lấy danh sách quyền: {str(e)}")
            raise e
    
    @staticmethod
    def get_by_conditions(
        db: Session,
        conditions: Dict[str, Any],
        skip: int = 0,
        limit: int = 100,
        order_by: Optional[str] = None,
        order_desc: bool = False
    ) -> List[Permission]:
        """
        Lấy danh sách quyền theo các điều kiện tùy chỉnh.
        
        Args:
            db: Database session
            conditions: Dictionary chứa các điều kiện lọc
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa
            order_by: Sắp xếp theo trường
            order_desc: Sắp xếp giảm dần nếu True
            
        Returns:
            Danh sách quyền thỏa mãn điều kiện
        """
        try:
            query = db.query(Permission)
            
            for field, value in conditions.items():
                if value is not None:
                    if field == 'search':
                        query = query.filter(
                            or_(
                                Permission.name.ilike(f"%{value}%"),
                                Permission.description.ilike(f"%{value}%")
                            )
                        )
                    elif hasattr(Permission, field):
                        query = query.filter(getattr(Permission, field) == value)
            
            if order_by and hasattr(Permission, order_by):
                if order_desc:
                    query = query.order_by(desc(getattr(Permission, order_by)))
                else:
                    query = query.order_by(getattr(Permission, order_by))
            
            return query.offset(skip).limit(limit).all()
        except Exception as e:
            logger.error(f"Lỗi khi lấy danh sách quyền theo điều kiện: {str(e)}")
            raise e
    
    @staticmethod
    def get_by_role_id(db: Session, role_id: int) -> List[Permission]:
        """
        Lấy danh sách quyền theo vai trò.
        
        Args:
            db: Database session
            role_id: ID của vai trò
            
        Returns:
            Danh sách quyền của vai trò
        """
        try:
            return (
                db.query(Permission)
                .join(RolePermission, Permission.id == RolePermission.permission_id)
                .filter(RolePermission.role_id == role_id)
                .all()
            )
        except Exception as e:
            logger.error(f"Lỗi khi lấy danh sách quyền của vai trò ID={role_id}: {str(e)}")
            raise e
    
    @staticmethod
    def create(db: Session, permission_data: Dict[str, Any]) -> Permission:
        """
        Tạo quyền mới.
        
        Args:
            db: Database session
            permission_data: Dữ liệu quyền cần tạo
            
        Returns:
            Permission object đã tạo
        """
        try:
            # Thêm ngày tạo và cập nhật nếu không có
            if 'created_at' not in permission_data:
                permission_data['created_at'] = datetime.now(timezone.utc)
            if 'updated_at' not in permission_data:
                permission_data['updated_at'] = datetime.now(timezone.utc)
                
            db_permission = Permission(**permission_data)
            db.add(db_permission)
            db.commit()
            db.refresh(db_permission)
            logger.info(f"Đã tạo quyền mới: {db_permission.name}")
            return db_permission
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi tạo quyền: {str(e)}")
            raise e
    
    @staticmethod
    def update(db: Session, permission_id: int, permission_data: Dict[str, Any]) -> Optional[Permission]:
        """
        Cập nhật thông tin quyền.
        
        Args:
            db: Database session
            permission_id: ID của quyền
            permission_data: Dữ liệu cập nhật
            
        Returns:
            Permission object đã cập nhật hoặc None nếu không tìm thấy
        """
        try:
            db_permission = PermissionRepository.get_by_id(db, permission_id)
            if not db_permission:
                logger.warning(f"Không tìm thấy quyền ID={permission_id} để cập nhật")
                return None
            
            for key, value in permission_data.items():
                setattr(db_permission, key, value)
            
            db_permission.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(db_permission)
            logger.info(f"Đã cập nhật quyền ID={permission_id}")
            return db_permission
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi cập nhật quyền ID={permission_id}: {str(e)}")
            raise e
    
    @staticmethod
    def delete(db: Session, permission_id: int) -> bool:
        """
        Xóa quyền.
        
        Args:
            db: Database session
            permission_id: ID của quyền
            
        Returns:
            True nếu xóa thành công, False nếu không
        """
        try:
            db_permission = PermissionRepository.get_by_id(db, permission_id)
            if not db_permission:
                logger.warning(f"Không tìm thấy quyền ID={permission_id} để xóa")
                return False
            
            # Xóa tất cả liên kết với vai trò
            db.query(RolePermission).filter(RolePermission.permission_id == permission_id).delete()
            
            # Xóa quyền
            db.delete(db_permission)
            db.commit()
            logger.info(f"Đã xóa quyền ID={permission_id}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi xóa quyền ID={permission_id}: {str(e)}")
            raise e
    
    @staticmethod
    def add_permission_to_role(db: Session, role_id: int, permission_id: int) -> bool:
        """
        Thêm quyền vào vai trò.
        
        Args:
            db: Database session
            role_id: ID của vai trò
            permission_id: ID của quyền
            
        Returns:
            True nếu thêm thành công, False nếu không
        """
        try:
            # Kiểm tra xem đã có quyền này trong vai trò chưa
            existing = (
                db.query(RolePermission)
                .filter(
                    RolePermission.role_id == role_id,
                    RolePermission.permission_id == permission_id
                )
                .first()
            )
            
            if existing:
                logger.info(f"Quyền ID={permission_id} đã tồn tại trong vai trò ID={role_id}")
                return False
            
            role_permission = RolePermission(
                role_id=role_id,
                permission_id=permission_id,
                created_at=datetime.now(timezone.utc)
            )
            db.add(role_permission)
            db.commit()
            logger.info(f"Đã thêm quyền ID={permission_id} vào vai trò ID={role_id}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi thêm quyền ID={permission_id} vào vai trò ID={role_id}: {str(e)}")
            raise e
    
    @staticmethod
    def remove_permission_from_role(db: Session, role_id: int, permission_id: int) -> bool:
        """
        Xóa quyền khỏi vai trò.
        
        Args:
            db: Database session
            role_id: ID của vai trò
            permission_id: ID của quyền
            
        Returns:
            True nếu xóa thành công, False nếu không
        """
        try:
            deleted = (
                db.query(RolePermission)
                .filter(
                    RolePermission.role_id == role_id,
                    RolePermission.permission_id == permission_id
                )
                .delete()
            )
            db.commit()
            if deleted > 0:
                logger.info(f"Đã xóa quyền ID={permission_id} khỏi vai trò ID={role_id}")
            else:
                logger.info(f"Không tìm thấy quyền ID={permission_id} trong vai trò ID={role_id} để xóa")
            return deleted > 0
        except Exception as e:
            db.rollback()
            logger.error(f"Lỗi khi xóa quyền ID={permission_id} khỏi vai trò ID={role_id}: {str(e)}")
            raise e
    
    @staticmethod
    def get_resources(db: Session) -> List[str]:
        """
        Lấy danh sách các tài nguyên.
        
        Args:
            db: Database session
            
        Returns:
            Danh sách tên tài nguyên
        """
        try:
            results = db.query(Permission.resource).distinct().order_by(Permission.resource).all()
            return [result[0] for result in results if result[0] is not None]
        except Exception as e:
            logger.error(f"Lỗi khi lấy danh sách tài nguyên: {str(e)}")
            raise e
    
    @staticmethod
    def get_actions(db: Session, resource: Optional[str] = None) -> List[str]:
        """
        Lấy danh sách các hành động.
        
        Args:
            db: Database session
            resource: Tài nguyên để lọc hành động (tùy chọn)
            
        Returns:
            Danh sách tên hành động
        """
        try:
            query = db.query(Permission.action).distinct()
            
            if resource:
                query = query.filter(Permission.resource == resource)
                
            results = query.order_by(Permission.action).all()
            return [result[0] for result in results if result[0] is not None]
        except Exception as e:
            logger.error(f"Lỗi khi lấy danh sách hành động: {str(e)}")
            raise e
