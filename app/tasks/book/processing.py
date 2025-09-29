"""
Tác vụ xử lý sách

Module này cung cấp các tác vụ liên quan đến xử lý sách:
- Xử lý file sách khi tải lên
- Tạo bản xem trước
- Trích xuất metadata
- Tạo thumbnail
"""

import os
import time
import asyncio
from typing import Dict, Any, Optional, List
import datetime
from pathlib import Path
import urllib.parse as http

from app.core.config import get_settings
from app.logging.setup import get_logger
from app.tasks.worker import celery_app
from app.tasks.base_task import BaseTask
from app.core.db import async_session

# Thêm các import cho xử lý file PDF
from reportlab.pdfgen import canvas

# Lấy settings
settings = get_settings()

# Logger
logger = get_logger(__name__)


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="app.tasks.book.processing.process_book_upload",
    queue="books",
    max_retries=3,
)
def process_book_upload(
    self, book_id: int, file_path: str, file_format: str = "epub"
) -> Dict[str, Any]:
    """
    Xử lý file sách sau khi tải lên.

    Args:
        book_id: ID của sách
        file_path: Đường dẫn đến file sách
        file_format: Định dạng file (epub, pdf, mobi, ...)

    Returns:
        Dict chứa thông tin sau khi xử lý
    """
    try:
        logger.info(
            f"Processing book upload for book_id={book_id}, format={file_format}"
        )

        # Kiểm tra file tồn tại
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Book file not found at: {file_path}")

        # Khởi tạo kết quả
        result = {
            "book_id": book_id,
            "file_path": file_path,
            "file_format": file_format,
            "processed_at": datetime.datetime.now().isoformat(),
            "status": "success",
        }

        # 1. Validate file
        validate_result = validate_book_file(file_path, file_format)
        result.update({"validation": validate_result})

        if not validate_result["is_valid"]:
            result["status"] = "error"
            result["error"] = validate_result["error"]
            return result

        # 2. Trích xuất metadata
        metadata = extract_book_metadata(book_id, file_path, file_format)
        result.update({"metadata": metadata})

        # 3. Tạo bản xem trước
        preview_path = generate_book_preview(book_id, file_path, file_format)
        result.update({"preview_path": preview_path})

        # 4. Tạo thumbnail
        thumbnail_path = generate_book_thumbnail(book_id, file_path, file_format)
        result.update({"thumbnail_path": thumbnail_path})

        # 5. Lưu vào storage
        storage_result = save_to_permanent_storage(book_id, file_path, file_format)
        result.update({"storage": storage_result})

        logger.info(f"Book processing completed for book_id={book_id}")
        return result

    except Exception as e:
        logger.error(f"Error processing book upload for book_id={book_id}: {str(e)}")
        self.retry(exc=e, countdown=60)


def validate_book_file(file_path: str, file_format: str) -> Dict[str, Any]:
    """
    Kiểm tra tính hợp lệ của file sách.

    Args:
        file_path: Đường dẫn đến file sách
        file_format: Định dạng file

    Returns:
        Dict chứa kết quả kiểm tra
    """
    try:
        result = {"is_valid": False, "details": {}}

        # Kiểm tra file tồn tại
        if not os.path.exists(file_path):
            result["error"] = "File not found"
            return result

        # Kiểm tra kích thước file
        file_size = os.path.getsize(file_path)
        result["details"]["file_size"] = file_size

        # File không được quá lớn (100MB)
        if file_size > 100 * 1024 * 1024:
            result["error"] = "File too large"
            return result

        # Kiểm tra định dạng file
        if file_format == "epub":
            is_valid_epub = validate_epub(file_path)
            if not is_valid_epub:
                result["error"] = "Invalid EPUB format"
                return result
        elif file_format == "pdf":
            is_valid_pdf = validate_pdf(file_path)
            if not is_valid_pdf:
                result["error"] = "Invalid PDF format"
                return result
        elif file_format == "mobi":
            is_valid_mobi = validate_mobi(file_path)
            if not is_valid_mobi:
                result["error"] = "Invalid MOBI format"
                return result

        # Nếu qua tất cả kiểm tra
        result["is_valid"] = True
        return result

    except Exception as e:
        return {
            "is_valid": False,
            "error": f"Validation error: {str(e)}",
            "details": {},
        }


