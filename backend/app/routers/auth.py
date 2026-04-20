import logging
from datetime import timedelta
from pydantic import BaseModel

from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.security import verify_password, create_access_token
from app.core.dependencies import get_current_user
from app.schemas.user import UserCreate, UserLogin, TokenOut, UserOut
from app.services.user_service import create_user, get_user_by_email, get_user_by_id
from app.config import settings

logger = logging.getLogger("ocin")

router = APIRouter()


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    """Register a new user."""
    try:
        user = await create_user(db, user_data.email, user_data.password)
    except ValueError as e:
        logger.info({"event": "register", "email": user_data.email, "error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": str(e), "code": "USER_EXISTS"}
        )

    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    logger.info({"event": "register_success", "user_id": str(user.id), "email": user.email})
    return TokenOut(
        access_token=access_token,
        user=UserOut(id=str(user.id), email=user.email, plan=user.plan, created_at=str(user.created_at))
    )


@router.post("/login", response_model=TokenOut)
async def login(user_data: UserLogin, db: AsyncSession = Depends(get_db)):
    """Login a user."""
    user = await get_user_by_email(db, user_data.email)

    if user is None or not verify_password(user_data.password, user.hashed_password):
        logger.info({"event": "login", "email": user_data.email, "error": "Invalid credentials"})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Invalid email or password", "code": "INVALID_CREDENTIALS"}
        )

    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    logger.info({"event": "login_success", "user_id": str(user.id), "email": user.email})
    return TokenOut(
        access_token=access_token,
        user=UserOut(id=str(user.id), email=user.email, plan=user.plan, created_at=str(user.created_at))
    )


@router.post("/refresh", response_model=TokenOut)
async def refresh_token(
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Refresh an access token."""
    # Re-fetch user from DB to ensure they still exist
    user = await get_user_by_id(db, current_user.id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "User not found", "code": "USER_NOT_FOUND"}
        )

    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    return TokenOut(
        access_token=access_token,
        user=UserOut(id=str(user.id), email=user.email, plan=user.plan, created_at=str(user.created_at))
    )


@router.get("/me", response_model=UserOut)
async def get_me(current_user: UserOut = Depends(get_current_user)):
    """Get current user info."""
    return current_user


class ForgotPasswordRequest(BaseModel):
    email: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/forgot-password")
async def forgot_password(
    data: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """Request password reset. Always returns success to prevent email enumeration."""
    # Log the reset request (no email sending in v1)
    logger.info({"event": "forgot_password_request", "email": data.email})

    # Always return success, regardless of whether user exists
    return {"success": True}


@router.post("/change-password")
async def change_password(
    data: ChangePasswordRequest,
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change the current user's password."""
    # Re-fetch user from DB to get hashed_password
    user = await get_user_by_id(db, current_user.id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "User not found", "code": "USER_NOT_FOUND"}
        )

    # Verify current password
    if not verify_password(data.current_password, user.hashed_password):
        logger.info({"event": "change_password", "user_id": str(user.id), "error": "Invalid current password"})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Current password is incorrect", "code": "INVALID_PASSWORD"}
        )

    # Hash and store new password
    from app.core.security import hash_password
    user.hashed_password = hash_password(data.new_password)
    await db.commit()

    logger.info({"event": "change_password_success", "user_id": str(user.id)})
    return {"success": True}
