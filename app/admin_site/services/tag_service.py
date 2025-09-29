from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
import logging

from app.user_site.models.tag import Tag, BookTag
from app.user_site.repositories.tag_repo import TagRepository
from app.common.utils.cache import cached
from app.common.utils.slugify import slugify
from app.logs_manager.services import create_admin_activity_log
from app.logs_manager.schemas.admin_activity_log import AdminActivityLogCreate

logger = logging.getLogger(__name__)


async def get_all_tags(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    sort_by: str = "name",
    sort_desc: bool = False,
    admin_id: Optional[int] = None,
) -> List[Tag]:
    """
    Lấy danh sách tags với bộ lọc và phân trang.

    Args:
        db: Database session
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về
        search: Tìm kiếm theo tên
        sort_by: Sắp xếp theo trường
        sort_desc: Sắp xếp giảm dần
        admin_id: ID của admin thực hiện hành động

    Returns:
        Danh sách Tag
    """
    try:
        repo = TagRepository(db)
        tags = await repo.list_tags(
            skip=skip,
            limit=limit,
            search_query=search,
            sort_by=sort_by,
            sort_desc=sort_desc,
        )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="TAGS",
                        entity_id=0,
                        description="Viewed tag list",
                        metadata={
                            "skip": skip,
                            "limit": limit,
                            "search": search,
                            "sort_by": sort_by,
                            "sort_desc": sort_desc,
                            "results_count": len(tags),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return tags
    except Exception as e:
        logger.error(f"Error retrieving tags: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi lấy danh sách thẻ",
        )


async def count_tags(db: Session, search: Optional[str] = None) -> int:
    """
    Đếm số lượng tags với bộ lọc.

    Args:
        db: Database session
        search: Tìm kiếm theo tên

    Returns:
        Số lượng tag
    """
    try:
        repo = TagRepository(db)
        return await repo.count_tags(search_query=search)
    except Exception as e:
        logger.error(f"Error counting tags: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi đếm số lượng thẻ",
        )


@cached(key_prefix="tag", ttl=3600)
async def get_tag_by_id(
    db: Session, tag_id: int, admin_id: Optional[int] = None
) -> Tag:
    """
    Lấy thông tin tag theo ID.

    Args:
        db: Database session
        tag_id: ID của tag
        admin_id: ID của admin thực hiện hành động

    Returns:
        Tag object

    Raises:
        HTTPException: Nếu không tìm thấy tag
    """
    try:
        repo = TagRepository(db)
        tag = await repo.get_by_id(tag_id, include_books=True)

        if not tag:
            logger.warning(f"Tag with ID {tag_id} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Không tìm thấy thẻ với ID {tag_id}",
            )

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="VIEW",
                        entity_type="TAG",
                        entity_id=tag_id,
                        description=f"Viewed tag details: {tag.name}",
                        metadata={
                            "name": tag.name,
                            "slug": tag.slug,
                            "books_count": len(tag.books) if tag.books else 0,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return tag
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving tag: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi lấy thông tin thẻ",
        )


async def get_tag_by_slug(db: Session, slug: str) -> Tag:
    """
    Lấy thông tin tag theo slug.

    Args:
        db: Database session
        slug: Slug của tag

    Returns:
        Tag object

    Raises:
        HTTPException: Nếu không tìm thấy tag
    """
    try:
        repo = TagRepository(db)
        tag = await repo.get_by_slug(slug)
        if not tag:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Không tìm thấy thẻ với slug {slug}",
            )
        return tag
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving tag by slug: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi lấy thông tin thẻ theo slug",
        )


async def create_tag(
    db: Session, tag_data: Dict[str, Any], admin_id: Optional[int] = None
) -> Tag:
    """
    Tạo tag mới.

    Args:
        db: Database session
        tag_data: Dữ liệu của tag
        admin_id: ID của admin thực hiện hành động

    Returns:
        Tag đã tạo

    Raises:
        HTTPException: Nếu tên tag đã tồn tại
    """
    try:
        repo = TagRepository(db)

        # Kiểm tra tên tag đã tồn tại chưa
        existing_tag = await repo.get_by_name(tag_data["name"])
        if existing_tag:
            logger.warning(f"Tag with name '{tag_data['name']}' already exists")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Thẻ với tên '{tag_data['name']}' đã tồn tại",
            )

        # Tạo slug nếu không được cung cấp
        if "slug" not in tag_data or not tag_data["slug"]:
            tag_data["slug"] = slugify(tag_data["name"])

        # Kiểm tra slug đã tồn tại chưa
        existing_slug = await repo.get_by_slug(tag_data["slug"])
        if existing_slug:
            logger.warning(f"Tag with slug '{tag_data['slug']}' already exists")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Thẻ với slug '{tag_data['slug']}' đã tồn tại",
            )

        # Tạo tag mới
        tag = await repo.create(tag_data)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="CREATE",
                        entity_type="TAG",
                        entity_id=tag.id,
                        description=f"Created new tag: {tag.name}",
                        metadata={
                            "name": tag.name,
                            "slug": tag.slug,
                            "description": (
                                tag.description if hasattr(tag, "description") else None
                            ),
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Created new tag: {tag.name}")
        return tag
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating tag: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi tạo thẻ mới",
        )


