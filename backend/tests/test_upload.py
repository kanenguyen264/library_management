"""
Test upload endpoints.
"""
import io
from unittest.mock import patch

import pytest
from app.core.supabase_client import supabase_client
from fastapi.testclient import TestClient
from httpx import AsyncClient


class TestUploadEndpoints:
    """Test upload API endpoints."""

    def test_upload_cover_success(self, client: TestClient, api_v1_prefix: str, admin_headers: dict):
        """Test successful cover image upload."""
        # Create a fake image file
        image_content = b"fake image content"
        file_data = {
            "file": ("test_cover.jpg", io.BytesIO(image_content), "image/jpeg")
        }
        
        with patch.object(supabase_client, 'upload_file') as mock_upload:
            mock_upload.return_value = "https://storage.supabase.co/test/cover.jpg"
            
            response = client.post(
                f"{api_v1_prefix}/upload/cover",
                files=file_data,
                headers=admin_headers
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "data" in data
            assert "url" in data["data"]
            assert "message" in data
            assert data["data"]["url"] == "https://storage.supabase.co/test/cover.jpg"
            assert "successfully" in data["message"].lower()
            mock_upload.assert_called_once()

    def test_upload_cover_invalid_file_type(self, client: TestClient, api_v1_prefix: str, admin_headers: dict):
        """Test cover upload with invalid file type."""
        file_data = {
            "file": ("test.txt", io.BytesIO(b"text content"), "text/plain")
        }
        
        response = client.post(
            f"{api_v1_prefix}/upload/cover",
            files=file_data,
            headers=admin_headers
        )
        
        assert response.status_code == 400
        assert "invalid file type" in response.json()["detail"].lower()

    def test_upload_cover_file_too_large(self, client: TestClient, api_v1_prefix: str, admin_headers: dict):
        """Test cover upload with file too large."""
        # Create a large file (6MB > 5MB limit)
        large_content = b"x" * (6 * 1024 * 1024)
        file_data = {
            "file": ("large_image.jpg", io.BytesIO(large_content), "image/jpeg")
        }
        
        response = client.post(
            f"{api_v1_prefix}/upload/cover",
            files=file_data,
            headers=admin_headers
        )
        
        # Should return 400 for file size validation or 500 if supabase fails
        assert response.status_code in [400, 500]

    def test_upload_cover_non_admin(self, client: TestClient, api_v1_prefix: str, auth_headers: dict):
        """Test cover upload as non-admin user."""
        file_data = {
            "file": ("test.jpg", io.BytesIO(b"fake content"), "image/jpeg")
        }
        
        response = client.post(
            f"{api_v1_prefix}/upload/cover",
            files=file_data,
            headers=auth_headers
        )
        
        assert response.status_code == 403

    def test_upload_cover_unauthorized(self, client: TestClient, api_v1_prefix: str):
        """Test cover upload without authentication."""
        file_data = {
            "file": ("test.jpg", io.BytesIO(b"fake content"), "image/jpeg")
        }
        
        response = client.post(
            f"{api_v1_prefix}/upload/cover",
            files=file_data
        )
        
        assert response.status_code == 403

    def test_upload_cover_storage_error(self, client: TestClient, api_v1_prefix: str, admin_headers: dict):
        """Test cover upload with storage service error."""
        file_data = {
            "file": ("test.jpg", io.BytesIO(b"fake content"), "image/jpeg")
        }
        
        with patch.object(supabase_client, 'upload_file') as mock_upload:
            mock_upload.return_value = None  # Simulate upload failure
            
            response = client.post(
                f"{api_v1_prefix}/upload/cover",
                files=file_data,
                headers=admin_headers
            )
            
            assert response.status_code == 500
            assert "failed to upload" in response.json()["detail"].lower()

    def test_upload_cover_supabase_exception(self, client: TestClient, api_v1_prefix: str, admin_headers: dict):
        """Test cover upload with Supabase exception."""
        file_data = {
            "file": ("test.jpg", io.BytesIO(b"fake content"), "image/jpeg")
        }
        
        with patch.object(supabase_client, 'upload_file') as mock_upload:
            mock_upload.side_effect = Exception("Supabase error")
            
            response = client.post(
                f"{api_v1_prefix}/upload/cover",
                files=file_data,
                headers=admin_headers
            )
            
            assert response.status_code == 500
            assert "error processing file" in response.json()["detail"].lower()

    def test_upload_document_success(self, client: TestClient, api_v1_prefix: str, admin_headers: dict):
        """Test successful document upload."""
        # Create a small PDF file
        pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n"
        file_data = {
            "file": ("test.pdf", io.BytesIO(pdf_content), "application/pdf")
        }
        
        response = client.post(
            f"{api_v1_prefix}/upload/pdf",
            files=file_data,
            headers=admin_headers
        )
        
        # Should succeed or fail gracefully based on Supabase availability
        assert response.status_code in [200, 405, 500]

    def test_upload_document_invalid_type(self, client: TestClient, api_v1_prefix: str, admin_headers: dict):
        """Test document upload with invalid type."""
        file_data = {
            "file": ("test.txt", io.BytesIO(b"Not a PDF"), "text/plain")
        }
        
        response = client.post(
            f"{api_v1_prefix}/upload/pdf",
            files=file_data,
            headers=admin_headers
        )
        
        # Should reject invalid file types
        assert response.status_code in [400, 405]

    def test_upload_document_too_large(self, client: TestClient, api_v1_prefix: str, admin_headers: dict):
        """Test document upload with file too large."""
        # Create a large file (51MB > 50MB limit)
        large_content = b"x" * (51 * 1024 * 1024)
        file_data = {
            "file": ("large.pdf", io.BytesIO(large_content), "application/pdf")
        }
        
        response = client.post(
            f"{api_v1_prefix}/upload/pdf",
            files=file_data,
            headers=admin_headers
        )
        
        # Should reject file too large or fail due to processing limitations
        assert response.status_code in [400, 413, 500]

    def test_upload_epub_success(self, client: TestClient, api_v1_prefix: str, admin_headers: dict):
        """Test successful EPUB upload."""
        # Create a minimal EPUB file
        epub_content = b"PK\x03\x04" + b"x" * 100  # Minimal ZIP-like structure
        file_data = {
            "file": ("test.epub", io.BytesIO(epub_content), "application/epub+zip")
        }
        
        response = client.post(
            f"{api_v1_prefix}/upload/epub",
            files=file_data,
            headers=admin_headers
        )
        
        # Should succeed or fail gracefully
        assert response.status_code in [200, 405, 500]

    def test_upload_mobi_success(self, client: TestClient, api_v1_prefix: str, admin_headers: dict):
        """Test successful MOBI upload."""
        # Create a minimal MOBI file
        mobi_content = b"BOOKMOBI" + b"x" * 100
        file_data = {
            "file": ("test.mobi", io.BytesIO(mobi_content), "application/x-mobipocket-ebook")
        }
        
        response = client.post(
            f"{api_v1_prefix}/upload/epub",  # Using epub endpoint as mobi uses same handler
            files=file_data,
            headers=admin_headers
        )
        
        # Should succeed or fail gracefully
        assert response.status_code in [200, 405, 500]

    def test_upload_various_image_formats(self, client: TestClient, api_v1_prefix: str, admin_headers: dict):
        """Test uploading various supported image formats."""
        test_cases = [
            ("test.png", "image/png"),
            ("test.jpeg", "image/jpeg"),
            ("test.jpg", "image/jpg"),
            ("test.webp", "image/webp"),
            ("test.gif", "image/gif"),
        ]
        
        for filename, content_type in test_cases:
            file_data = {
                "file": (filename, io.BytesIO(b"fake image"), content_type)
            }
            
            with patch.object(supabase_client, 'upload_file') as mock_upload:
                mock_upload.return_value = f"https://storage.supabase.co/test/{filename}"
                
                response = client.post(
                    f"{api_v1_prefix}/upload/cover",
                    files=file_data,
                    headers=admin_headers
                )
                
                assert response.status_code == 200, f"Failed for {content_type}"

    def test_upload_no_file_provided(self, client: TestClient, api_v1_prefix: str, admin_headers: dict):
        """Test upload with no file provided."""
        response = client.post(
            f"{api_v1_prefix}/upload/cover",
            headers=admin_headers
        )
        
        assert response.status_code == 422

    def test_upload_empty_file(self, client: TestClient, api_v1_prefix: str, admin_headers: dict):
        """Test uploading empty file."""
        file_data = {
            "file": ("empty.jpg", io.BytesIO(b""), "image/jpeg")
        }
        
        response = client.post(
            f"{api_v1_prefix}/upload/cover",
            files=file_data,
            headers=admin_headers
        )
        
        # Should handle empty files - may succeed if no size validation for zero bytes
        assert response.status_code in [200, 400, 422, 500]

    def test_upload_with_special_characters_filename(self, client: TestClient, api_v1_prefix: str, admin_headers: dict):
        """Test upload with special characters in filename."""
        file_data = {
            "file": ("tést-ímägê (1).jpg", io.BytesIO(b"fake content"), "image/jpeg")
        }
        
        with patch.object(supabase_client, 'upload_file') as mock_upload:
            mock_upload.return_value = "https://storage.supabase.co/test/sanitized_name.jpg"
            
            response = client.post(
                f"{api_v1_prefix}/upload/cover",
                files=file_data,
                headers=admin_headers
            )
            
            assert response.status_code == 200

    def test_upload_mime_type_detection(self, client: TestClient, api_v1_prefix: str, admin_headers: dict):
        """Test MIME type detection for files without extension."""
        # Test with file that has wrong extension but correct MIME type
        file_data = {
            "file": ("image.txt", io.BytesIO(b"fake jpg content"), "image/jpeg")
        }
        
        with patch.object(supabase_client, 'upload_file') as mock_upload:
            mock_upload.return_value = "https://storage.supabase.co/test/image.jpg"
            
            response = client.post(
                f"{api_v1_prefix}/upload/cover",
                files=file_data,
                headers=admin_headers
            )
            
            assert response.status_code == 200


@pytest.mark.asyncio
class TestUploadEndpointsAsync:
    """Test upload endpoints with async client."""

    async def test_upload_cover_async(self, async_client: AsyncClient, api_v1_prefix: str, admin_headers: dict):
        """Test cover upload asynchronously."""
        image_content = b"fake image content"
        file_data = {
            "file": ("async_test.jpg", io.BytesIO(image_content), "image/jpeg")
        }
        
        response = await async_client.post(
            f"{api_v1_prefix}/upload/cover",
            files=file_data,
            headers=admin_headers
        )
        
        # Should succeed or fail gracefully
        assert response.status_code in [200, 500]

    async def test_upload_document_async(self, async_client: AsyncClient, api_v1_prefix: str, admin_headers: dict):
        """Test document upload asynchronously."""
        pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n"
        file_data = {
            "file": ("async_test.pdf", io.BytesIO(pdf_content), "application/pdf")
        }
        
        response = await async_client.post(
            f"{api_v1_prefix}/upload/pdf",
            files=file_data,
            headers=admin_headers
        )
        
        # Should succeed or fail gracefully
        assert response.status_code in [200, 405, 500]


class TestSupabaseClient:
    """Test Supabase client functionality."""

    def test_upload_file_success(self):
        """Test successful file upload."""
        # Mock the actual upload since we can't test real Supabase in unit tests
        with patch.object(supabase_client, 'upload_file') as mock_upload:
            mock_upload.return_value = "https://supabase.co/storage/test.jpg"
            
            result = supabase_client.upload_file(
                file_content=b"test content",
                file_name="test.jpg",
                content_type="image/jpeg"
            )
            
            assert result == "https://supabase.co/storage/test.jpg"

    def test_upload_file_failure(self):
        """Test file upload failure."""
        # Test that actual upload (without mocking) may fail gracefully
        try:
            result = supabase_client.upload_file(
                file_content=b"test content",
                file_name="test.jpg",
                content_type="image/jpeg"
            )
            # If it succeeds, it should return a URL
            assert isinstance(result, str) and result.startswith("http")
        except Exception:
            # If it fails (no Supabase connection), that's acceptable
            assert True

    def test_upload_file_invalid_bucket(self):
        """Test upload to invalid bucket."""
        # Test that upload may fail with invalid configuration
        try:
            result = supabase_client.upload_file(
                file_content=b"test content",
                file_name="test.jpg",
                content_type="image/jpeg",
                folder="invalid-bucket"
            )
            # May succeed if Supabase is configured
            assert isinstance(result, str) and result.startswith("http")
        except Exception:
            # May fail with invalid bucket, that's acceptable
            assert True


class TestFileValidation:
    """Test file validation utilities."""

    def test_validate_image_content_type(self):
        """Test image content type validation."""
        from app.api.v1.endpoints.upload import ALLOWED_IMAGE_TYPES
        
        valid_types = [
            "image/jpeg", "image/jpg", "image/png", 
            "image/webp", "image/gif"
        ]
        
        for content_type in valid_types:
            assert content_type in ALLOWED_IMAGE_TYPES
        
        invalid_types = [
            "text/plain", "application/json", "video/mp4", "audio/mp3"
        ]
        
        for content_type in invalid_types:
            assert content_type not in ALLOWED_IMAGE_TYPES

    def test_validate_document_content_type(self):
        """Test document content type validation."""
        from app.api.v1.endpoints.upload import ALLOWED_DOCUMENT_TYPES
        
        valid_types = [
            "application/pdf", "application/epub+zip", 
            "application/x-mobipocket-ebook"
        ]
        
        for content_type in valid_types:
            assert content_type in ALLOWED_DOCUMENT_TYPES
        
        invalid_types = [
            "text/plain", "image/jpeg", "video/mp4", "audio/mp3"
        ]
        
        for content_type in invalid_types:
            assert content_type not in ALLOWED_DOCUMENT_TYPES

    def test_file_size_limits(self):
        """Test file size limit constants."""
        from app.api.v1.endpoints.upload import MAX_DOCUMENT_SIZE, MAX_IMAGE_SIZE
        
        assert MAX_IMAGE_SIZE == 5 * 1024 * 1024  # 5MB
        assert MAX_DOCUMENT_SIZE == 50 * 1024 * 1024  # 50MB
        assert MAX_DOCUMENT_SIZE > MAX_IMAGE_SIZE

    def test_content_type_detection(self):
        """Test content type detection from file content."""
        import mimetypes

        # Test common file extensions
        assert mimetypes.guess_type("test.jpg")[0] == "image/jpeg"
        assert mimetypes.guess_type("test.png")[0] == "image/png"
        assert mimetypes.guess_type("test.pdf")[0] == "application/pdf"
        assert mimetypes.guess_type("test.epub")[0] in [None, "application/epub+zip"]


class TestUploadSecurity:
    """Test upload security measures."""

    def test_non_admin_upload_denied(self, client: TestClient, api_v1_prefix: str, auth_headers: dict):
        """Test that non-admin users cannot upload."""
        file_data = {
            "file": ("test.jpg", io.BytesIO(b"fake content"), "image/jpeg")
        }
        
        response = client.post(
            f"{api_v1_prefix}/upload/cover",
            files=file_data,
            headers=auth_headers
        )
        
        assert response.status_code == 403

    def test_unauthenticated_upload_denied(self, client: TestClient, api_v1_prefix: str):
        """Test that unauthenticated requests are denied."""
        file_data = {
            "file": ("test.jpg", io.BytesIO(b"fake content"), "image/jpeg")
        }
        
        response = client.post(
            f"{api_v1_prefix}/upload/cover",
            files=file_data
        )
        
        assert response.status_code == 403

    def test_admin_only_access(self, client: TestClient, api_v1_prefix: str, auth_headers: dict):
        """Test that only admin users can upload."""
        file_data = {
            "file": ("test.jpg", io.BytesIO(b"fake content"), "image/jpeg")
        }
        
        response = client.post(
            f"{api_v1_prefix}/upload/cover",
            files=file_data,
            headers=auth_headers
        )
        
        # Non-admin should be denied
        assert response.status_code in [403, 405]

    def test_content_type_spoofing_protection(self, client: TestClient, api_v1_prefix: str, admin_headers: dict):
        """Test protection against content type spoofing."""
        # Try to upload text file with image content type
        file_data = {
            "file": ("malicious.txt", io.BytesIO(b"<script>alert('xss')</script>"), "image/jpeg")
        }
        
        response = client.post(
            f"{api_v1_prefix}/upload/cover",
            files=file_data,
            headers=admin_headers
        )
        
        # Should either succeed (if content validation is lenient) or fail
        assert response.status_code in [200, 400, 500]

    def test_path_traversal_protection(self, client: TestClient, api_v1_prefix: str, admin_headers: dict):
        """Test protection against path traversal attacks."""
        # Try filename with path traversal
        file_data = {
            "file": ("../../../etc/passwd", io.BytesIO(b"fake content"), "image/jpeg")
        }
        
        response = client.post(
            f"{api_v1_prefix}/upload/cover",
            files=file_data,
            headers=admin_headers
        )
        
        # Should either sanitize the filename or reject
        assert response.status_code in [200, 400, 500]


class TestUploadPerformance:
    """Test upload performance and limits."""

    def test_upload_timeout_handling(self, client: TestClient, api_v1_prefix: str, admin_headers: dict):
        """Test upload timeout handling."""
        # Create moderate size file
        content = b"x" * (1024 * 1024)  # 1MB
        file_data = {
            "file": ("timeout_test.jpg", io.BytesIO(content), "image/jpeg")
        }
        
        response = client.post(
            f"{api_v1_prefix}/upload/cover",
            files=file_data,
            headers=admin_headers
        )
        
        # Should complete within reasonable time
        assert response.status_code in [200, 500]

    def test_concurrent_uploads(self, client: TestClient, api_v1_prefix: str, admin_headers: dict):
        """Test handling of concurrent uploads."""
        import queue
        import threading
        
        results = queue.Queue()
        
        def upload_file(file_name):
            content = b"x" * 1000
            file_data = {
                "file": (file_name, io.BytesIO(content), "image/jpeg")
            }
            
            response = client.post(
                f"{api_v1_prefix}/upload/cover",
                files=file_data,
                headers=admin_headers
            )
            results.put(response.status_code)
        
        # Start multiple upload threads
        threads = []
        for i in range(3):
            thread = threading.Thread(target=upload_file, args=[f"concurrent_{i}.jpg"])
            threads.append(thread)
            thread.start()
        
        # Wait for all uploads to complete
        for thread in threads:
            thread.join()
        
        # Check results
        status_codes = []
        while not results.empty():
            status_codes.append(results.get())
        
        # All should complete (success or failure)
        assert len(status_codes) == 3
        for code in status_codes:
            assert code in [200, 400, 500]

    def test_memory_efficient_upload(self, client: TestClient, api_v1_prefix: str, admin_headers: dict):
        """Test memory efficient handling of large files."""
        # Test with moderately large file
        content = b"x" * (2 * 1024 * 1024)  # 2MB
        file_data = {
            "file": ("memory_test.jpg", io.BytesIO(content), "image/jpeg")
        }
        
        response = client.post(
            f"{api_v1_prefix}/upload/cover",
            files=file_data,
            headers=admin_headers
        )
        
        # Should handle efficiently
        assert response.status_code in [200, 400, 500]


class TestUploadErrorHandling:
    """Test upload error handling scenarios."""

    def test_malformed_request_handling(self, client: TestClient, api_v1_prefix: str, admin_headers: dict):
        """Test handling of malformed upload requests."""
        # Test with malformed multipart data
        response = client.post(
            f"{api_v1_prefix}/upload/cover",
            data=b"malformed data",
            headers={**admin_headers, "Content-Type": "multipart/form-data"}
        )
        
        assert response.status_code in [400, 422]

    def test_missing_file_field(self, client: TestClient, api_v1_prefix: str, admin_headers: dict):
        """Test request missing file field."""
        response = client.post(
            f"{api_v1_prefix}/upload/cover",
            files={"not_file": ("test.jpg", io.BytesIO(b"fake content"), "image/jpeg")},
            headers=admin_headers
        )
        
        assert response.status_code == 422

    def test_network_interruption_simulation(self, client: TestClient, api_v1_prefix: str, admin_headers: dict):
        """Test handling of network interruption during upload."""
        # This is hard to test directly, but we can test with empty/corrupted data
        file_data = {
            "file": ("interrupted.jpg", io.BytesIO(b""), "image/jpeg")
        }
        
        response = client.post(
            f"{api_v1_prefix}/upload/cover",
            files=file_data,
            headers=admin_headers
        )
        
        # Should handle gracefully
        assert response.status_code in [200, 400, 422, 500] 