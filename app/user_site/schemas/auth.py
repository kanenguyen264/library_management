from typing import Optional
from pydantic import BaseModel, EmailStr, Field, validator
from app.user_site.models.user import User
from app.user_site.schemas.user import UserResponse


class LoginRequest(BaseModel):
    username: str = Field(..., description="Username hoặc email")
    password: str = Field(..., min_length=1)
    remember_me: bool = Field(False, description="Ghi nhớ đăng nhập")


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse


class RegisterRequest(BaseModel):
    username: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="Tên đăng nhập, chỉ chấp nhận chữ cái, số và dấu gạch dưới",
    )
    email: EmailStr = Field(..., description="Địa chỉ email hợp lệ")
    password: str = Field(
        ...,
        min_length=8,
        description="Mật khẩu tối thiểu 8 ký tự, nên có chữ hoa, chữ thường, số và ký tự đặc biệt",
    )
    password_confirm: str = Field(
        ..., description="Xác nhận mật khẩu - phải khớp với mật khẩu"
    )
    full_name: Optional[str] = Field(
        None, max_length=100, description="Họ và tên đầy đủ"
    )
    display_name: Optional[str] = Field(None, max_length=50, description="Tên hiển thị")
    country: Optional[str] = Field(None, max_length=50, description="Quốc gia")
    language: Optional[str] = Field(
        None, max_length=10, description="Mã ngôn ngữ (vd: en, vi)"
    )

    @validator("username")
    def username_valid(cls, v):
        import re

        if not v or not v.strip():
            raise ValueError("Tên đăng nhập không được để trống")
        if not re.match(r"^[a-zA-Z0-9_]+$", v):
            raise ValueError("Tên đăng nhập chỉ được chứa chữ cái, số và dấu gạch dưới")
        return v

    @validator("full_name")
    def full_name_valid(cls, v, values):
        if v is None:
            return v
        if v.strip() == "" or v.strip() == "string":
            return None
        return v

    @validator("display_name")
    def display_name_valid(cls, v, values):
        if v is None:
            return values.get("username")
        if v.strip() == "" or v.strip() == "string":
            return values.get("username")
        return v

    @validator("country")
    def country_valid(cls, v):
        if v is None or v.strip() == "" or v.strip() == "string":
            return None
        return v

    @validator("language")
    def language_valid(cls, v):
        valid_languages = ["en", "vi", "fr", "de", "es", "ja", "ko", "zh"]

        if v is None or v.strip() == "" or v.strip() == "string":
            return "en"

        if v not in valid_languages:
            return "en"

        return v

    @validator("password_confirm")
    def passwords_match(cls, v, values, **kwargs):
        if "password" in values and v != values["password"]:
            raise ValueError("Mật khẩu không khớp")
        return v


class RegisterResponse(BaseModel):
    success: bool = True
    message: str
    user: dict  # Using dict instead of UserResponse to allow for simplified response structure


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8)
    new_password_confirm: str

    @validator("new_password_confirm")
    def new_passwords_match(cls, v, values, **kwargs):
        if "new_password" in values and v != values["new_password"]:
            raise ValueError("Mật khẩu mới không khớp")
        return v


class EmailVerificationRequest(BaseModel):
    token: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class TwoFactorVerifyRequest(BaseModel):
    temp_token: str = Field(
        ..., description="Token tạm thời từ bước đăng nhập đầu tiên"
    )
    code: str = Field(
        ..., min_length=6, max_length=6, description="Mã xác thực 6 chữ số"
    )


class TwoFactorSetupResponse(BaseModel):
    secret: str = Field(..., description="Secret key cho cài đặt 2FA")
    qr_code_url: str = Field(..., description="URL mã QR để quét bằng ứng dụng 2FA")
    message: str


class TwoFactorEnableRequest(BaseModel):
    code: str = Field(
        ..., min_length=6, max_length=6, description="Mã xác thực 6 chữ số"
    )


class TwoFactorDisableRequest(BaseModel):
    password: str = Field(..., description="Mật khẩu hiện tại để xác nhận")
