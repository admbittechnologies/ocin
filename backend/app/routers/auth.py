import logging
from datetime import timedelta
from pydantic import BaseModel

from fastapi import APIRouter, Depends, Query, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.security import verify_password, create_access_token, decode_token
from app.core.dependencies import get_current_user
from app.schemas.user import UserCreate, UserLogin, TokenOut, UserOut
from app.services.user_service import create_user, get_user_by_email, get_user_by_id
from app.services.email_service import send_verification_email, generate_verification_token
from app.config import settings

logger = logging.getLogger("ocin")

router = APIRouter()


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    """Register a new user. Sends verification email. Does NOT log in until verified."""
    try:
        user = await create_user(db, user_data.email, user_data.password)
    except ValueError as e:
        logger.info({"event": "register", "email": user_data.email, "error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": str(e), "code": "USER_EXISTS"}
        )

    # Generate verification token and send email
    verification_token = generate_verification_token(str(user.id), user.email)
    user.verification_token = verification_token
    await db.commit()

    await send_verification_email(user.email, verification_token)

    logger.info({"event": "register_success", "user_id": str(user.id), "email": user.email})
    return {
        "success": True,
        "message": "Verification email sent. Please check your inbox.",
    }


@router.get("/verify-email")
async def verify_email(token: str = Query(...), db: AsyncSession = Depends(get_db)):
    """Verify a user's email address."""
    payload = decode_token(token)
    if payload is None or payload.get("type") != "email_verification":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Invalid or expired verification link", "code": "INVALID_TOKEN"},
        )

    user_id = payload.get("sub")
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "User not found", "code": "USER_NOT_FOUND"},
        )

    if user.email_verified:
        # Already verified, just log them in
        access_token = create_access_token(
            data={"sub": str(user.id)},
            expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        )
        return TokenOut(
            access_token=access_token,
            user=UserOut(id=str(user.id), email=user.email, plan=user.plan, email_verified=True, created_at=str(user.created_at)),
        )

    # Verify the email
    user.email_verified = True
    user.verification_token = None
    await db.commit()

    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    logger.info({"event": "email_verified", "user_id": str(user.id), "email": user.email})
    return TokenOut(
        access_token=access_token,
        user=UserOut(id=str(user.id), email=user.email, plan=user.plan, email_verified=True, created_at=str(user.created_at)),
    )


@router.post("/resend-verification")
async def resend_verification(data: dict, db: AsyncSession = Depends(get_db)):
    """Resend verification email."""
    email = data.get("email")
    if not email:
        raise HTTPException(status_code=400, detail={"error": "Email required"})

    user = await get_user_by_email(db, email)
    if user is None or user.email_verified:
        # Always return success to prevent email enumeration
        return {"success": True, "message": "If the email exists, a verification link has been sent."}

    verification_token = generate_verification_token(str(user.id), user.email)
    user.verification_token = verification_token
    await db.commit()

    await send_verification_email(user.email, verification_token)
    return {"success": True, "message": "Verification email sent."}


@router.post("/login", response_model=TokenOut)
async def login(user_data: UserLogin, db: AsyncSession = Depends(get_db)):
    """Login a user."""
    user = await get_user_by_email(db, user_data.email)

    if user is None or not verify_password(user_data.password, user.hashed_password):
        logger.info({"event": "login", "email": user_data.email, "error": "Invalid credentials"})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Invalid email or password", "code": "INVALID_CREDENTIALS"},
        )

    if not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "Please verify your email before logging in", "code": "EMAIL_NOT_VERIFIED"},
        )

    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    logger.info({"event": "login_success", "user_id": str(user.id), "email": user.email})
    return TokenOut(
        access_token=access_token,
        user=UserOut(id=str(user.id), email=user.email, plan=user.plan, email_verified=True, created_at=str(user.created_at)),
    )


@router.post("/refresh", response_model=TokenOut)
async def refresh_token(
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Refresh an access token."""
    user = await get_user_by_id(db, current_user.id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "User not found", "code": "USER_NOT_FOUND"},
        )

    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    return TokenOut(
        access_token=access_token,
        user=UserOut(id=str(user.id), email=user.email, plan=user.plan, email_verified=user.email_verified, created_at=str(user.created_at)),
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
    logger.info({"event": "forgot_password_request", "email": data.email})
    return {"success": True}


@router.post("/change-password")
async def change_password(
    data: ChangePasswordRequest,
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change the current user's password."""
    user = await get_user_by_id(db, current_user.id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "User not found", "code": "USER_NOT_FOUND"},
        )

    if not verify_password(data.current_password, user.hashed_password):
        logger.info({"event": "change_password", "user_id": str(user.id), "error": "Invalid current password"})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Current password is incorrect", "code": "INVALID_PASSWORD"},
        )

    from app.core.security import hash_password
    user.hashed_password = hash_password(data.new_password)
    await db.commit()

    logger.info({"event": "change_password_success", "user_id": str(user.id)})
    return {"success": True}
