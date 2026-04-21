import logging
import secrets
from datetime import datetime, timedelta

import httpx
from jose import jwt

from app.config import settings

logger = logging.getLogger("ocin")


async def send_verification_email(to_email: str, verification_token: str) -> bool:
    """Send email verification via Mailjet."""
    base_url = settings.OCIN_PUBLIC_URL
    verify_link = f"{base_url}/verify-email?token={verification_token}"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://api.mailjet.com/v3.1/send",
                auth=(settings.MAILJET_API_KEY, settings.MAILJET_API_SECRET),
                json={
                    "Messages": [
                        {
                            "From": {"Email": settings.MAILJET_SENDER, "Name": "OCIN"},
                            "To": [{"Email": to_email}],
                            "Subject": "Verify your email — OCIN",
                            "TextPart": f"Welcome to OCIN!\n\nPlease verify your email by clicking:\n{verify_link}\n\nThis link expires in 24 hours.",
                            "HTMLPart": f"""
                            <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
                                <h2 style="color:#1a1a2e;">Welcome to OCIN</h2>
                                <p>Please verify your email address to get started.</p>
                                <a href="{verify_link}" 
                                   style="display:inline-block;padding:12px 24px;background:#1a1a2e;color:#fff;
                                          text-decoration:none;border-radius:6px;font-weight:bold;">
                                    Verify Email
                                </a>
                                <p style="color:#666;margin-top:20px;font-size:13px;">
                                    This link expires in 24 hours. If you didn't create an account, ignore this email.
                                </p>
                            </div>
                            """,
                        }
                    ]
                },
            )
            resp.raise_for_status()
            result = resp.json()
            logger.info({"event": "verification_email_sent", "email": to_email, "status": result})
            return True
    except Exception as e:
        logger.error({"event": "verification_email_failed", "email": to_email, "error": str(e)})
        return False


def generate_verification_token(user_id: str, email: str) -> str:
    """Generate a JWT verification token valid for 24h."""
    expire = datetime.utcnow() + timedelta(hours=24)
    payload = {"sub": user_id, "email": email, "type": "email_verification", "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
