from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.auth import (
    create_access_token,
    get_current_user,
    get_password_hash,
    verify_password,
)
from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import DuplicateEmail
from app.crud.user import crud_user
from app.models.user import User
from app.schemas.response import CreateResponse, Messages, SuccessResponse
from app.schemas.token import Token
from app.schemas.user import (
    ForgotPasswordRequest,
    PasswordChangeRequest,
    ResetPasswordRequest,
    UserCreate,
    UserLogin,
    UserResponse,
)
from app.services.email_service import email_service
from app.services.token_service import token_service

# Constants
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES

router = APIRouter()


@router.post(
    "/register",
    response_model=CreateResponse[UserResponse],
    status_code=status.HTTP_201_CREATED,
)
def register(
    *,
    db: Session = Depends(get_db),
    user_in: UserCreate,
) -> Any:
    """
    Create new user.
    """
    user = crud_user.get_by_email(db, email=user_in.email)
    if user:
        raise DuplicateEmail()

    user = crud_user.get_by_username(db, username=user_in.username)
    if user:
        raise HTTPException(status_code=400, detail="Username already registered")

    user = crud_user.create(db, obj_in=user_in)

    # Send welcome email (optional, don't fail if email service is not configured)
    try:
        email_service.send_welcome_email(user.email, user.full_name)
    except Exception:
        # Log but don't fail registration if email fails
        pass

    return CreateResponse(message=Messages.REGISTER_SUCCESS, data=user)


@router.post("/login", response_model=SuccessResponse[Token])
def login_for_access_token(
    db: Session = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()
) -> Any:
    """
    OAuth2 compatible token login, get an access token for future requests
    """
    user = crud_user.authenticate(
        db, email=form_data.username, password=form_data.password
    )
    if not user:
        raise HTTPException(status_code=400, detail=Messages.INCORRECT_CREDENTIALS)
    elif not crud_user.is_active(user):
        raise HTTPException(status_code=400, detail=Messages.INACTIVE_USER)
    access_token = create_access_token(
        user.id, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return SuccessResponse(
        message=Messages.LOGIN_SUCCESSFUL,
        data={
            "access_token": access_token,
            "token_type": "bearer",
        },
    )


@router.post("/login-json", response_model=SuccessResponse[Token])
def login_json(user_in: UserLogin, db: Session = Depends(get_db)) -> Any:
    """
    JSON login endpoint
    """
    # Try email first, then username
    user = crud_user.authenticate(db, email=user_in.username, password=user_in.password)
    if not user:
        # Try as username
        user_by_username = crud_user.get_by_username(db, username=user_in.username)
        if user_by_username:
            user = crud_user.authenticate(
                db, email=user_by_username.email, password=user_in.password
            )

    if not user:
        raise HTTPException(status_code=400, detail=Messages.INCORRECT_CREDENTIALS)
    elif not crud_user.is_active(user):
        raise HTTPException(status_code=400, detail=Messages.INACTIVE_USER)
    access_token = create_access_token(
        user.id, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return SuccessResponse(
        message=Messages.LOGIN_SUCCESSFUL,
        data={
            "access_token": access_token,
            "token_type": "bearer",
        },
    )


@router.get("/me", response_model=SuccessResponse[UserResponse])
def read_users_me(
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Get current user.
    """
    return SuccessResponse(message=Messages.DATA_RETRIEVED, data=current_user)


@router.post("/test-token", response_model=SuccessResponse[UserResponse])
def test_token(current_user: User = Depends(get_current_user)) -> Any:
    """
    Test access token.
    """
    return SuccessResponse(message="Token is valid", data=current_user)


@router.post("/forgot-password", response_model=SuccessResponse[None])
def forgot_password(
    *,
    db: Session = Depends(get_db),
    password_reset: ForgotPasswordRequest,
) -> Any:
    """
    Password Recovery.
    """
    user = crud_user.get_by_email(db, email=password_reset.email)
    if not user:
        # Don't reveal whether the email exists or not for security
        return SuccessResponse(message=Messages.PASSWORD_RESET_SENT, data=None)

    password_reset_token = token_service.create_password_reset_token(email=user.email)

    try:
        email_service.send_password_reset_email(
            to_email=user.email,
            reset_token=password_reset_token,
            user_name=user.full_name,
        )
    except Exception:
        # Log error but don't expose it to user
        pass

    return SuccessResponse(message=Messages.PASSWORD_RESET_SENT, data=None)


@router.post("/reset-password", response_model=SuccessResponse[None])
def reset_password(
    *,
    db: Session = Depends(get_db),
    password_reset: ResetPasswordRequest,
) -> Any:
    """
    Reset password.
    """
    email = token_service.verify_password_reset_token(password_reset.token)
    if not email:
        raise HTTPException(status_code=400, detail="Invalid token")

    user = crud_user.get_by_email(db, email=email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    hashed_password = get_password_hash(password_reset.new_password)
    user.hashed_password = hashed_password
    db.add(user)
    db.commit()

    return SuccessResponse(message=Messages.PASSWORD_RESET_SUCCESS, data=None)


@router.post("/change-password", response_model=SuccessResponse[None])
def change_password(
    *,
    db: Session = Depends(get_db),
    password_change: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Change password.
    """
    if not verify_password(
        password_change.current_password, current_user.hashed_password
    ):
        raise HTTPException(status_code=400, detail="Incorrect password")

    hashed_password = get_password_hash(password_change.new_password)
    current_user.hashed_password = hashed_password
    db.add(current_user)
    db.commit()

    return SuccessResponse(message=Messages.PASSWORD_CHANGED, data=None)