def validate_epub(file_path: str) -> bool:
    """Kiểm tra tính hợp lệ của file EPUB."""
    try:
        # Thử đọc file bằng thư viện EPUB
        import zipfile

        with zipfile.ZipFile(file_path) as zf:
            # Kiểm tra file mimetype
            if "mimetype" not in zf.namelist():
                return False

            # Đọc nội dung mimetype
            mimetype = zf.read("mimetype").decode("utf-8").strip()
            if mimetype != "application/epub+zip":
                return False

            # Kiểm tra META-INF/container.xml
            if "META-INF/container.xml" not in zf.namelist():
                return False

        return True
    except:
        return False


def validate_pdf(file_path: str) -> bool:
    """Kiểm tra tính hợp lệ của file PDF."""
    try:
        # Đọc header của file
        with open(file_path, "rb") as f:
            header = f.read(5)
            # PDF header phải bắt đầu bằng %PDF-
            if header != b"%PDF-":
                return False
        return True
    except:
        return False


def validate_mobi(file_path: str) -> bool:
    """Kiểm tra tính hợp lệ của file MOBI."""
    try:
        # Đọc file để tìm signature
        with open(file_path, "rb") as f:
            content = f.read(60)
            # MOBI header thường xuất hiện ở offset 60
            if b"MOBI" not in content:
                return False
        return True
    except:
        return False


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="app.tasks.book.processing.extract_book_metadata",
    queue="books",
)
def extract_book_metadata(
    self, book_id: int, file_path: str, file_format: str
) -> Dict[str, Any]:
    """
    Trích xuất metadata từ file sách.

    Args:
        book_id: ID của sách
        file_path: Đường dẫn đến file sách
        file_format: Định dạng file

    Returns:
        Dict chứa metadata của sách
    """
    logger.info(f"Extracting metadata for book_id={book_id}")

    metadata = {
        "title": None,
        "author": None,
        "language": None,
        "publisher": None,
        "published_date": None,
        "description": None,
        "isbn": None,
        "page_count": None,
        "subjects": [],
        "cover_image": None,
    }

    try:
        if file_format == "epub":
            # Trích xuất metadata từ EPUB
            import zipfile
            import xml.etree.ElementTree as ET

            with zipfile.ZipFile(file_path) as zf:
                # Đọc container.xml để tìm OPF file
                container = ET.fromstring(zf.read("META-INF/container.xml"))
                opf_path = container.find(
                    ".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile"
                ).attrib["full-path"]

                # Đọc OPF file
                opf_content = zf.read(opf_path)
                opf = ET.fromstring(opf_content)

                # Trích xuất metadata
                ns = {
                    "dc": "http://purl.org/dc/elements/1.1/",
                    "opf": "http://www.idpf.org/2007/opf",
                }

                # Title
                title_elem = opf.find(".//{http://purl.org/dc/elements/1.1/}title")
                if title_elem is not None and title_elem.text:
                    metadata["title"] = title_elem.text

                # Author
                author_elem = opf.find(".//{http://purl.org/dc/elements/1.1/}creator")
                if author_elem is not None and author_elem.text:
                    metadata["author"] = author_elem.text

                # Language
                lang_elem = opf.find(".//{http://purl.org/dc/elements/1.1/}language")
                if lang_elem is not None and lang_elem.text:
                    metadata["language"] = lang_elem.text

                # Publisher
                publisher_elem = opf.find(
                    ".//{http://purl.org/dc/elements/1.1/}publisher"
                )
                if publisher_elem is not None and publisher_elem.text:
                    metadata["publisher"] = publisher_elem.text

                # Description
                desc_elem = opf.find(".//{http://purl.org/dc/elements/1.1/}description")
                if desc_elem is not None and desc_elem.text:
                    metadata["description"] = desc_elem.text

                # Subjects/Categories
                for subject in opf.findall(
                    ".//{http://purl.org/dc/elements/1.1/}subject"
                ):
                    if subject.text:
                        metadata["subjects"].append(subject.text)

                # ISBN
                for identifier in opf.findall(
                    ".//{http://purl.org/dc/elements/1.1/}identifier"
                ):
                    if "isbn" in (identifier.attrib.get("id", "") or "").lower():
                        metadata["isbn"] = identifier.text

                # Tìm cover image
                manifest = opf.find(".//{http://www.idpf.org/2007/opf}manifest")
                if manifest is not None:
                    for item in manifest.findall(
                        ".//{http://www.idpf.org/2007/opf}item"
                    ):
                        if (
                            "cover" in (item.attrib.get("id", "") or "").lower()
                            or "cover"
                            in (item.attrib.get("properties", "") or "").lower()
                        ):
                            metadata["cover_image"] = item.attrib.get("href")

        elif file_format == "pdf":
            # Trích xuất metadata từ PDF
            try:
                import PyPDF2

                with open(file_path, "rb") as f:
                    reader = PyPDF2.PdfFileReader(f)
                    info = reader.getDocumentInfo()

                    if info:
                        metadata["title"] = info.get("/Title")
                        metadata["author"] = info.get("/Author")
                        metadata["page_count"] = reader.getNumPages()
            except ImportError:
                logger.warning("PyPDF2 not installed. PDF metadata extraction limited.")

        # Lưu metadata vào database
        save_metadata_to_db(book_id, metadata)

        return metadata

    except Exception as e:
        logger.error(f"Error extracting metadata: {str(e)}")
        return metadata


