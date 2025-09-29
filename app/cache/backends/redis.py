import json
from typing import Any, Dict, List, Optional, Union
import redis.asyncio as redis
from app.core.config import get_settings
from app.cache.serializers import serialize, deserialize
from app.logging.setup import get_logger
import time

settings = get_settings()
logger = get_logger(__name__)


class RedisBackend:
    """
    Redis cache backend cho cache phân tán.
    Hỗ trợ các mục có time-to-live, tag-based invalidation,
    và serialization của các object phức tạp.
    """

    def __init__(
        self,
        redis_client: Optional[redis.Redis] = None,
        redis_host: str = settings.REDIS_HOST,
        redis_port: int = settings.REDIS_PORT,
        redis_password: Optional[str] = settings.REDIS_PASSWORD,
        redis_db: int = settings.REDIS_DB,
        key_prefix: str = "cache:",
        default_ttl: int = 3600,  # 1 hour
        use_json: bool = True,
        use_pickle: bool = False,
        serializer_version: str = "v1",
        key_encoding: str = "utf-8",
    ):
        """
        Khởi tạo Redis cache backend.

        Args:
            redis_client: Redis client
            redis_host: Redis host
            redis_port: Redis port
            redis_password: Redis password
            redis_db: Redis database
            key_prefix: Cache key prefix
            default_ttl: Default time to live in seconds
            use_json: Whether to use JSON serialization
            use_pickle: Whether to allow pickle serialization
            serializer_version: Serializer version
            key_encoding: Key encoding
        """
        self.client = redis_client

        if self.client is None:
            self.client = redis.from_url(
                f"redis://{':' + redis_password + '@' if redis_password else ''}{redis_host}:{redis_port}/{redis_db}"
            )

        self.key_prefix = key_prefix
        self.default_ttl = default_ttl
        self.use_json = use_json
        self.use_pickle = use_pickle
        self.serializer_version = serializer_version
        self.key_encoding = key_encoding
        self.metadata_suffix = "_meta"

    def _get_full_key(self, key: str) -> str:
        """
        Get full key with prefix.

        Args:
            key: Cache key

        Returns:
            Full key with prefix
        """
        return f"{self.key_prefix}{key}"

    def _get_metadata_key(self, key: str) -> str:
        """
        Get metadata key.

        Args:
            key: Cache key

        Returns:
            Metadata key
        """
        return f"{self._get_full_key(key)}{self.metadata_suffix}"

    def _encode_key(self, key: str) -> bytes:
        """
        Encode key.

        Args:
            key: Cache key

        Returns:
            Encoded key
        """
        return key.encode(self.key_encoding)

    async def get(self, key: str, default: Any = None) -> Any:
        """
        Get value from cache.

        Args:
            key: Cache key
            default: Default value if key not found

        Returns:
            Cached value or default
        """
        try:
            full_key = self._get_full_key(key)
            cached_value = await self.client.get(full_key)

            if cached_value is None:
                return default

            # Get metadata if available
            metadata_key = self._get_metadata_key(key)
            metadata_raw = await self.client.get(metadata_key)

            # Parse metadata
            metadata = {}
            if metadata_raw:
                try:
                    metadata = json.loads(metadata_raw)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse metadata for key: {key}")

            # Deserialize value
            serializer = metadata.get(
                "serializer", "json" if self.use_json else "pickle"
            )
            return deserialize(cached_value, serializer, self.use_pickle)

        except Exception as e:
            logger.error(f"Error getting from cache: {e}")
            return default

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds
            tags: List of tags for invalidation
            metadata: Additional metadata

        Returns:
            Whether the operation was successful
        """
        try:
            full_key = self._get_full_key(key)

            # Determine serializer based on value type
            serializer = "json" if self.use_json else "pickle"
            if (
                not self.use_json
                or isinstance(value, (bytes, bytearray))
                or callable(value)
            ):
                if not self.use_pickle:
                    logger.warning(
                        f"Cannot serialize non-JSON value without pickle: {key}"
                    )
                    return False
                serializer = "pickle"

            # Serialize value
            serialized_value = serialize(value, serializer)

            # Prepare metadata
            meta = metadata or {}
            meta.update(
                {
                    "serializer": serializer,
                    "version": self.serializer_version,
                    "timestamp": time.time(),
                }
            )

            # Add tags if provided
            if tags:
                meta["tags"] = tags
                # Add key to tag index
                pipe = self.client.pipeline()
                for tag in tags:
                    tag_key = f"{self.key_prefix}tag:{tag}"
                    pipe.sadd(tag_key, full_key)
                    pipe.expire(tag_key, ttl or self.default_ttl)
                await pipe.execute()

            # Set value and metadata
            pipe = self.client.pipeline()

            # Set value with TTL
            if ttl:
                pipe.setex(full_key, ttl, serialized_value)
            else:
                pipe.setex(full_key, self.default_ttl, serialized_value)

            # Set metadata with same TTL
            metadata_key = self._get_metadata_key(key)
            metadata_value = json.dumps(meta)
            if ttl:
                pipe.setex(metadata_key, ttl, metadata_value)
            else:
                pipe.setex(metadata_key, self.default_ttl, metadata_value)

            await pipe.execute()
            return True

        except Exception as e:
            logger.error(f"Error setting cache: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """
        Delete value from cache.

        Args:
            key: Cache key

        Returns:
            Whether the operation was successful
        """
        try:
            full_key = self._get_full_key(key)
            metadata_key = self._get_metadata_key(key)

            # Delete value and metadata
            pipe = self.client.pipeline()
            pipe.delete(full_key)
            pipe.delete(metadata_key)
            await pipe.execute()

            return True

        except Exception as e:
            logger.error(f"Error deleting from cache: {e}")
            return False

    async def exists(self, key: str) -> bool:
        """
        Check if key exists in cache.

        Args:
            key: Cache key

        Returns:
            Whether the key exists
        """
        try:
            full_key = self._get_full_key(key)
            return await self.client.exists(full_key) > 0

        except Exception as e:
            logger.error(f"Error checking cache existence: {e}")
            return False

    async def increment(
        self, key: str, amount: int = 1, ttl: Optional[int] = None
    ) -> Optional[int]:
        """
        Increment value in cache.

        Args:
            key: Cache key
            amount: Amount to increment
            ttl: Time to live in seconds

        Returns:
            New value or None if operation failed
        """
        try:
            full_key = self._get_full_key(key)

            pipe = self.client.pipeline()
            pipe.incrby(full_key, amount)

            if ttl:
                pipe.expire(full_key, ttl)
            elif not await self.client.ttl(full_key) > 0:
                pipe.expire(full_key, self.default_ttl)

            results = await pipe.execute()
            return results[0]

        except Exception as e:
            logger.error(f"Error incrementing cache: {e}")
            return None

    async def expire(self, key: str, ttl: int) -> bool:
        """
        Set expiration for key.

        Args:
            key: Cache key
            ttl: Time to live in seconds

        Returns:
            Whether the operation was successful
        """
        try:
            full_key = self._get_full_key(key)
            metadata_key = self._get_metadata_key(key)

            pipe = self.client.pipeline()
            pipe.expire(full_key, ttl)
            pipe.expire(metadata_key, ttl)
            results = await pipe.execute()

            return all(results)

        except Exception as e:
            logger.error(f"Error setting cache expiration: {e}")
            return False

    async def clear(self, pattern: Optional[str] = None) -> int:
        """
        Clear cache by pattern.

        Args:
            pattern: Key pattern to clear

        Returns:
            Number of keys deleted
        """
        try:
            pattern = pattern or "*"
            full_pattern = f"{self.key_prefix}{pattern}"

            # Get keys matching pattern
            cursor = b"0"
            keys = []

            while cursor:
                cursor, partial_keys = await self.client.scan(
                    cursor=cursor, match=full_pattern, count=1000
                )

                keys.extend(partial_keys)

                if cursor == b"0":
                    break

            # Delete keys
            if keys:
                return await self.client.delete(*keys)
            return 0

        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
            return 0

    async def invalidate_by_tags(self, tags: List[str]) -> int:
        """
        Invalidate cache by tags.

        Args:
            tags: List of tags

        Returns:
            Number of keys deleted
        """
        try:
            if not tags:
                return 0

            # Get all keys with these tags
            keys = set()
            for tag in tags:
                tag_key = f"{self.key_prefix}tag:{tag}"
                tag_keys = await self.client.smembers(tag_key)
                keys.update(tag_keys)

            # Delete keys
            deleted = 0
            if keys:
                deleted = await self.client.delete(*keys)

                # Also delete metadata keys
                metadata_keys = [f"{key}{self.metadata_suffix}" for key in keys]
                await self.client.delete(*metadata_keys)

                # Delete tag index
                for tag in tags:
                    tag_key = f"{self.key_prefix}tag:{tag}"
                    await self.client.delete(tag_key)

            return deleted

        except Exception as e:
            logger.error(f"Error invalidating cache by tags: {e}")
            return 0


# Tạo alias để tương thích với factory.py
RedisCache = RedisBackend
