import time
from typing import Dict, List, Optional, Tuple, Any, Callable
import redis.asyncio as redis
import ipaddress
from app.core.config import get_settings
from app.logging.setup import get_logger

settings = get_settings()
logger = get_logger(__name__)

class DDoSProtection:
    """
    Lớp xử lý phòng chống DDoS với nhiều chiến lược:
    - Rate limiting theo tier
    - Phát hiện request patterns bất thường
    - IP whitelisting và blacklisting
    - Challenge-response cho client đáng ngờ
    """
    
    def __init__(
        self,
        redis_client: redis.Redis = None,
        redis_host: str = settings.REDIS_HOST,
        redis_port: int = settings.REDIS_PORT,
        redis_password: str = settings.REDIS_PASSWORD,
        redis_db: int = settings.REDIS_DB,
        whitelist: List[str] = None,
        blacklist: List[str] = None,
        rate_limits: Dict[str, int] = None,
        window_seconds: int = 60,
        block_duration: int = 3600,  # 1 hour
        suspicious_threshold: int = 10
    ):
        """
        Initialize DDoS protection.
        
        Args:
            redis_client: Redis client (optional)
            redis_host: Redis host
            redis_port: Redis port
            redis_password: Redis password
            redis_db: Redis database
            whitelist: List of IP addresses or CIDR ranges to always allow
            blacklist: List of IP addresses or CIDR ranges to always block
            rate_limits: Dict mapping tier names to request limits
            window_seconds: Time window for rate limiting in seconds
            block_duration: Duration to block IPs in seconds
            suspicious_threshold: Threshold for suspicious activity counter
        """
        self.redis_client = redis_client
        
        if not self.redis_client:
            self.redis_client = redis.from_url(
                f"redis://{':' + redis_password + '@' if redis_password else ''}{redis_host}:{redis_port}/{redis_db}"
            )
            
        # Network lists
        self.whitelist_networks = []
        if whitelist:
            for ip in whitelist:
                try:
                    self.whitelist_networks.append(ipaddress.ip_network(ip))
                except ValueError:
                    logger.warning(f"Invalid whitelist IP/CIDR: {ip}")
                    
        self.blacklist_networks = []
        if blacklist:
            for ip in blacklist:
                try:
                    self.blacklist_networks.append(ipaddress.ip_network(ip))
                except ValueError:
                    logger.warning(f"Invalid blacklist IP/CIDR: {ip}")
        
        # Rate limit configuration
        self.rate_limits = rate_limits or {
            "normal": 100,      # Normal users
            "suspicious": 30,   # Suspicious behavior
            "bot": 10           # Likely bots
        }
        self.window_seconds = window_seconds
        self.block_duration = block_duration
        self.suspicious_threshold = suspicious_threshold
        
        # Key prefixes
        self.key_prefix = "ddos:"
        self.counter_prefix = f"{self.key_prefix}counter:"
        self.block_prefix = f"{self.key_prefix}block:"
        self.tier_prefix = f"{self.key_prefix}tier:"
        self.suspicious_prefix = f"{self.key_prefix}suspicious:"
        self.challenged_prefix = f"{self.key_prefix}challenged:"
        
    async def is_ip_allowed(self, ip: str) -> bool:
        """
        Kiểm tra xem IP có được phép truy cập không.
        
        Args:
            ip: IP address to check
            
        Returns:
            True if allowed, False if blocked
        """
        try:
            ip_obj = ipaddress.ip_address(ip)
            
            # Check whitelist
            for network in self.whitelist_networks:
                if ip_obj in network:
                    return True
                    
            # Check blacklist
            for network in self.blacklist_networks:
                if ip_obj in network:
                    return False
                    
            # Check if IP is blocked
            is_blocked = await self.redis_client.exists(f"{self.block_prefix}{ip}")
            return not is_blocked
            
        except ValueError:
            logger.warning(f"Invalid IP address: {ip}")
            return False
    
    async def get_ip_tier(self, ip: str) -> str:
        """
        Lấy tier của IP address.
        
        Args:
            ip: IP address
            
        Returns:
            Tier name (normal, suspicious, bot)
        """
        tier = await self.redis_client.get(f"{self.tier_prefix}{ip}")
        return tier.decode() if tier else "normal"
    
    async def set_ip_tier(self, ip: str, tier: str, duration: int = None) -> None:
        """
        Đặt tier cho IP address.
        
        Args:
            ip: IP address
            tier: Tier name
            duration: Expiration time in seconds
        """
        if duration is None:
            duration = self.window_seconds * 5  # Default to 5 windows
            
        await self.redis_client.setex(
            f"{self.tier_prefix}{ip}",
            duration,
            tier
        )
        
    async def is_rate_limited(self, ip: str) -> bool:
        """
        Kiểm tra xem IP có bị giới hạn tốc độ không.
        
        Args:
            ip: IP address
            
        Returns:
            True if rate limited, False if allowed
        """
        # Check if already blocked
        if not await self.is_ip_allowed(ip):
            return True
            
        # Get tier and rate limit
        tier = await self.get_ip_tier(ip)
        limit = self.rate_limits.get(tier, self.rate_limits["normal"])
        
        # Increment counter
        window = int(time.time() / self.window_seconds)
        key = f"{self.counter_prefix}{ip}:{window}"
        
        # Increment with expiration
        count = await self.redis_client.incr(key)
        if count == 1:
            await self.redis_client.expire(key, self.window_seconds * 2)
            
        # Check if limit exceeded
        if count > limit:
            # Record suspicious activity
            await self.record_suspicious_activity(ip)
            return True
            
        return False
        
    async def record_suspicious_activity(self, ip: str) -> None:
        """
        Ghi nhận hoạt động đáng ngờ từ IP và nâng cấp/block nếu cần.
        
        Args:
            ip: IP address
        """
        key = f"{self.suspicious_prefix}{ip}"
        count = await self.redis_client.incr(key)
        
        # Set expiration if new key
        if count == 1:
            await self.redis_client.expire(key, 86400)  # 24 hours
            
        # Update tier based on suspicious count
        if count >= self.suspicious_threshold * 3:
            # Block the IP
            await self.block_ip(ip)
        elif count >= self.suspicious_threshold:
            # Move to bot tier
            await self.set_ip_tier(ip, "bot")
        elif count >= self.suspicious_threshold / 2:
            # Move to suspicious tier
            await self.set_ip_tier(ip, "suspicious")
            
    async def block_ip(self, ip: str, duration: int = None) -> None:
        """
        Block an IP address.
        
        Args:
            ip: IP address to block
            duration: Block duration in seconds
        """
        if duration is None:
            duration = self.block_duration
            
        await self.redis_client.setex(
            f"{self.block_prefix}{ip}",
            duration,
            "1"
        )
        
        # Log the block
        logger.warning(f"IP {ip} has been blocked for {duration} seconds due to suspicious activity")
        
    async def unblock_ip(self, ip: str) -> None:
        """
        Unblock an IP address.
        
        Args:
            ip: IP address to unblock
        """
        await self.redis_client.delete(f"{self.block_prefix}{ip}")
        await self.redis_client.delete(f"{self.suspicious_prefix}{ip}")
        await self.redis_client.delete(f"{self.tier_prefix}{ip}")
        
        # Log the unblock
        logger.info(f"IP {ip} has been unblocked")
        
    async def generate_challenge(self, ip: str) -> Dict[str, Any]:
        """
        Tạo một challenge cho client đáng ngờ (vd: JavaScript challenge, CAPTCHA).
        
        Args:
            ip: IP address
            
        Returns:
            Challenge data
        """
        import random
        import hashlib
        
        # Generate a simple math challenge
        a = random.randint(1, 10)
        b = random.randint(1, 10)
        operation = random.choice(["+", "*"])
        
        if operation == "+":
            answer = a + b
        else:
            answer = a * b
            
        # Create a token
        timestamp = int(time.time())
        token = hashlib.sha256(f"{ip}:{timestamp}:{answer}".encode()).hexdigest()
        
        # Store the expected answer
        await self.redis_client.setex(
            f"{self.challenged_prefix}{token}",
            300,  # 5 minutes
            str(answer)
        )
        
        return {
            "type": "math",
            "challenge": f"What is {a} {operation} {b}?",
            "token": token
        }
        
    async def verify_challenge(self, token: str, answer: str) -> bool:
        """
        Verify a challenge response.
        
        Args:
            token: Challenge token
            answer: User's answer
            
        Returns:
            True if correct, False otherwise
        """
        key = f"{self.challenged_prefix}{token}"
        expected = await self.redis_client.get(key)
        
        if not expected:
            return False
            
        # Delete the challenge to prevent reuse
        await self.redis_client.delete(key)
        
        return expected.decode() == answer
