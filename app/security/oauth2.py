from typing import Dict, List, Optional, Union, Any
import json
import requests
from urllib.parse import urlencode
from fastapi import HTTPException, status, Depends, Request
from fastapi.security import OAuth2AuthorizationCodeBearer
from pydantic import BaseModel, Field, validator
from datetime import datetime, timedelta
from app.core.config import get_settings
from app.logging.setup import get_logger
from app.core.security import create_access_token
from app.monitoring.metrics import track_auth_request
import os

settings = get_settings()
logger = get_logger(__name__)


class OAuth2Provider(BaseModel):
    """Thông tin cấu hình cho OAuth2 provider."""

    name: str
    client_id: str
    client_secret: str
    authorize_url: str
    token_url: str
    userinfo_url: str
    redirect_uri: str
    scope: str = "openid email profile"
    id_field: str = "sub"
    email_field: str = "email"
    name_field: str = "name"
    active: bool = True

    class Config:
        validate_assignment = True


class OAuthUserInfo(BaseModel):
    """Thông tin người dùng từ OAuth2 provider."""

    provider: str
    provider_user_id: str
    email: Optional[str] = None
    name: Optional[str] = None
    picture: Optional[str] = None
    raw_data: Dict[str, Any] = Field(default_factory=dict)


class OAuth2Manager:
    """
    Quản lý xác thực OAuth2 với nhiều providers.
    Hỗ trợ: Google, Facebook, GitHub, Microsoft, v.v.
    """

    def __init__(self):
        """Khởi tạo OAuth2 manager với providers được cấu hình."""
        self.providers: Dict[str, OAuth2Provider] = {}
        self._load_providers()

    def _load_providers(self):
        """Tải cấu hình providers từ settings hoặc biến môi trường."""
        providers_loaded = 0

        # Đọc API URL từ settings hoặc mặc định
        api_url = getattr(settings, "API_URL", "http://localhost:8000")

        # Google OAuth2
        google_client_id = os.environ.get("GOOGLE_CLIENT_ID") or getattr(
            settings, "GOOGLE_CLIENT_ID", None
        )
        google_client_secret = os.environ.get("GOOGLE_CLIENT_SECRET") or getattr(
            settings, "GOOGLE_CLIENT_SECRET", None
        )

        if google_client_id and google_client_secret:
            self.providers["google"] = OAuth2Provider(
                name="google",
                client_id=google_client_id,
                client_secret=google_client_secret,
                authorize_url="https://accounts.google.com/o/oauth2/auth",
                token_url="https://oauth2.googleapis.com/token",
                userinfo_url="https://www.googleapis.com/oauth2/v3/userinfo",
                redirect_uri=f"{api_url}/api/v1/auth/oauth/google/callback",
                scope="openid email profile",
            )
            providers_loaded += 1
        else:
            logger.warning(
                "Google OAuth2 không được cấu hình: Thiếu client_id hoặc client_secret"
            )

        # Facebook OAuth2
        facebook_client_id = os.environ.get("FACEBOOK_CLIENT_ID") or getattr(
            settings, "FACEBOOK_CLIENT_ID", None
        )
        facebook_client_secret = os.environ.get("FACEBOOK_CLIENT_SECRET") or getattr(
            settings, "FACEBOOK_CLIENT_SECRET", None
        )

        if facebook_client_id and facebook_client_secret:
            self.providers["facebook"] = OAuth2Provider(
                name="facebook",
                client_id=facebook_client_id,
                client_secret=facebook_client_secret,
                authorize_url="https://www.facebook.com/v13.0/dialog/oauth",
                token_url="https://graph.facebook.com/v13.0/oauth/access_token",
                userinfo_url="https://graph.facebook.com/me?fields=id,name,email,picture",
                redirect_uri=f"{api_url}/api/v1/auth/oauth/facebook/callback",
                scope="email public_profile",
                id_field="id",
                email_field="email",
                name_field="name",
            )
            providers_loaded += 1
        else:
            logger.warning(
                "Facebook OAuth2 không được cấu hình: Thiếu client_id hoặc client_secret"
            )

        # GitHub OAuth2
        github_client_id = os.environ.get("GITHUB_CLIENT_ID") or getattr(
            settings, "GITHUB_CLIENT_ID", None
        )
        github_client_secret = os.environ.get("GITHUB_CLIENT_SECRET") or getattr(
            settings, "GITHUB_CLIENT_SECRET", None
        )

        if github_client_id and github_client_secret:
            self.providers["github"] = OAuth2Provider(
                name="github",
                client_id=github_client_id,
                client_secret=github_client_secret,
                authorize_url="https://github.com/login/oauth/authorize",
                token_url="https://github.com/login/oauth/access_token",
                userinfo_url="https://api.github.com/user",
                redirect_uri=f"{api_url}/api/v1/auth/oauth/github/callback",
                scope="read:user user:email",
                id_field="id",
                email_field="email",
                name_field="name",
            )
            providers_loaded += 1
        else:
            logger.warning(
                "GitHub OAuth2 không được cấu hình: Thiếu client_id hoặc client_secret"
            )

        # Microsoft OAuth2
        microsoft_client_id = os.environ.get("MICROSOFT_CLIENT_ID") or getattr(
            settings, "MICROSOFT_CLIENT_ID", None
        )
        microsoft_client_secret = os.environ.get("MICROSOFT_CLIENT_SECRET") or getattr(
            settings, "MICROSOFT_CLIENT_SECRET", None
        )

        if microsoft_client_id and microsoft_client_secret:
            self.providers["microsoft"] = OAuth2Provider(
                name="microsoft",
                client_id=microsoft_client_id,
                client_secret=microsoft_client_secret,
                authorize_url="https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
                token_url="https://login.microsoftonline.com/common/oauth2/v2.0/token",
                userinfo_url="https://graph.microsoft.com/v1.0/me",
                redirect_uri=f"{api_url}/api/v1/auth/oauth/microsoft/callback",
                scope="openid email profile User.Read",
                id_field="id",
                email_field="userPrincipalName",
                name_field="displayName",
            )
            providers_loaded += 1
        else:
            logger.warning(
                "Microsoft OAuth2 không được cấu hình: Thiếu client_id hoặc client_secret"
            )

        if providers_loaded > 0:
            logger.info(
                f"Đã khởi tạo {providers_loaded} OAuth2 providers: {', '.join(self.providers.keys())}"
            )
        else:
            logger.warning(
                "Không có OAuth2 provider nào được cấu hình. Đăng nhập bằng OAuth2 sẽ không hoạt động."
            )

    def get_provider(self, provider_name: str) -> OAuth2Provider:
        """
        Lấy provider theo tên.

        Args:
            provider_name: Tên provider

        Returns:
            OAuth2Provider

        Raises:
            HTTPException: Nếu provider không tồn tại hoặc không active
        """
        provider = self.providers.get(provider_name.lower())

        if not provider:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Provider {provider_name} không được hỗ trợ.",
            )

        if not provider.active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Provider {provider_name} hiện không hoạt động.",
            )

        return provider

    def get_authorization_url(
        self, provider_name: str, state: Optional[str] = None
    ) -> str:
        """
        Tạo URL ủy quyền cho provider.

        Args:
            provider_name: Tên provider
            state: State để bảo vệ CSRF

        Returns:
            URL ủy quyền
        """
        provider = self.get_provider(provider_name)

        params = {
            "response_type": "code",
            "client_id": provider.client_id,
            "redirect_uri": provider.redirect_uri,
            "scope": provider.scope,
        }

        if state:
            params["state"] = state

        return f"{provider.authorize_url}?{urlencode(params)}"

    async def exchange_code_for_token(
        self, provider_name: str, code: str
    ) -> Dict[str, Any]:
        """
        Đổi authorization code lấy access token.

        Args:
            provider_name: Tên provider
            code: Authorization code

        Returns:
            Token response từ provider
        """
        provider = self.get_provider(provider_name)

        data = {
            "grant_type": "authorization_code",
            "client_id": provider.client_id,
            "client_secret": provider.client_secret,
            "code": code,
            "redirect_uri": provider.redirect_uri,
        }

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        # Đặc biệt cho GitHub
        if provider_name.lower() == "github":
            headers["Accept"] = "application/json"

        try:
            response = requests.post(
                provider.token_url, data=data, headers=headers, timeout=10
            )

            response.raise_for_status()

            # GitHub trả về application/x-www-form-urlencoded
            if (
                provider_name.lower() == "github"
                and "application/json" not in response.headers.get("Content-Type", "")
            ):
                import urllib.parse

                return dict(urllib.parse.parse_qsl(response.text))

            return response.json()

        except requests.RequestException as e:
            logger.error(f"Lỗi khi trao đổi code với {provider_name}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Không thể trao đổi authorization code: {str(e)}",
            )

    async def get_user_info(
        self, provider_name: str, token_response: Dict[str, Any]
    ) -> OAuthUserInfo:
        """
        Lấy thông tin người dùng từ OAuth2 provider.

        Args:
            provider_name: Tên provider
            token_response: Token response từ provider

        Returns:
            OAuthUserInfo
        """
        provider = self.get_provider(provider_name)

        access_token = token_response.get("access_token")
        token_type = token_response.get("token_type", "Bearer")

        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token response không chứa access_token",
            )

        headers = {"Authorization": f"{token_type} {access_token}"}

        try:
            response = requests.get(provider.userinfo_url, headers=headers, timeout=10)

            response.raise_for_status()
            user_data = response.json()

            # Thử lấy email riêng cho GitHub nếu cần
            if provider_name.lower() == "github" and not user_data.get("email"):
                email_response = requests.get(
                    "https://api.github.com/user/emails", headers=headers, timeout=10
                )

                if email_response.status_code == 200:
                    emails = email_response.json()
                    primary_email = next((e for e in emails if e.get("primary")), None)
                    if primary_email:
                        user_data["email"] = primary_email.get("email")

            return OAuthUserInfo(
                provider=provider_name,
                provider_user_id=str(user_data.get(provider.id_field)),
                email=user_data.get(provider.email_field),
                name=user_data.get(provider.name_field),
                picture=self._extract_picture(provider_name, user_data),
                raw_data=user_data,
            )

        except requests.RequestException as e:
            logger.error(
                f"Lỗi khi lấy thông tin người dùng từ {provider_name}: {str(e)}"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Không thể lấy thông tin người dùng: {str(e)}",
            )

    def _extract_picture(
        self, provider_name: str, user_data: Dict[str, Any]
    ) -> Optional[str]:
        """
        Trích xuất URL avatar từ dữ liệu người dùng.

        Args:
            provider_name: Tên provider
            user_data: Dữ liệu người dùng

        Returns:
            URL avatar hoặc None
        """
        provider_name = provider_name.lower()

        if provider_name == "google":
            return user_data.get("picture")
        elif provider_name == "facebook":
            picture = user_data.get("picture", {})
            if isinstance(picture, dict):
                return picture.get("data", {}).get("url")
            return None
        elif provider_name == "github":
            return user_data.get("avatar_url")
        elif provider_name == "microsoft":
            # Cần API call riêng để lấy ảnh từ Microsoft Graph
            return None

        return None

    async def create_user_token(
        self, user_id: str, provider_name: str
    ) -> Dict[str, str]:
        """
        Tạo JWT token cho người dùng sau khi xác thực OAuth2.

        Args:
            user_id: ID người dùng
            provider_name: Tên provider

        Returns:
            Dict với access_token và token_type
        """
        # Theo dõi sự kiện xác thực
        track_auth_request(user_id, True, provider_name)

        access_token = create_access_token(subject=user_id, scopes=["user"])

        return {"access_token": access_token, "token_type": "bearer"}


# Tạo singleton instance
oauth2_manager = OAuth2Manager()


def get_oauth2_manager() -> OAuth2Manager:
    """
    Dependency để lấy OAuth2Manager.

    Returns:
        OAuth2Manager instance
    """
    return oauth2_manager
