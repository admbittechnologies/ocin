import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import User
from app.core.security import hash_password

logger = logging.getLogger("ocin")


async def create_user(db: AsyncSession, email: str, password: str) -> User:
    """Create a new user."""
    # Check if user already exists
    result = await db.execute(select(User).where(User.email == email))
    existing = result.scalar_one_or_none()
    if existing:
        logger.warning({"event": "create_user", "email": email, "error": "User already exists"})
        raise ValueError("User with this email already exists")

    user = User(
        email=email,
        hashed_password=hash_password(password),
        plan="free",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info({"event": "create_user", "user_id": str(user.id), "email": email})
    return user


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    """Get a user by email."""
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: str) -> User | None:
    """Get a user by ID."""
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
