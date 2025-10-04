import logging
import uuid
from typing import Optional
from urllib.parse import unquote, urlparse

from supabase import Client, create_client

from app.core.settings import settings

logger = logging.getLogger(__name__)


class SupabaseClient:
    def __init__(self):
        self.url = settings.SUPABASE_URL
        self.key = settings.SUPABASE_KEY
        self.bucket_name = settings.BUCKET_NAME

        if not self.url or not self.key:
            raise ValueError(
                "SUPABASE_URL and SUPABASE_KEY must be configured in settings"
            )

        self.client: Client = create_client(self.url, self.key)

    def upload_file(
        self,
        file_content: bytes,
        file_name: str,
        content_type: str = "image/jpeg",
        folder: str = "covers",
    ) -> Optional[str]:
        try:
            # Generate unique filename
            file_extension = file_name.split(".")[-1] if "." in file_name else "jpg"
            unique_filename = f"{uuid.uuid4()}.{file_extension}"

            # Create full path with folder
            full_path = f"{folder}/{unique_filename}"

            # Upload file
            response = self.client.storage.from_(self.bucket_name).upload(
                path=full_path,
                file=file_content,
                file_options={"content-type": content_type},
            )

            # Get public URL if upload successful
            public_url = self.client.storage.from_(self.bucket_name).get_public_url(
                full_path
            )
            logger.info(f"Successfully uploaded file to: {full_path}")
            return public_url

        except Exception as e:
            logger.error(f"Error uploading file {file_name}: {str(e)}")
            return None

    def delete_file(self, file_url: str) -> bool:
        if not file_url:
            return False

        try:
            # Clean URL and extract file path
            file_path = self._extract_file_path(file_url)
            if not file_path:
                logger.warning(f"Could not extract file path from URL: {file_url}")
                return False

            # Delete file from Supabase Storage
            response = self.client.storage.from_(self.bucket_name).remove([file_path])

            # Handle Supabase response
            if isinstance(response, list):
                if len(response) == 0:
                    # Empty array means file was not found/deleted
                    # Return True because the end result is the same - file is not in storage
                    logger.info(
                        f"File not found in storage (already deleted): {file_path}"
                    )
                    return True
                else:
                    # Non-empty array means files were processed
                    deleted_file = response[0]

                    # Check if it's an error object
                    if isinstance(deleted_file, dict):
                        if "error" in deleted_file or "message" in deleted_file:
                            logger.error(f"Supabase delete error: {deleted_file}")
                            return False
                        else:
                            logger.info(f"File successfully deleted: {file_path}")
                            return True
                    else:
                        logger.info(f"File deletion confirmed: {file_path}")
                        return True
            else:
                logger.warning(f"Unexpected response format from Supabase: {response}")
                return False

        except Exception as e:
            # Check if it's a "not found" error which is actually OK
            if "not found" in str(e).lower() or "404" in str(e):
                logger.info(
                    f"File not found error - treating as successful deletion: {file_url}"
                )
                return True
            logger.error(f"Error deleting file {file_url}: {str(e)}")
            return False

    def _extract_file_path(self, file_url: str) -> Optional[str]:
        try:
            if not file_url:
                return None

            # Parse URL to remove query parameters
            parsed_url = urlparse(file_url)
            clean_path = parsed_url.path

            # Remove URL encoding
            clean_path = unquote(clean_path)

            # Extract file path after '/object/public/{bucket_name}/'
            bucket_prefix = f"/object/public/{self.bucket_name}/"
            if bucket_prefix in clean_path:
                file_path = clean_path.split(bucket_prefix)[1]
                return file_path

            # Fallback: try to extract folder/filename pattern
            if "/covers/" in clean_path:
                idx = clean_path.find("/covers/")
                file_path = clean_path[idx + 1 :]  # Skip the leading /
                return file_path
            elif "/pdfs/" in clean_path:
                idx = clean_path.find("/pdfs/")
                file_path = clean_path[idx + 1 :]  # Skip the leading /
                return file_path
            elif "/epubs/" in clean_path:
                idx = clean_path.find("/epubs/")
                file_path = clean_path[idx + 1 :]  # Skip the leading /
                return file_path

            logger.warning(f"Could not extract file path from URL: {file_url}")
            return None

        except Exception as e:
            logger.error(f"Error extracting file path from {file_url}: {str(e)}")
            return None


# Singleton instance
supabase_client = SupabaseClient()