async def update_tag(
    db: Session, tag_id: int, tag_data: Dict[str, Any], admin_id: Optional[int] = None
) -> Tag:
    """
    Cập nhật thông tin tag.

    Args:
        db: Database session
        tag_id: ID của tag
        tag_data: Dữ liệu cập nhật
        admin_id: ID của admin thực hiện hành động

    Returns:
        Tag đã cập nhật

    Raises:
        HTTPException: Nếu không tìm thấy tag hoặc tên/slug đã tồn tại
    """
    try:
        repo = TagRepository(db)

        # Get old tag data for logging
        old_tag = await repo.get_by_id(tag_id)
        if not old_tag:
            logger.warning(f"Tag with ID {tag_id} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Không tìm thấy thẻ với ID {tag_id}",
            )

        # Kiểm tra tên tag nếu được cập nhật
        if "name" in tag_data and tag_data["name"] != old_tag.name:
            existing_tag = await repo.get_by_name(tag_data["name"])
            if existing_tag and existing_tag.id != tag_id:
                logger.warning(f"Tag with name '{tag_data['name']}' already exists")
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Thẻ với tên '{tag_data['name']}' đã tồn tại",
                )

        # Tạo slug mới nếu cập nhật tên nhưng không cung cấp slug
        if "name" in tag_data and ("slug" not in tag_data or not tag_data["slug"]):
            tag_data["slug"] = slugify(tag_data["name"])

        # Kiểm tra slug nếu được cập nhật
        if "slug" in tag_data and tag_data["slug"] != old_tag.slug:
            existing_slug = await repo.get_by_slug(tag_data["slug"])
            if existing_slug and existing_slug.id != tag_id:
                logger.warning(f"Tag with slug '{tag_data['slug']}' already exists")
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Thẻ với slug '{tag_data['slug']}' đã tồn tại",
                )

        # Cập nhật tag
        updated_tag = await repo.update(tag_id, tag_data)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="UPDATE",
                        entity_type="TAG",
                        entity_id=tag_id,
                        description=f"Updated tag: {updated_tag.name}",
                        metadata={
                            "updated_fields": list(tag_data.keys()),
                            "old_values": {
                                k: getattr(old_tag, k) for k in tag_data.keys()
                            },
                            "new_values": {
                                k: getattr(updated_tag, k) for k in tag_data.keys()
                            },
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Updated tag: {updated_tag.name}")
        return updated_tag
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating tag: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi cập nhật thẻ",
        )


async def delete_tag(db: Session, tag_id: int, admin_id: Optional[int] = None) -> None:
    """
    Xóa tag.

    Args:
        db: Database session
        tag_id: ID của tag
        admin_id: ID của admin thực hiện hành động

    Raises:
        HTTPException: Nếu không tìm thấy tag
    """
    try:
        repo = TagRepository(db)

        # Get tag details before deletion for logging
        tag = await repo.get_by_id(tag_id)
        if not tag:
            logger.warning(f"Tag with ID {tag_id} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Không tìm thấy thẻ với ID {tag_id}",
            )

        # Xóa tag
        await repo.delete(tag_id)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="DELETE",
                        entity_type="TAG",
                        entity_id=tag_id,
                        description=f"Deleted tag: {tag.name}",
                        metadata={
                            "name": tag.name,
                            "slug": tag.slug,
                            "books_count": len(tag.books) if tag.books else 0,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        logger.info(f"Deleted tag: {tag.name}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting tag: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Lỗi khi xóa thẻ"
        )


async def get_books_by_tag(
    db: Session,
    tag_id: int,
    skip: int = 0,
    limit: int = 20,
    only_published: bool = True,
) -> List[Any]:
    """
    Lấy danh sách sách theo tag.

    Args:
        db: Database session
        tag_id: ID của tag
        skip: Số bản ghi bỏ qua
        limit: Số bản ghi tối đa trả về
        only_published: Chỉ lấy sách đã xuất bản

    Returns:
        Danh sách sách

    Raises:
        HTTPException: Nếu không tìm thấy tag
    """
    try:
        repo = TagRepository(db)

        # Kiểm tra tag tồn tại
        tag = await repo.get_by_id(tag_id)
        if not tag:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Không tìm thấy thẻ với ID {tag_id}",
            )

        # Lấy danh sách sách
        return await repo.get_books_by_tag(
            tag_id=tag_id, skip=skip, limit=limit, only_published=only_published
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving books by tag: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi lấy danh sách sách theo thẻ",
        )


