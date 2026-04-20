import secrets
from datetime import datetime, timedelta
from typing import Optional
import base64

from passlib.context import CryptContext
from jose import jwt, JWTError
from cryptography.fernet import Fernet

from app.config import settings

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Encryption for API keys (Fernet)
_fernet: Optional[Fernet] = None


def get_fernet() -> Fernet:
    """Get or create Fernet instance for encryption."""
    global _fernet
    if _fernet is None:
        # Ensure key is 32 bytes for Fernet (base64 encoded)
        key = settings.ENCRYPTION_KEY
        if len(key) < 32:
            key = key.ljust(32, '0')
        elif len(key) > 32:
            key = key[:32]

        # Fernet requires a base64-encoded 32-byte key
        # If the key is not valid base64, encode the raw 32 bytes
        try:
            fernet_key = base64.urlsafe_b64encode(key[:32].encode()).decode()
            _fernet = Fernet(fernet_key)
        except Exception:
            # Fallback: try using the key as-is if it looks like valid base64
            _fernet = Fernet(key)
    return _fernet


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    # Bcrypt only uses the first 72 bytes of the password.
    # Truncate here to avoid passlib ValueError for longer passwords.
    password_bytes = password.encode('utf-8')
    if len(password_bytes) > 72:
        password = password_bytes[:72].decode('utf-8', errors='ignore')
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    # Bcrypt only uses first 72 bytes - truncate to avoid ValueError
    password_bytes = plain_password.encode('utf-8')
    if len(password_bytes) > 72:
        plain_password = password_bytes[:72].decode('utf-8', errors='ignore')
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT token."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None


def generate_api_key() -> str:
    """Generate a unique API key for a user."""
    return secrets.token_urlsafe(48)


def encrypt_value(value: str) -> str:
    """Encrypt a value using Fernet (for API keys)."""
    fernet = get_fernet()
    encrypted = fernet.encrypt(value.encode())
    return encrypted.decode()


def decrypt_value(encrypted_value: str) -> str:
    """Decrypt a value using Fernet."""
    fernet = get_fernet()
    decrypted = fernet.decrypt(encrypted_value.encode())
    return decrypted.decode()
