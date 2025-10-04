import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt

from app.core.config import settings

logger = logging.getLogger(__name__)


class TokenService:
    """Service for managing password reset tokens."""

    def __init__(self):
        self.secret_key = settings.SECRET_KEY
        self.algorithm = settings.ALGORITHM
        # Password reset tokens expire in 1 hour
        self.reset_token_expire_hours = 1

    def create_password_reset_token(self, email: str) -> str:
        """Create a password reset token for the given email."""
        expire = datetime.utcnow() + timedelta(hours=self.reset_token_expire_hours)

        to_encode = {
            "sub": email,
            "exp": expire,
            "type": "password_reset",
            "iat": datetime.utcnow(),
        }

        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)

        logger.info(f"Created password reset token for email: {email}")
        return encoded_jwt

    def verify_password_reset_token(self, token: str) -> Optional[str]:
        """Verify password reset token and return email if valid."""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])

            email: str = payload.get("sub")
            token_type: str = payload.get("type")

            if email is None or token_type != "password_reset":
                logger.warning("Invalid token payload")
                return None

            # Check if token is expired (jose already handles this, but let's be explicit)
            exp = payload.get("exp")
            if exp and datetime.utcnow().timestamp() > exp:
                logger.warning(f"Expired token for email: {email}")
                return None

            logger.info(
                f"Successfully verified password reset token for email: {email}"
            )
            return email

        except JWTError as e:
            logger.error(f"JWT error while verifying token: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error while verifying token: {str(e)}")
            return None

    def create_verification_token(self, email: str) -> str:
        """Create an email verification token."""
        expire = datetime.utcnow() + timedelta(
            hours=24
        )  # 24 hours for email verification

        to_encode = {
            "sub": email,
            "exp": expire,
            "type": "email_verification",
            "iat": datetime.utcnow(),
        }

        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)

        logger.info(f"Created email verification token for email: {email}")
        return encoded_jwt

    def verify_verification_token(self, token: str) -> Optional[str]:
        """Verify email verification token and return email if valid."""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])

            email: str = payload.get("sub")
            token_type: str = payload.get("type")

            if email is None or token_type != "email_verification":
                logger.warning("Invalid verification token payload")
                return None

            logger.info(
                f"Successfully verified email verification token for email: {email}"
            )
            return email

        except JWTError as e:
            logger.error(f"JWT error while verifying verification token: {str(e)}")
            return None
        except Exception as e:
            logger.error(
                f"Unexpected error while verifying verification token: {str(e)}"
            )
            return None

    def generate_secure_token(self, length: int = 32) -> str:
        """Generate a secure random token."""
        return secrets.token_urlsafe(length)


# Create a singleton instance
token_service = TokenService()
