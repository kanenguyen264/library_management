from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.user_site.repositories.annotation_repo import AnnotationRepository
from app.core.exceptions import (
    NotFoundException,
    BadRequestException,
    ForbiddenException,
)
from app.logs_manager.services import create_user_activity_log
from app.logs_manager.schemas.user_activity_log import UserActivityLogCreate
from app.cache.decorators import cached, invalidate_cache
from app.cache import get_cache
from app.cache.keys import create_api_response_key, generate_cache_key
from app.monitoring.metrics import Metrics
from app.performance.profiling.code_profiler import CodeProfiler
from app.security.input_validation.sanitizers import sanitize_html, sanitize_dict


class AnnotationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.annotation_repo = AnnotationRepository(db)
        self.cache = get_cache()
        self.metrics = Metrics()
        self.profiler = CodeProfiler(enabled=True)

    @invalidate_cache(
        namespace="annotations", tags=["user_annotations", "book_annotations"]
    )
    async def create_annotation(
        self, user_id: int, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Tạo ghi chú mới.

        Args:
            user_id: ID của người dùng
            data: Dữ liệu ghi chú

        Returns:
            Thông tin ghi chú đã tạo
        """
        with self.metrics.time_request("POST", "/annotations"):
            # Đảm bảo user_id được thiết lập
            data["user_id"] = user_id

            # Đảm bảo có các trường bắt buộc
            required_fields = ["book_id", "content", "text_position"]
            for field in required_fields:
                if field not in data:
                    raise BadRequestException(detail=f"Thiếu trường {field}")

            # Sanitize content để tránh XSS
            if "content" in data and data["content"]:
                data["content"] = sanitize_html(data["content"])

            # Tạo annotation
            annotation = await self.annotation_repo.create(data)

            # Log the creation activity
            try:
                await create_user_activity_log(
                    self.db,
                    UserActivityLogCreate(
                        user_id=user_id,
                        activity_type="CREATE",
                        entity_type="ANNOTATION",
                        entity_id=annotation.id,
                        description=f"Created annotation in book ID: {annotation.book_id}",
                        metadata={
                            "book_id": annotation.book_id,
                            "chapter_id": annotation.chapter_id,
                            "is_public": annotation.is_public,
                            "text_position": annotation.text_position,
                        },
                    ),
                )

                # Track metrics
                self.metrics.track_book_activity(
                    action="annotate",
                    book_id=str(annotation.book_id),
                    user_type="registered",
                )

            except Exception:
                # Log but don't fail if logging fails
                pass

            # Invalidate related caches
            book_id = data.get("book_id")
            chapter_id = data.get("chapter_id")
            if book_id:
                # Invalidate book annotations cache
                cache_key = f"book_annotations:{book_id}"
                await self.cache.delete(cache_key)

                if chapter_id:
                    # Invalidate chapter annotations cache
                    cache_key = f"chapter_annotations:{chapter_id}"
                    await self.cache.delete(cache_key)

            return {
                "id": annotation.id,
                "user_id": annotation.user_id,
                "book_id": annotation.book_id,
                "chapter_id": annotation.chapter_id,
                "content": annotation.content,
                "text_position": annotation.text_position,
                "text_context": annotation.text_context,
                "color": annotation.color,
                "is_public": annotation.is_public,
                "created_at": annotation.created_at,
                "updated_at": annotation.updated_at,
            }

    @cached(ttl=3600, namespace="annotations", tags=["annotation_details"])
    async def get_annotation(
        self, annotation_id: int, user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Lấy thông tin ghi chú theo ID.

        Args:
            annotation_id: ID của ghi chú
            user_id: ID của người dùng (nếu cần kiểm tra quyền)

        Returns:
            Thông tin ghi chú

        Raises:
            NotFoundException: Nếu không tìm thấy ghi chú
            ForbiddenException: Nếu ghi chú không công khai và user_id không phải chủ sở hữu
        """
        with self.profiler.profile_time(name="get_annotation", threshold=0.5):
            # Kiểm tra cache trước
            cache_key = f"annotation:{annotation_id}"
            cached_data = await self.cache.get(cache_key)
            if cached_data:
                # Khi dùng cache, vẫn cần kiểm tra quyền truy cập
                if (
                    user_id is not None
                    and cached_data.get("user_id") != user_id
                    and not cached_data.get("is_public")
                ):
                    raise ForbiddenException(
                        detail="Bạn không có quyền xem ghi chú này"
                    )
                return cached_data

            annotation = await self.annotation_repo.get_by_id(
                annotation_id, with_relations=True
            )
            if not annotation:
                raise NotFoundException(
                    detail=f"Không tìm thấy ghi chú với ID {annotation_id}"
                )

            # Kiểm tra quyền truy cập
            if (
                user_id is not None
                and annotation.user_id != user_id
                and not annotation.is_public
            ):
                raise ForbiddenException(detail="Bạn không có quyền xem ghi chú này")

            result = {
                "id": annotation.id,
                "user_id": annotation.user_id,
                "book_id": annotation.book_id,
                "chapter_id": annotation.chapter_id,
                "content": annotation.content,
                "text_position": annotation.text_position,
                "text_context": annotation.text_context,
                "color": annotation.color,
                "is_public": annotation.is_public,
                "created_at": annotation.created_at,
                "updated_at": annotation.updated_at,
            }

            # Thêm thông tin quan hệ nếu có
            if hasattr(annotation, "user") and annotation.user:
                result["user"] = {
                    "id": annotation.user.id,
                    "username": annotation.user.username,
                    "display_name": annotation.user.display_name,
                }

            if hasattr(annotation, "book") and annotation.book:
                result["book"] = {
                    "id": annotation.book.id,
                    "title": annotation.book.title,
                    "cover_image": annotation.book.cover_image,
                }

            if hasattr(annotation, "chapter") and annotation.chapter:
                result["chapter"] = {
                    "id": annotation.chapter.id,
                    "title": annotation.chapter.title,
                    "number": annotation.chapter.number,
                }

            # Cache kết quả
            await self.cache.set(cache_key, result, ttl=3600)

            return result

    @cached(
        ttl=1800,
        namespace="annotations",
        key_builder=lambda *args, **kwargs: f"user_annotations:{kwargs.get('user_id')}:{kwargs.get('book_id')}:{kwargs.get('chapter_id')}:{kwargs.get('only_public')}:{kwargs.get('skip')}:{kwargs.get('limit')}",
    )
    async def list_user_annotations(
        self,
        user_id: int,
        book_id: Optional[int] = None,
        chapter_id: Optional[int] = None,
        only_public: bool = False,
        skip: int = 0,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        Lấy danh sách ghi chú của người dùng.

        Args:
            user_id: ID của người dùng
            book_id: Lọc theo ID sách (tùy chọn)
            chapter_id: Lọc theo ID chương (tùy chọn)
            only_public: Chỉ lấy ghi chú công khai
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa trả về

        Returns:
            Danh sách ghi chú và thông tin phân trang
        """
        with self.metrics.time_request("GET", f"/users/{user_id}/annotations"):
            annotations = await self.annotation_repo.list_by_user(
                user_id, book_id, chapter_id, only_public, skip, limit
            )
            total = await self.annotation_repo.count_by_user(
                user_id, book_id, chapter_id
            )

            return {
                "items": [
                    {
                        "id": annotation.id,
                        "user_id": annotation.user_id,
                        "book_id": annotation.book_id,
                        "chapter_id": annotation.chapter_id,
                        "content": annotation.content,
                        "text_position": annotation.text_position,
                        "text_context": annotation.text_context,
                        "color": annotation.color,
                        "is_public": annotation.is_public,
                        "created_at": annotation.created_at,
                        "updated_at": annotation.updated_at,
                        "book": (
                            {
                                "id": annotation.book.id,
                                "title": annotation.book.title,
                                "cover_image": annotation.book.cover_image,
                            }
                            if hasattr(annotation, "book") and annotation.book
                            else None
                        ),
                        "chapter": (
                            {
                                "id": annotation.chapter.id,
                                "title": annotation.chapter.title,
                                "number": annotation.chapter.number,
                            }
                            if hasattr(annotation, "chapter") and annotation.chapter
                            else None
                        ),
                    }
                    for annotation in annotations
                ],
                "total": total,
                "skip": skip,
                "limit": limit,
            }

    @cached(
        ttl=1800,
        namespace="annotations",
        key_builder=lambda *args, **kwargs: f"public_book_annotations:{kwargs.get('book_id')}:{kwargs.get('chapter_id')}:{kwargs.get('skip')}:{kwargs.get('limit')}",
    )
    async def list_public_book_annotations(
        self,
        book_id: int,
        chapter_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        Lấy danh sách ghi chú công khai của một sách.

        Args:
            book_id: ID của sách
            chapter_id: Lọc theo ID chương (tùy chọn)
            skip: Số lượng bản ghi bỏ qua
            limit: Số lượng bản ghi tối đa trả về

        Returns:
            Danh sách ghi chú và thông tin phân trang
        """
        with self.metrics.time_request("GET", f"/books/{book_id}/annotations"):
            annotations = await self.annotation_repo.list_public_by_book(
                book_id, chapter_id, skip, limit
            )
            total = await self.annotation_repo.count_by_book(
                book_id, chapter_id, only_public=True
            )

            return {
                "items": [
                    {
                        "id": annotation.id,
                        "user_id": annotation.user_id,
                        "book_id": annotation.book_id,
                        "chapter_id": annotation.chapter_id,
                        "content": annotation.content,
                        "text_position": annotation.text_position,
                        "text_context": annotation.text_context,
                        "color": annotation.color,
                        "is_public": annotation.is_public,
                        "created_at": annotation.created_at,
                        "updated_at": annotation.updated_at,
                        "user": (
                            {
                                "id": annotation.user.id,
                                "username": annotation.user.username,
                                "display_name": annotation.user.display_name,
                            }
                            if hasattr(annotation, "user") and annotation.user
                            else None
                        ),
                        "chapter": (
                            {
                                "id": annotation.chapter.id,
                                "title": annotation.chapter.title,
                                "number": annotation.chapter.number,
                            }
                            if hasattr(annotation, "chapter") and annotation.chapter
                            else None
                        ),
                    }
                    for annotation in annotations
                ],
                "total": total,
                "skip": skip,
                "limit": limit,
            }

    @invalidate_cache(
        namespace="annotations",
        tags=["annotation_details", "user_annotations", "book_annotations"],
    )
    async def update_annotation(
        self, annotation_id: int, user_id: int, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Cập nhật thông tin ghi chú.

        Args:
            annotation_id: ID của ghi chú
            user_id: ID của người dùng (để kiểm tra quyền)
            data: Dữ liệu cập nhật

        Returns:
            Thông tin ghi chú đã cập nhật

        Raises:
            NotFoundException: Nếu không tìm thấy ghi chú
            ForbiddenException: Nếu user_id không phải chủ sở hữu
        """
        with self.metrics.time_request("PUT", f"/annotations/{annotation_id}"):
            # Kiểm tra ghi chú tồn tại
            annotation = await self.annotation_repo.get_by_id(annotation_id)
            if not annotation:
                raise NotFoundException(
                    detail=f"Không tìm thấy ghi chú với ID {annotation_id}"
                )

            # Kiểm tra quyền
            if annotation.user_id != user_id:
                raise ForbiddenException(
                    detail="Bạn không có quyền cập nhật ghi chú này"
                )

            # Ngăn cập nhật user_id
            if "user_id" in data:
                del data["user_id"]

            # Sanitize content để tránh XSS
            if "content" in data and data["content"]:
                data["content"] = sanitize_html(data["content"])

            # Cập nhật
            updated = await self.annotation_repo.update(annotation_id, data)

            # Log the update activity
            try:
                # Track which fields were updated
                updated_fields = list(data.keys())

                await create_user_activity_log(
                    self.db,
                    UserActivityLogCreate(
                        user_id=user_id,
                        activity_type="UPDATE",
                        entity_type="ANNOTATION",
                        entity_id=annotation_id,
                        description=f"Updated annotation in book ID: {updated.book_id}",
                        metadata={
                            "book_id": updated.book_id,
                            "chapter_id": updated.chapter_id,
                            "is_public": updated.is_public,
                            "updated_fields": updated_fields,
                        },
                    ),
                )

                # Invalidate specific caches
                await self.cache.delete(f"annotation:{annotation_id}")
                await self.cache.delete(f"user_annotations:{user_id}")
                if updated.book_id:
                    await self.cache.delete(f"book_annotations:{updated.book_id}")
                if updated.chapter_id:
                    await self.cache.delete(f"chapter_annotations:{updated.chapter_id}")

            except Exception:
                # Log but don't fail if logging fails
                pass

            return {
                "id": updated.id,
                "user_id": updated.user_id,
                "book_id": updated.book_id,
                "chapter_id": updated.chapter_id,
                "content": updated.content,
                "text_position": updated.text_position,
                "text_context": updated.text_context,
                "color": updated.color,
                "is_public": updated.is_public,
                "created_at": updated.created_at,
                "updated_at": updated.updated_at,
            }

    @invalidate_cache(
        namespace="annotations",
        tags=["annotation_details", "user_annotations", "book_annotations"],
    )
    async def delete_annotation(self, annotation_id: int, user_id: int) -> bool:
        """
        Xóa ghi chú.

        Args:
            annotation_id: ID của ghi chú
            user_id: ID của người dùng (để kiểm tra quyền)

        Returns:
            True nếu xóa thành công

        Raises:
            NotFoundException: Nếu không tìm thấy ghi chú
            ForbiddenException: Nếu user_id không phải chủ sở hữu
        """
        with self.metrics.time_request("DELETE", f"/annotations/{annotation_id}"):
            # Kiểm tra ghi chú tồn tại
            annotation = await self.annotation_repo.get_by_id(annotation_id)
            if not annotation:
                raise NotFoundException(
                    detail=f"Không tìm thấy ghi chú với ID {annotation_id}"
                )

            # Kiểm tra quyền
            if annotation.user_id != user_id:
                raise ForbiddenException(detail="Bạn không có quyền xóa ghi chú này")

            # Delete the annotation
            result = await self.annotation_repo.delete(annotation_id)

            if result:
                # Log the deletion activity
                try:
                    await create_user_activity_log(
                        self.db,
                        UserActivityLogCreate(
                            user_id=user_id,
                            activity_type="DELETE",
                            entity_type="ANNOTATION",
                            entity_id=annotation_id,
                            description=f"Deleted annotation from book ID: {annotation.book_id}",
                            metadata={
                                "book_id": annotation.book_id,
                                "chapter_id": annotation.chapter_id,
                            },
                        ),
                    )

                    # Invalidate specific caches
                    await self.cache.delete(f"annotation:{annotation_id}")
                    await self.cache.delete(f"user_annotations:{user_id}")
                    book_id = annotation.book_id
                    chapter_id = annotation.chapter_id

                    if book_id:
                        await self.cache.delete(f"book_annotations:{book_id}")
                    if chapter_id:
                        await self.cache.delete(f"chapter_annotations:{chapter_id}")

                    # Track metrics
                    self.metrics.track_user_activity("delete_annotation")

                except Exception:
                    # Log but don't fail if logging fails
                    pass

            return result

    @cached(ttl=300, namespace="annotations")
    async def count_user_annotations(
        self,
        user_id: int,
        book_id: Optional[int] = None,
        chapter_id: Optional[int] = None,
    ) -> int:
        """
        Đếm số lượng ghi chú của người dùng.

        Args:
            user_id: ID của người dùng
            book_id: Lọc theo ID sách (tùy chọn)
            chapter_id: Lọc theo ID chương (tùy chọn)

        Returns:
            Số lượng ghi chú
        """
        return await self.annotation_repo.count_by_user(user_id, book_id, chapter_id)

    async def bulk_create_annotations(
        self, user_id: int, annotations: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Tạo nhiều ghi chú cùng lúc.

        Args:
            user_id: ID của người dùng
            annotations: Danh sách các dữ liệu ghi chú

        Returns:
            Danh sách ghi chú đã tạo
        """
        results = []
        book_ids = set()
        chapter_ids = set()

        for data in annotations:
            # Đảm bảo user_id được thiết lập
            data["user_id"] = user_id

            # Đảm bảo có các trường bắt buộc
            required_fields = ["book_id", "content", "text_position"]
            if not all(field in data for field in required_fields):
                continue

            # Sanitize content để tránh XSS
            if "content" in data and data["content"]:
                data["content"] = sanitize_html(data["content"])

            # Tạo annotation
            try:
                annotation = await self.annotation_repo.create(data)

                # Track để invalidate cache
                if annotation.book_id:
                    book_ids.add(annotation.book_id)
                if annotation.chapter_id:
                    chapter_ids.add(annotation.chapter_id)

                # Log activity
                try:
                    await create_user_activity_log(
                        self.db,
                        UserActivityLogCreate(
                            user_id=user_id,
                            activity_type="CREATE",
                            entity_type="ANNOTATION",
                            entity_id=annotation.id,
                            description=f"Created annotation in book ID: {annotation.book_id}",
                            metadata={
                                "book_id": annotation.book_id,
                                "chapter_id": annotation.chapter_id,
                                "is_public": annotation.is_public,
                                "text_position": annotation.text_position,
                                "bulk": True,
                            },
                        ),
                    )
                except Exception:
                    pass

                results.append(
                    {
                        "id": annotation.id,
                        "user_id": annotation.user_id,
                        "book_id": annotation.book_id,
                        "chapter_id": annotation.chapter_id,
                        "content": annotation.content,
                        "text_position": annotation.text_position,
                        "text_context": annotation.text_context,
                        "color": annotation.color,
                        "is_public": annotation.is_public,
                        "created_at": annotation.created_at,
                        "updated_at": annotation.updated_at,
                    }
                )
            except Exception:
                # Skip failed annotations
                continue

        # Invalidate caches
        await self.cache.delete(f"user_annotations:{user_id}")
        for book_id in book_ids:
            await self.cache.delete(f"book_annotations:{book_id}")
        for chapter_id in chapter_ids:
            await self.cache.delete(f"chapter_annotations:{chapter_id}")

        # Track metrics
        if results:
            self.metrics.track_user_activity(
                "bulk_create_annotations", metadata={"count": len(results)}
            )

        return results

    @invalidate_cache(
        namespace="annotations", tags=["user_annotations", "book_annotations"]
    )
    async def delete_all_user_annotations(
        self, user_id: int, book_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Xóa tất cả ghi chú của người dùng.

        Args:
            user_id: ID của người dùng
            book_id: ID của sách (tùy chọn, nếu chỉ muốn xóa ghi chú của một sách)

        Returns:
            Thông báo kết quả
        """
        # Xóa tất cả ghi chú
        count = await self.annotation_repo.delete_by_user(user_id, book_id)

        if count > 0:
            # Log activity
            try:
                book_info = f" từ sách ID: {book_id}" if book_id else ""
                await create_user_activity_log(
                    self.db,
                    UserActivityLogCreate(
                        user_id=user_id,
                        activity_type="DELETE_ALL",
                        entity_type="ANNOTATIONS",
                        entity_id=0,
                        description=f"Deleted {count} annotations{book_info}",
                        metadata={
                            "count": count,
                            "book_id": book_id,
                        },
                    ),
                )

                # Track metrics
                self.metrics.track_user_activity(
                    "delete_all_annotations", metadata={"count": count}
                )
            except Exception:
                # Log but don't fail if logging fails
                pass

        return {
            "message": f"Đã xóa {count} ghi chú",
            "count": count,
        }
