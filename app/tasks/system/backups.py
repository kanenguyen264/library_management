"""
Tác vụ sao lưu

Module này cung cấp các tác vụ liên quan đến sao lưu:
- Sao lưu database
- Sao lưu file
- Kiểm tra tính toàn vẹn của bản sao lưu
"""

import os
import datetime
import time
import subprocess
import shutil
import glob
import gzip
import json
import hashlib
from typing import Dict, Any, List, Optional

from app.core.config import get_settings
from app.logging.setup import get_logger
from app.tasks.worker import celery_app
from app.tasks.base_task import BaseTask

# Lấy settings
settings = get_settings()

# Logger
logger = get_logger(__name__)


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="app.tasks.system.backups.backup_database",
    queue="system",
)
def backup_database(self) -> Dict[str, Any]:
    """
    Sao lưu database.

    Returns:
        Dict chứa kết quả sao lưu
    """
    try:
        logger.info("Starting database backup")

        # Timestamp để đặt tên file
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        # Thư mục sao lưu
        backup_dir = os.path.join(settings.BACKUP_DIR, "database")
        os.makedirs(backup_dir, exist_ok=True)

        # Tên file sao lưu
        backup_filename = f"db_backup_{timestamp}.sql.gz"
        backup_path = os.path.join(backup_dir, backup_filename)

        # Thực hiện sao lưu
        result = perform_db_backup(backup_path)

        if result["success"]:
            # Tính toán checksum
            file_checksum = calculate_file_checksum(backup_path)

            # Kiểm tra tính toàn vẹn
            check_result = verify_backup_integrity(backup_path, file_checksum)

            # Xóa các bản sao lưu cũ nếu cần
            cleanup_result = cleanup_old_backups(
                backup_dir, "db_backup_*.sql.gz", settings.MAX_DB_BACKUPS
            )

            # Thêm thông tin vào kết quả
            result.update(
                {
                    "checksum": file_checksum,
                    "integrity_check": check_result,
                    "cleanup_result": cleanup_result,
                }
            )

            # Lưu metadata
            save_backup_metadata(backup_path, result)

            logger.info(f"Database backup completed: {backup_path}")
        else:
            logger.error(f"Database backup failed: {result['error']}")

        return result

    except Exception as e:
        logger.error(f"Error backing up database: {str(e)}")
        return {
            "timestamp": datetime.datetime.now().isoformat(),
            "success": False,
            "error": str(e),
        }


def perform_db_backup(backup_path: str) -> Dict[str, Any]:
    """
    Thực hiện sao lưu database.

    Args:
        backup_path: Đường dẫn file sao lưu

    Returns:
        Dict chứa kết quả sao lưu
    """
    try:
        start_time = time.time()

        # Lấy thông tin kết nối database từ settings
        db_host = settings.DB_HOST
        db_port = settings.DB_PORT
        db_name = settings.DB_NAME
        db_user = settings.DB_USER
        db_password = settings.DB_PASSWORD

        # Tạo command để sao lưu
        pg_dump_cmd = [
            "pg_dump",
            f"--host={db_host}",
            f"--port={db_port}",
            f"--username={db_user}",
            f"--dbname={db_name}",
            "--format=plain",
            "--no-owner",
            "--no-acl",
        ]

        # Thiết lập biến môi trường cho mật khẩu
        env = os.environ.copy()
        env["PGPASSWORD"] = db_password

        # Chạy pg_dump và gzip đồng thời
        with open(backup_path, "wb") as f:
            # Chạy pg_dump
            pg_dump_proc = subprocess.Popen(
                pg_dump_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )

            # Chạy gzip để nén
            gzip_proc = subprocess.Popen(
                ["gzip"],
                stdin=pg_dump_proc.stdout,
                stdout=f,
                stderr=subprocess.PIPE,
            )

            # Đóng stdout của pg_dump để đảm bảo gzip nhận EOF
            pg_dump_proc.stdout.close()

            # Đợi các process hoàn thành
            gzip_proc.wait()
            pg_dump_ret = pg_dump_proc.wait()
            gzip_ret = gzip_proc.returncode

            # Kiểm tra kết quả
            if pg_dump_ret != 0:
                pg_dump_stderr = pg_dump_proc.stderr.read().decode("utf-8")
                return {
                    "success": False,
                    "error": f"pg_dump failed with code {pg_dump_ret}: {pg_dump_stderr}",
                }

            if gzip_ret != 0:
                gzip_stderr = gzip_proc.stderr.read().decode("utf-8")
                return {
                    "success": False,
                    "error": f"gzip failed with code {gzip_ret}: {gzip_stderr}",
                }

        # Lấy kích thước file
        file_size = os.path.getsize(backup_path)

        return {
            "success": True,
            "backup_path": backup_path,
            "size_bytes": file_size,
            "duration_seconds": time.time() - start_time,
            "timestamp": datetime.datetime.now().isoformat(),
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.datetime.now().isoformat(),
        }


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="app.tasks.system.backups.backup_files",
    queue="system",
)
def backup_files(self) -> Dict[str, Any]:
    """
    Sao lưu file.

    Returns:
        Dict chứa kết quả sao lưu
    """
    try:
        logger.info("Starting files backup")

        # Timestamp để đặt tên file
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        # Thư mục sao lưu
        backup_dir = os.path.join(settings.BACKUP_DIR, "files")
        os.makedirs(backup_dir, exist_ok=True)

        # Tên file sao lưu
        backup_filename = f"files_backup_{timestamp}.tar.gz"
        backup_path = os.path.join(backup_dir, backup_filename)

        # Thực hiện sao lưu
        result = perform_files_backup(backup_path)

        if result["success"]:
            # Tính toán checksum
            file_checksum = calculate_file_checksum(backup_path)

            # Kiểm tra tính toàn vẹn
            check_result = verify_backup_integrity(backup_path, file_checksum)

            # Xóa các bản sao lưu cũ nếu cần
            cleanup_result = cleanup_old_backups(
                backup_dir, "files_backup_*.tar.gz", settings.MAX_FILE_BACKUPS
            )

            # Thêm thông tin vào kết quả
            result.update(
                {
                    "checksum": file_checksum,
                    "integrity_check": check_result,
                    "cleanup_result": cleanup_result,
                }
            )

            # Lưu metadata
            save_backup_metadata(backup_path, result)

            logger.info(f"Files backup completed: {backup_path}")
        else:
            logger.error(f"Files backup failed: {result['error']}")

        return result

    except Exception as e:
        logger.error(f"Error backing up files: {str(e)}")
        return {
            "timestamp": datetime.datetime.now().isoformat(),
            "success": False,
            "error": str(e),
        }


