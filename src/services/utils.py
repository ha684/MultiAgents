from src.common.types import Message
from src.utils.logger_conf import logger
from src.db.models.user import User
from src.common.gmail_api import GmailAPI
from src.config.settings import settings

gmail_api = GmailAPI(
    client_id=settings.google_client_id,
    client_secret=settings.google_client_secret,
    refresh_token=settings.google_refresh_token,
)


def get_message_id(m: Message | None) -> str | None:
    """Get message ID with error handling"""
    try:
        if not m or not m.metadata or "message_id" not in m.metadata:
            return None
        return m.metadata["message_id"]
    except Exception as e:
        logger.error(f"Error getting message ID: {e}")
        return None


def get_last_message_id(m: Message | None) -> str | None:
    """Get last message ID with error handling"""
    try:
        if not m or not m.metadata or "last_message_id" not in m.metadata:
            return None
        return m.metadata["last_message_id"]
    except Exception as e:
        logger.error(f"Error getting last message ID: {e}")
        return None


async def send_verification_email(user: User) -> None:
    """Send verification code email to user"""
    try:
        subject = "Your Email Verification Code"
        verification_code = user.email_verification_token

        body = f"""
Hello {user.full_name},

Thank you for registering with our service!

Your email verification code is: {verification_code}

Please enter this code on the verification page to complete your registration.

This verification code will expire on {user.email_verification_expires.strftime("%Y-%m-%d %H:%M:%S UTC")}.

If you didn't create this account, you can safely ignore this email.

Best regards,
The Team
        """.strip()

        await gmail_api.send_message(to_email=user.email, subject=subject, body=body)
    except Exception as e:
        logger.error(f"Failed to send verification email to {user.email}: {str(e)}")
        raise e


async def send_password_reset_email(user: User, reset_token: str) -> None:
    """Send password reset email to user"""
    try:
        subject = "Your Password Reset Code"

        body = f"""
        Hello {user.full_name},

        Thank you for requesting a password reset!

        Your password reset code is: {reset_token}

        Please enter this code on the password reset page to complete your password reset.

        This password reset code will expire on {user.password_reset_expires.strftime("%Y-%m-%d %H:%M:%S UTC")}.

        If you didn't request a password reset, you can safely ignore this email.

        Best regards,
        The Team
        """.strip()

        result = await gmail_api.send_message(
            to_email=user.email, subject=subject, body=body
        )

        if result:
            logger.info(f"Password reset email sent to {user.email}")
        else:
            logger.error(f"Failed to send password reset email to {user.email}")
            raise Exception("Failed to send password reset email")
    except Exception as e:
        logger.error(f"Failed to send password reset email to {user.email}: {str(e)}")
        raise