def save_metadata_to_db(book_id: int, metadata: Dict[str, Any]) -> None:
    """
    Lưu metadata vào database.

    Args:
        book_id: ID của sách
        metadata: Metadata của sách
    """
    # Đây là phiên bản đơn giản
    # Trong thực tế sẽ cần sử dụng async với sqlalchemy
    try:

        async def update_book():
            from app.user_site.models.book import Book
            from sqlalchemy import select

            async with async_session() as session:
                # Lấy book từ database
                stmt = select(Book).where(Book.id == book_id)
                result = await session.execute(stmt)
                book = result.scalars().first()

                if book:
                    # Cập nhật thông tin
                    if metadata.get("title") and not book.title:
                        book.title = metadata["title"]
                    if metadata.get("author") and not book.author_name:
                        book.author_name = metadata["author"]
                    if metadata.get("language"):
                        book.language = metadata["language"]
                    if metadata.get("publisher"):
                        book.publisher = metadata["publisher"]
                    if metadata.get("description") and not book.description:
                        book.description = metadata["description"]
                    if metadata.get("isbn"):
                        book.isbn = metadata["isbn"]
                    if metadata.get("page_count"):
                        book.pages = metadata["page_count"]

                    # Lưu thay đổi
                    session.add(book)
                    await session.commit()

        # Chạy async task
        import asyncio

        loop = asyncio.get_event_loop()
        loop.run_until_complete(update_book())

    except Exception as e:
        logger.error(f"Error saving metadata to database: {str(e)}")


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="app.tasks.book.processing.generate_book_preview",
    queue="books",
)
def generate_book_preview(
    self, book_id: int, file_path: str, file_format: str = "epub"
) -> str:
    """
    Tạo bản xem trước cho sách (preview).

    Args:
        book_id: ID của sách
        file_path: Đường dẫn đến file sách
        file_format: Định dạng file

    Returns:
        Đường dẫn đến file preview
    """
    try:
        logger.info(f"Generating preview for book_id={book_id}")

        # Tạo thư mục lưu preview nếu chưa tồn tại
        preview_dir = os.path.join(settings.MEDIA_ROOT, "previews", str(book_id))
        os.makedirs(preview_dir, exist_ok=True)

        preview_path = os.path.join(preview_dir, f"preview.html")

        # Tạo nội dung preview tùy thuộc vào định dạng sách
        if file_format == "epub":
            # Trích xuất một số chương đầu từ EPUB
            import zipfile
            import xml.etree.ElementTree as ET

            with zipfile.ZipFile(file_path) as zf:
                # Đọc container.xml để tìm OPF file
                container = ET.fromstring(zf.read("META-INF/container.xml"))
                opf_path = container.find(
                    ".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile"
                ).attrib["full-path"]

                # Tính đường dẫn cơ sở từ OPF file
                if "/" in opf_path:
                    base_dir = os.path.dirname(opf_path) + "/"
                else:
                    base_dir = ""

                # Đọc OPF file
                opf = ET.fromstring(zf.read(opf_path))

                # Lấy spine - thứ tự các file HTML trong sách
                spine = opf.find(".//{http://www.idpf.org/2007/opf}spine")
                if spine is not None:
                    # Lấy manifest để map itemrefs to href
                    manifest = opf.find(".//{http://www.idpf.org/2007/opf}manifest")
                    id_to_href = {}

                    for item in manifest.findall(
                        ".//{http://www.idpf.org/2007/opf}item"
                    ):
                        item_id = item.attrib.get("id")
                        item_href = item.attrib.get("href")
                        if item_id and item_href:
                            id_to_href[item_id] = item_href

                    # Lấy 3 chương đầu tiên từ spine
                    preview_content = (
                        "<html><head><title>Book Preview</title></head><body>"
                    )
                    count = 0

                    for itemref in spine.findall(
                        ".//{http://www.idpf.org/2007/opf}itemref"
                    ):
                        idref = itemref.attrib.get("idref")
                        if idref and idref in id_to_href:
                            href = id_to_href[idref]
                            full_path = base_dir + href

                            try:
                                html_content = zf.read(full_path).decode("utf-8")
                                # Thêm vào preview
                                preview_content += (
                                    f"<div class='chapter'>{html_content}</div>"
                                )
                                count += 1

                                # Chỉ lấy 3 chương đầu cho preview
                                if count >= 3:
                                    break
                            except:
                                continue

                    preview_content += "</body></html>"

                    # Lưu preview
                    with open(preview_path, "w", encoding="utf-8") as f:
                        f.write(preview_content)

        elif file_format == "pdf":
            # Trích xuất một số trang đầu từ PDF
            try:
                import PyPDF2
                from reportlab.pdfgen import canvas

                with open(file_path, "rb") as f:
                    reader = PyPDF2.PdfFileReader(f)

                    # Tạo PDF mới chỉ chứa 10 trang đầu
                    writer = PyPDF2.PdfFileWriter()
                    max_pages = min(10, reader.getNumPages())

                    for i in range(max_pages):
                        writer.addPage(reader.getPage(i))

                    # Lưu file preview PDF
                    preview_pdf_path = os.path.join(preview_dir, "preview.pdf")
                    with open(preview_pdf_path, "wb") as out_pdf:
                        writer.write(out_pdf)

                    # Để compatibility, tạo một HTML tham chiếu đến PDF
                    with open(preview_path, "w", encoding="utf-8") as f:
                        f.write(
                            f"""
                        <html>
                        <head><title>PDF Preview</title></head>
                        <body>
                            <embed src="/media/previews/{book_id}/preview.pdf" type="application/pdf" width="100%" height="600px" />
                        </body>
                        </html>
                        """
                        )
            except ImportError:
                logger.warning("PyPDF2 not installed. PDF preview limited.")

                # Tạo HTML giả
                with open(preview_path, "w", encoding="utf-8") as f:
                    f.write(
                        "<html><body><p>Preview not available for this PDF.</p></body></html>"
                    )

        return preview_path

    except Exception as e:
        logger.error(f"Error generating book preview: {str(e)}")
        return ""


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="app.tasks.book.processing.generate_book_thumbnail",
    queue="books",
)
def generate_book_thumbnail(
    self, book_id: int, file_path: str, file_format: str = "epub"
) -> str:
    """
    Tạo thumbnail cho sách.

    Args:
        book_id: ID của sách
        file_path: Đường dẫn đến file sách
        file_format: Định dạng file

    Returns:
        Đường dẫn đến file thumbnail
    """
    try:
        logger.info(f"Generating thumbnail for book_id={book_id}")

        # Tạo thư mục lưu thumbnail nếu chưa tồn tại
        thumbnail_dir = os.path.join(settings.MEDIA_ROOT, "thumbnails", str(book_id))
        os.makedirs(thumbnail_dir, exist_ok=True)

        thumbnail_path = os.path.join(thumbnail_dir, "cover.jpg")

        # Tạo thumbnail dựa trên định dạng sách
        if file_format == "epub":
            # Trích xuất cover image từ EPUB
            import zipfile
            import xml.etree.ElementTree as ET
            from PIL import Image

            with zipfile.ZipFile(file_path) as zf:
                # Đọc container.xml để tìm OPF file
                container = ET.fromstring(zf.read("META-INF/container.xml"))
                opf_path = container.find(
                    ".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile"
                ).attrib["full-path"]

                # Tính đường dẫn cơ sở từ OPF file
                if "/" in opf_path:
                    base_dir = os.path.dirname(opf_path) + "/"
                else:
                    base_dir = ""

                # Đọc OPF file
                opf = ET.fromstring(zf.read(opf_path))

                # Tìm cover image
                cover_path = None

                # Phương pháp 1: Tìm meta với name="cover"
                meta_cover = opf.find(
                    ".//{http://www.idpf.org/2007/opf}meta[@name='cover']"
                )
                if meta_cover is not None:
                    cover_id = meta_cover.attrib.get("content")
                    if cover_id:
                        # Tìm item với id tương ứng
                        cover_item = opf.find(
                            f".//{http://www.idpf.org/2007/opf}item[@id='{cover_id}']"
                        )
                        if cover_item is not None:
                            cover_path = base_dir + cover_item.attrib.get("href")

                # Phương pháp 2: Tìm item với properties="cover-image"
                if not cover_path:
                    cover_item = opf.find(
                        ".//{http://www.idpf.org/2007/opf}item[@properties='cover-image']"
                    )
                    if cover_item is not None:
                        cover_path = base_dir + cover_item.attrib.get("href")

                # Phương pháp 3: Tìm item với id có chứa "cover"
                if not cover_path:
                    for item in opf.findall(".//{http://www.idpf.org/2007/opf}item"):
                        item_id = item.attrib.get("id", "").lower()
                        if "cover" in item_id and (
                            item.attrib.get("media-type", "").startswith("image/")
                            or ".jpg" in item.attrib.get("href", "").lower()
                            or ".jpeg" in item.attrib.get("href", "").lower()
                            or ".png" in item.attrib.get("href", "").lower()
                        ):
                            cover_path = base_dir + item.attrib.get("href")
                            break

                # Nếu tìm thấy cover image
                if cover_path:
                    # Lưu cover image
                    with open(thumbnail_path, "wb") as f:
                        f.write(zf.read(cover_path))

                    # Resize thumbnail
                    with Image.open(thumbnail_path) as img:
                        img.thumbnail((300, 450))
                        img.save(thumbnail_path)
                else:
                    # Tạo thumbnail mặc định
                    create_default_thumbnail(thumbnail_path)

        elif file_format == "pdf":
            # Trích xuất trang đầu từ PDF làm thumbnail
            try:
                import fitz  # PyMuPDF

                doc = fitz.open(file_path)
                if doc.page_count > 0:
                    page = doc[0]
                    pix = page.get_pixmap()
                    pix.save(thumbnail_path)

                    # Resize thumbnail
                    from PIL import Image

                    with Image.open(thumbnail_path) as img:
                        img.thumbnail((300, 450))
                        img.save(thumbnail_path)
                else:
                    # Tạo thumbnail mặc định
                    create_default_thumbnail(thumbnail_path)
            except ImportError:
                logger.warning("PyMuPDF not installed. Using default thumbnail.")
                create_default_thumbnail(thumbnail_path)

        # Cập nhật đường dẫn thumbnail trong database
        update_thumbnail_path(book_id, f"/media/thumbnails/{book_id}/cover.jpg")

        return thumbnail_path

    except Exception as e:
        logger.error(f"Error generating book thumbnail: {str(e)}")
        # Tạo thumbnail mặc định trong trường hợp lỗi
        thumbnail_dir = os.path.join(settings.MEDIA_ROOT, "thumbnails", str(book_id))
        os.makedirs(thumbnail_dir, exist_ok=True)
        thumbnail_path = os.path.join(thumbnail_dir, "cover.jpg")
        create_default_thumbnail(thumbnail_path)
        return thumbnail_path