def perform_files_backup(backup_path: str) -> Dict[str, Any]:
    """
    Thực hiện sao lưu file.

    Args:
        backup_path: Đường dẫn file sao lưu

    Returns:
        Dict chứa kết quả sao lưu
    """
    try:
        start_time = time.time()

        # Các thư mục cần sao lưu
        media_dirs = [
            os.path.join(settings.MEDIA_ROOT, "books"),
            os.path.join(settings.MEDIA_ROOT, "previews"),
            os.path.join(settings.MEDIA_ROOT, "thumbnails"),
        ]

        # Kiểm tra các thư mục tồn tại
        dirs_to_backup = [d for d in media_dirs if os.path.exists(d)]

        if not dirs_to_backup:
            return {
                "success": False,
                "error": "No directories to backup",
                "timestamp": datetime.datetime.now().isoformat(),
            }

        # Tạo command để sao lưu
        tar_cmd = [
            "tar",
            "-czf",
            backup_path,
        ] + dirs_to_backup

        # Chạy tar
        proc = subprocess.Popen(
            tar_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Đợi process hoàn thành
        stdout, stderr = proc.communicate()

        # Kiểm tra kết quả
        if proc.returncode != 0:
            return {
                "success": False,
                "error": f"tar failed with code {proc.returncode}: {stderr.decode('utf-8')}",
                "timestamp": datetime.datetime.now().isoformat(),
            }

        # Lấy kích thước file
        file_size = os.path.getsize(backup_path)

        return {
            "success": True,
            "backup_path": backup_path,
            "size_bytes": file_size,
            "backed_up_dirs": dirs_to_backup,
            "duration_seconds": time.time() - start_time,
            "timestamp": datetime.datetime.now().isoformat(),
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.datetime.now().isoformat(),
        }


def calculate_file_checksum(file_path: str) -> str:
    """
    Tính toán checksum của file.

    Args:
        file_path: Đường dẫn file

    Returns:
        Checksum của file
    """
    sha256_hash = hashlib.sha256()

    with open(file_path, "rb") as f:
        # Đọc và cập nhật hash theo từng khối
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)

    return sha256_hash.hexdigest()


def verify_backup_integrity(file_path: str, checksum: str) -> Dict[str, Any]:
    """
    Kiểm tra tính toàn vẹn của file sao lưu.

    Args:
        file_path: Đường dẫn file
        checksum: Checksum ban đầu

    Returns:
        Dict chứa kết quả kiểm tra
    """
    # Tính toán lại checksum
    verify_checksum = calculate_file_checksum(file_path)

    is_valid = verify_checksum == checksum

    return {
        "is_valid": is_valid,
        "original_checksum": checksum,
        "verification_checksum": verify_checksum,
    }


