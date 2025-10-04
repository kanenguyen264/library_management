from pydantic import BaseModel
from typing import Optional


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: Optional[int] = None


class TokenPayload(BaseModel):
    user_id: Optional[int] = None
    email: Optional[str] = None
    username: Optional[str] = None
    is_admin: Optional[bool] = None
    exp: Optional[int] = None


class RefreshToken(BaseModel):
    refresh_token: str