def create_default_thumbnail(thumbnail_path: str) -> None:
    """
    Tạo thumbnail mặc định cho sách.

    Args:
        thumbnail_path: Đường dẫn lưu thumbnail
    """
    try:
        from PIL import Image, ImageDraw, ImageFont

        # Tạo một hình ảnh trống
        img = Image.new("RGB", (300, 450), color=(240, 240, 240))
        draw = ImageDraw.Draw(img)

        # Vẽ border
        draw.rectangle([(10, 10), (290, 440)], outline=(200, 200, 200))

        # Vẽ text "No Cover"
        try:
            font = ImageFont.truetype("arial.ttf", 30)
        except:
            font = ImageFont.load_default()

        draw.text((75, 200), "No Cover", fill=(150, 150, 150), font=font)

        # Lưu hình ảnh
        img.save(thumbnail_path)

    except Exception as e:
        logger.error(f"Error creating default thumbnail: {str(e)}")


def update_thumbnail_path(book_id: int, thumbnail_path: str) -> None:
    """
    Cập nhật đường dẫn thumbnail trong database.

    Args:
        book_id: ID của sách
        thumbnail_path: Đường dẫn thumbnail
    """
    try:

        async def update_book():
            from app.user_site.models.book import Book
            from sqlalchemy import select

            async with async_session() as session:
                # Lấy book từ database
                stmt = select(Book).where(Book.id == book_id)
                result = await session.execute(stmt)
                book = result.scalars().first()

                if book:
                    # Cập nhật đường dẫn thumbnail
                    book.cover_image = thumbnail_path

                    # Lưu thay đổi
                    session.add(book)
                    await session.commit()

        # Chạy async task
        import asyncio

        loop = asyncio.get_event_loop()
        loop.run_until_complete(update_book())

    except Exception as e:
        logger.error(f"Error updating thumbnail path: {str(e)}")