async def count_books_by_tag(
    db: Session, tag_id: int, only_published: bool = True
) -> int:
    """
    Đếm số lượng sách theo tag.

    Args:
        db: Database session
        tag_id: ID của tag
        only_published: Chỉ đếm sách đã xuất bản

    Returns:
        Số lượng sách

    Raises:
        HTTPException: Nếu không tìm thấy tag
    """
    try:
        repo = TagRepository(db)

        # Kiểm tra tag tồn tại
        tag = await repo.get_by_id(tag_id)
        if not tag:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Không tìm thấy thẻ với ID {tag_id}",
            )

        # Đếm số lượng sách
        return await repo.count_books_by_tag(
            tag_id=tag_id, only_published=only_published
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error counting books by tag: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi đếm số lượng sách theo thẻ",
        )


@cached(key_prefix="popular_tags", ttl=3600)
async def get_popular_tags(db: Session, limit: int = 10) -> List[Tag]:
    """
    Lấy danh sách tag phổ biến.

    Args:
        db: Database session
        limit: Số lượng tối đa trả về

    Returns:
        Danh sách tag phổ biến
    """
    try:
        repo = TagRepository(db)
        return await repo.get_popular_tags(limit=limit)
    except Exception as e:
        logger.error(f"Error retrieving popular tags: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi lấy danh sách thẻ phổ biến",
        )


async def add_book_tag(
    db: Session, book_id: int, tag_id: int, admin_id: Optional[int] = None
) -> BookTag:
    """
    Thêm tag cho sách.

    Args:
        db: Database session
        book_id: ID của sách
        tag_id: ID của tag
        admin_id: ID của admin thực hiện hành động

    Returns:
        BookTag object

    Raises:
        HTTPException: Nếu không thành công
    """
    try:
        repo = TagRepository(db)
        book_tag = await repo.add_book_tag(book_id=book_id, tag_id=tag_id)

        # Log admin activity
        if admin_id:
            try:
                # Get tag and book details for logging
                tag = await repo.get_by_id(tag_id)
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="ADD",
                        entity_type="BOOK_TAG",
                        entity_id=book_id,
                        description=f"Added tag '{tag.name}' to book ID {book_id}",
                        metadata={
                            "book_id": book_id,
                            "tag_id": tag_id,
                            "tag_name": tag.name,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

        return book_tag
    except Exception as e:
        logger.error(f"Error adding tag to book: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi thêm thẻ cho sách",
        )


async def remove_book_tag(
    db: Session, book_id: int, tag_id: int, admin_id: Optional[int] = None
) -> None:
    """
    Xóa tag khỏi sách.

    Args:
        db: Database session
        book_id: ID của sách
        tag_id: ID của tag
        admin_id: ID của admin thực hiện hành động

    Raises:
        HTTPException: Nếu không thành công
    """
    try:
        repo = TagRepository(db)

        # Get tag details before removal for logging
        tag = await repo.get_by_id(tag_id)

        await repo.remove_book_tag(book_id=book_id, tag_id=tag_id)

        # Log admin activity
        if admin_id:
            try:
                await create_admin_activity_log(
                    db,
                    AdminActivityLogCreate(
                        admin_id=admin_id,
                        activity_type="REMOVE",
                        entity_type="BOOK_TAG",
                        entity_id=book_id,
                        description=f"Removed tag '{tag.name}' from book ID {book_id}",
                        metadata={
                            "book_id": book_id,
                            "tag_id": tag_id,
                            "tag_name": tag.name,
                        },
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to log admin activity: {str(e)}")

    except Exception as e:
        logger.error(f"Error removing tag from book: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi xóa thẻ khỏi sách",
        )


async def get_tags_by_book(db: Session, book_id: int) -> List[Tag]:
    """
    Lấy danh sách tag của sách.

    Args:
        db: Database session
        book_id: ID của sách

    Returns:
        Danh sách tag
    """
    try:
        repo = TagRepository(db)
        return await repo.get_tags_by_book(book_id=book_id)
    except Exception as e:
        logger.error(f"Error retrieving tags by book: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi lấy danh sách thẻ của sách",
        )


async def search_tags(db: Session, query: str, limit: int = 10) -> List[Tag]:
    """
    Tìm kiếm tag.

    Args:
        db: Database session
        query: Từ khóa tìm kiếm
        limit: Số lượng tối đa trả về

    Returns:
        Danh sách tag
    """
    try:
        repo = TagRepository(db)
        return await repo.search_tags(query=query, limit=limit)
    except Exception as e:
        logger.error(f"Error searching tags: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi khi tìm kiếm thẻ",
        )