def cleanup_old_backups(
    backup_dir: str, pattern: str, max_backups: int
) -> Dict[str, Any]:
    """
    Xóa các bản sao lưu cũ.

    Args:
        backup_dir: Thư mục chứa bản sao lưu
        pattern: Mẫu tên file
        max_backups: Số lượng bản sao lưu tối đa cần giữ lại

    Returns:
        Dict chứa kết quả dọn dẹp
    """
    try:
        # Lấy danh sách file sao lưu
        backup_pattern = os.path.join(backup_dir, pattern)
        backup_files = glob.glob(backup_pattern)

        # Sắp xếp theo thời gian sửa đổi
        backup_files.sort(key=os.path.getmtime)

        # Nếu số lượng file vượt quá giới hạn
        files_to_delete = (
            backup_files[:-max_backups] if len(backup_files) > max_backups else []
        )

        deleted_files = []
        total_size = 0

        # Xóa các file cũ
        for file_path in files_to_delete:
            try:
                # Lấy kích thước file
                file_size = os.path.getsize(file_path)
                total_size += file_size

                # Xóa file
                os.remove(file_path)

                # Xóa file metadata nếu có
                metadata_path = f"{file_path}.meta"
                if os.path.exists(metadata_path):
                    os.remove(metadata_path)

                # Lưu thông tin
                deleted_files.append(
                    {
                        "path": file_path,
                        "size": file_size,
                    }
                )
            except Exception as e:
                logger.warning(f"Error deleting backup file {file_path}: {str(e)}")

        return {
            "deleted_count": len(deleted_files),
            "total_size_bytes": total_size,
            "deleted_files": deleted_files,
        }

    except Exception as e:
        logger.error(f"Error cleaning up old backups: {str(e)}")
        return {
            "deleted_count": 0,
            "total_size_bytes": 0,
            "deleted_files": [],
            "error": str(e),
        }


def save_backup_metadata(backup_path: str, metadata: Dict[str, Any]) -> None:
    """
    Lưu metadata của bản sao lưu.

    Args:
        backup_path: Đường dẫn file sao lưu
        metadata: Thông tin metadata
    """
    try:
        # Tên file metadata
        metadata_path = f"{backup_path}.meta"

        # Lưu metadata
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

    except Exception as e:
        logger.error(f"Error saving backup metadata: {str(e)}")


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="app.tasks.system.backups.verify_backups",
    queue="system",
)
def verify_backups(self) -> Dict[str, Any]:
    """
    Kiểm tra tính toàn vẹn của các bản sao lưu.

    Returns:
        Dict chứa kết quả kiểm tra
    """
    try:
        logger.info("Starting backup verification")

        # Thư mục sao lưu
        db_backup_dir = os.path.join(settings.BACKUP_DIR, "database")
        files_backup_dir = os.path.join(settings.BACKUP_DIR, "files")

        # Kiểm tra các bản sao lưu database
        db_result = verify_backup_directory(db_backup_dir, "db_backup_*.sql.gz")

        # Kiểm tra các bản sao lưu file
        files_result = verify_backup_directory(
            files_backup_dir, "files_backup_*.tar.gz"
        )

        # Tổng hợp kết quả
        result = {
            "timestamp": datetime.datetime.now().isoformat(),
            "database_backups": db_result,
            "files_backups": files_result,
            "overall_status": "success",
        }

        # Xác định trạng thái tổng thể
        if not db_result["success"] or not files_result["success"]:
            result["overall_status"] = "error"

        logger.info(f"Backup verification completed: {result['overall_status']}")
        return result

    except Exception as e:
        logger.error(f"Error verifying backups: {str(e)}")
        return {
            "timestamp": datetime.datetime.now().isoformat(),
            "overall_status": "error",
            "error": str(e),
        }


def verify_backup_directory(backup_dir: str, pattern: str) -> Dict[str, Any]:
    """
    Kiểm tra tính toàn vẹn của các bản sao lưu trong thư mục.

    Args:
        backup_dir: Thư mục chứa bản sao lưu
        pattern: Mẫu tên file

    Returns:
        Dict chứa kết quả kiểm tra
    """
    try:
        # Lấy danh sách file sao lưu
        backup_pattern = os.path.join(backup_dir, pattern)
        backup_files = glob.glob(backup_pattern)

        # Sắp xếp theo thời gian sửa đổi
        backup_files.sort(key=os.path.getmtime, reverse=True)

        # Giới hạn số lượng file kiểm tra
        files_to_verify = backup_files[:5]  # Chỉ kiểm tra 5 file mới nhất

        results = []
        all_valid = True

        # Kiểm tra từng file
        for file_path in files_to_verify:
            try:
                # Đọc metadata
                metadata_path = f"{file_path}.meta"

                if not os.path.exists(metadata_path):
                    results.append(
                        {
                            "file": file_path,
                            "is_valid": False,
                            "error": "Metadata file not found",
                        }
                    )
                    all_valid = False
                    continue

                with open(metadata_path, "r") as f:
                    metadata = json.load(f)

                # Lấy checksum từ metadata
                checksum = metadata.get("checksum")

                if not checksum:
                    results.append(
                        {
                            "file": file_path,
                            "is_valid": False,
                            "error": "Checksum not found in metadata",
                        }
                    )
                    all_valid = False
                    continue

                # Kiểm tra tính toàn vẹn
                verify_result = verify_backup_integrity(file_path, checksum)

                results.append(
                    {
                        "file": file_path,
                        "is_valid": verify_result["is_valid"],
                        "details": verify_result,
                    }
                )

                if not verify_result["is_valid"]:
                    all_valid = False

            except Exception as e:
                results.append(
                    {
                        "file": file_path,
                        "is_valid": False,
                        "error": str(e),
                    }
                )
                all_valid = False

        return {
            "success": all_valid,
            "verified_count": len(results),
            "results": results,
        }

    except Exception as e:
        return {
            "success": False,
            "verified_count": 0,
            "results": [],
            "error": str(e),
        }