def save_to_permanent_storage(
    book_id: int, file_path: str, file_format: str
) -> Dict[str, Any]:
    """
    Lưu sách vào storage vĩnh viễn.

    Args:
        book_id: ID của sách
        file_path: Đường dẫn tạm của file sách
        file_format: Định dạng file

    Returns:
        Dict chứa thông tin lưu trữ
    """
    try:
        # Đường dẫn thư mục lưu trữ vĩnh viễn
        storage_dir = os.path.join(settings.MEDIA_ROOT, "books", str(book_id))
        os.makedirs(storage_dir, exist_ok=True)

        # Tên file cuối cùng
        final_filename = f"book.{file_format}"
        final_path = os.path.join(storage_dir, final_filename)

        # Copy file từ vị trí tạm thời sang vị trí vĩnh viễn
        import shutil

        shutil.copy2(file_path, final_path)

        # Cập nhật đường dẫn trong database
        async def update_book():
            from app.user_site.models.book import Book
            from sqlalchemy import select

            async with async_session() as session:
                # Lấy book từ database
                stmt = select(Book).where(Book.id == book_id)
                result = await session.execute(stmt)
                book = result.scalars().first()

                if book:
                    # Cập nhật đường dẫn file
                    book.file_path = f"/media/books/{book_id}/{final_filename}"
                    book.file_size = os.path.getsize(final_path)
                    book.file_format = file_format

                    # Lưu thay đổi
                    session.add(book)
                    await session.commit()

        # Chạy async task
        import asyncio

        loop = asyncio.get_event_loop()
        loop.run_until_complete(update_book())

        # Trả về thông tin
        return {
            "original_path": file_path,
            "storage_path": final_path,
            "public_url": f"/media/books/{book_id}/{final_filename}",
            "size": os.path.getsize(final_path),
        }

    except Exception as e:
        logger.error(f"Error saving to permanent storage: {str(e)}")
        return {
            "error": str(e),
            "original_path": file_path,
        }
