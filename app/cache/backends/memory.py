import time
import threading
from typing import Any, Dict, List, Optional, Set, Tuple
from app.cache.serializers import serialize, deserialize
from app.logging.setup import get_logger

logger = get_logger(__name__)


class MemoryBackend:
    """
    In-memory cache backend.
    Useful cho development và single-server deployments.
    """

    def __init__(
        self, max_size: int = 1000, default_ttl: int = 3600, cleanup_interval: int = 60
    ):
        """
        Khởi tạo memory cache backend.

        Args:
            max_size: Maximum number of items in cache
            default_ttl: Default time to live in seconds
            cleanup_interval: Interval for cleanup task in seconds
        """
        self._cache: Dict[str, Tuple[Any, float, Dict[str, Any]]] = {}
        self._tag_index: Dict[str, Set[str]] = {}
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._cleanup_interval = cleanup_interval
        self._lock = threading.RLock()

        # Start cleanup task
        self._start_cleanup_task()

    def _start_cleanup_task(self) -> None:
        """Start periodic cleanup task to remove expired items."""

        def cleanup():
            while True:
                time.sleep(self._cleanup_interval)
                self._cleanup_expired()

        threading.Thread(target=cleanup, daemon=True).start()

    def _cleanup_expired(self) -> None:
        """Remove expired items from cache."""
        now = time.time()
        expired_keys = []

        with self._lock:
            for key, (_, expiry, _) in self._cache.items():
                if expiry <= now:
                    expired_keys.append(key)

            # Remove expired items
            for key in expired_keys:
                self._remove_key(key)

    def _remove_key(self, key: str) -> None:
        """
        Remove key from cache and tag indexes.

        Args:
            key: Cache key
        """
        # Get metadata to find tags
        if key in self._cache:
            _, _, metadata = self._cache[key]
            tags = metadata.get("tags", [])

            # Remove key from tag indexes
            for tag in tags:
                if tag in self._tag_index and key in self._tag_index[tag]:
                    self._tag_index[tag].remove(key)

                    # Clean up empty tag sets
                    if not self._tag_index[tag]:
                        del self._tag_index[tag]

            # Remove key from cache
            del self._cache[key]

    def _evict_if_full(self) -> None:
        """Evict oldest items if cache is full."""
        if len(self._cache) >= self._max_size:
            # Find the oldest entry
            oldest_key = None
            oldest_time = float("inf")

            for key, (_, _, metadata) in self._cache.items():
                timestamp = metadata.get("timestamp", float("inf"))
                if timestamp < oldest_time:
                    oldest_time = timestamp
                    oldest_key = key

            # Remove oldest entry
            if oldest_key:
                self._remove_key(oldest_key)

    async def get(self, key: str, default: Any = None) -> Any:
        """
        Get value from cache.

        Args:
            key: Cache key
            default: Default value if key not found

        Returns:
            Cached value or default
        """
        with self._lock:
            if key not in self._cache:
                return default

            value, expiry, _ = self._cache[key]

            # Check if expired
            if expiry <= time.time():
                self._remove_key(key)
                return default

            return value

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
            Whether operation was successful
        """
        with self._lock:
            # Check if cache is full
            if key not in self._cache:
                self._evict_if_full()

            # Set expiry time
            expires_at = time.time() + (ttl if ttl is not None else self._default_ttl)

            # Prepare metadata
            meta = metadata or {}
            meta["timestamp"] = time.time()

            if tags:
                meta["tags"] = tags

                # Add key to tag indexes
                for tag in tags:
                    if tag not in self._tag_index:
                        self._tag_index[tag] = set()
                    self._tag_index[tag].add(key)

            # Store in cache
            self._cache[key] = (value, expires_at, meta)

            return True

    async def delete(self, key: str) -> bool:
        """
        Delete value from cache.

        Args:
            key: Cache key

        Returns:
            Whether key was deleted
        """
        with self._lock:
            if key not in self._cache:
                return False

            self._remove_key(key)
            return True

    async def exists(self, key: str) -> bool:
        """
        Check if key exists in cache.

        Args:
            key: Cache key

        Returns:
            Whether key exists
        """
        with self._lock:
            if key not in self._cache:
                return False

            _, expiry, _ = self._cache[key]

            # Check if expired
            if expiry <= time.time():
                self._remove_key(key)
                return False

            return True

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
        with self._lock:
            # Check if key exists
            if key not in self._cache:
                # Create new counter
                await self.set(key, amount, ttl)
                return amount

            value, expiry, metadata = self._cache[key]

            # Check if expired
            if expiry <= time.time():
                # Create new counter
                await self.set(key, amount, ttl)
                return amount

            # Check if value is numeric
            if not isinstance(value, (int, float)):
                return None

            # Increment value
            new_value = value + amount

            # Update expiry if provided
            if ttl is not None:
                expiry = time.time() + ttl

            # Update cache
            self._cache[key] = (new_value, expiry, metadata)

            return new_value

    async def expire(self, key: str, ttl: int) -> bool:
        """
        Set expiration for key.

        Args:
            key: Cache key
            ttl: Time to live in seconds

        Returns:
            Whether operation was successful
        """
        with self._lock:
            if key not in self._cache:
                return False

            value, _, metadata = self._cache[key]
            expiry = time.time() + ttl

            # Update cache
            self._cache[key] = (value, expiry, metadata)

            return True

    async def clear(self, pattern: Optional[str] = None) -> int:
        """
        Clear cache by pattern.

        Args:
            pattern: Key pattern to clear

        Returns:
            Number of keys deleted
        """
        import re

        with self._lock:
            if not pattern or pattern == "*":
                count = len(self._cache)
                self._cache.clear()
                self._tag_index.clear()
                return count

            # Convert glob pattern to regex
            pattern_regex = pattern.replace(".", "\\.").replace("*", ".*")
            regex = re.compile(f"^{pattern_regex}$")

            # Find matching keys
            matching_keys = [key for key in self._cache.keys() if regex.match(key)]

            # Remove matching keys
            for key in matching_keys:
                self._remove_key(key)

            return len(matching_keys)

    async def invalidate_by_tags(self, tags: List[str]) -> int:
        """
        Invalidate cache by tags.

        Args:
            tags: List of tags

        Returns:
            Number of keys deleted
        """
        with self._lock:
            if not tags:
                return 0

            # Find all keys with these tags
            keys_to_delete = set()

            for tag in tags:
                if tag in self._tag_index:
                    keys_to_delete.update(self._tag_index[tag])

            # Delete keys
            for key in keys_to_delete:
                if key in self._cache:
                    self._remove_key(key)

            return len(keys_to_delete)


# Tạo alias để tương thích với factory.py
MemoryCache = MemoryBackend
