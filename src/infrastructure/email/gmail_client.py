# src/infrastructure/email/gmail_client.py
import base64
from datetime import datetime, timedelta, timezone
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import Enum
import os
import re

import httpx

from src.utils.logger_conf import logger


class ErrorType(Enum):
    INVALID_EMAIL = "invalid_email"
    INVALID_TOKEN = "invalid_token"
    EXPIRED_TOKEN = "expired_token"
    INVALID_REFRESH_TOKEN = "invalid_refresh_token"
    QUOTA_EXCEEDED = "quota_exceeded"
    ATTACHMENT_TOO_LARGE = "attachment_too_large"
    NETWORK_ERROR = "network_error"
    UNKNOWN_ERROR = "unknown_error"


class GmailError(Exception):
    def __init__(self, error_type: ErrorType, message: str, original_error=None):
        self.error_type = error_type
        self.message = message
        self.original_error = original_error
        super().__init__(message)


class GmailAPI:
    def __init__(self, client_id, client_secret, refresh_token):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.access_token = None
        self.token_expires_at = None
        self.base_url = "https://gmail.googleapis.com/gmail/v1"

    def validate_email(self, email):
        """Validate email format"""
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        return re.match(pattern, email) is not None

    def analyze_error_response(self, response, context="general"):
        """Analyze error response and determine error type"""
        try:
            error_data = response.json()
        except Exception:
            error_data = {}

        status_code = response.status_code
        error_message = error_data.get("error", {}).get("message", "")

        if status_code == 401:
            if (
                "invalid_token" in error_message.lower()
                or "token" in error_message.lower()
            ):
                if context == "refresh_token":
                    return ErrorType.INVALID_REFRESH_TOKEN
                return ErrorType.INVALID_TOKEN
            elif "expired" in error_message.lower():
                return ErrorType.EXPIRED_TOKEN

        if status_code == 400:
            if any(
                keyword in error_message.lower()
                for keyword in ["invalid", "malformed", "bad request"]
            ):
                if context == "send_email" and (
                    "recipient" in error_message.lower()
                    or "to" in error_message.lower()
                ):
                    return ErrorType.INVALID_EMAIL

        if (
            status_code == 429
            or "quota" in error_message.lower()
            or "rate limit" in error_message.lower()
        ):
            return ErrorType.QUOTA_EXCEEDED

        if (
            status_code == 413
            or "too large" in error_message.lower()
            or "size" in error_message.lower()
        ):
            return ErrorType.ATTACHMENT_TOO_LARGE

        return ErrorType.UNKNOWN_ERROR

    async def get_access_token(self):
        """Get a new access token using refresh token"""
        url = "https://oauth2.googleapis.com/token"
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, data=data)

                if response.status_code == 200:
                    token_data = response.json()
                    self.access_token = token_data.get("access_token")
                    expires_in = token_data.get("expires_in", 3600)
                    self.token_expires_at = datetime.now(timezone.utc) + timedelta(
                        seconds=expires_in
                    )
                    logger.info("Access token obtained successfully!")
                    return self.access_token
                else:
                    error_type = self.analyze_error_response(response, "refresh_token")
                    error_message = f"Failed to get access token: {response.status_code} - {response.text}"
                    logger.error(error_message)
                    raise GmailError(error_type, error_message, response)

        except httpx.RequestError as e:
            logger.error(f"Network error while getting access token: {str(e)}")
            raise GmailError(ErrorType.NETWORK_ERROR, f"Network error: {str(e)}", e)

    def get_headers(self):
        """Get authorization headers"""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    async def ensure_valid_token(self):
        """Ensure we have a valid access token"""
        if not self.access_token or (
            self.token_expires_at
            and datetime.now(timezone.utc) >= self.token_expires_at
        ):
            await self.get_access_token()

    async def send_message(self, to_email, subject, body, attachments=None):
        """Send an email message with improved error handling"""
        if not self.validate_email(to_email):
            error_message = f"Invalid email format: {to_email}"
            logger.error(error_message)
            raise GmailError(ErrorType.INVALID_EMAIL, error_message)

        try:
            await self.ensure_valid_token()
        except GmailError:
            raise
        except Exception as e:
            raise GmailError(
                ErrorType.UNKNOWN_ERROR, f"Token validation failed: {str(e)}", e
            )
        try:
            message = MIMEMultipart()
            message["to"] = to_email
            message["subject"] = subject
            message.attach(MIMEText(body, "plain"))

            if attachments:
                total_size = 0
                for file_path in attachments:
                    if os.path.exists(file_path):
                        file_size = os.path.getsize(file_path)
                        total_size += file_size
                        if total_size > 25 * 1024 * 1024:
                            error_message = f"Attachments too large. Total size: {total_size / (1024 * 1024):.2f}MB, limit: 25MB"
                            logger.error(error_message)
                            raise GmailError(
                                ErrorType.ATTACHMENT_TOO_LARGE, error_message
                            )

                        with open(file_path, "rb") as attachment:
                            part = MIMEBase("application", "octet-stream")
                            part.set_payload(attachment.read())
                            encoders.encode_base64(part)
                            part.add_header(
                                "Content-Disposition",
                                f"attachment; filename= {os.path.basename(file_path)}",
                            )
                            message.attach(part)

            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

        except Exception as e:
            error_message = f"Failed to create email message: {str(e)}"
            logger.error(error_message)
            raise GmailError(ErrorType.UNKNOWN_ERROR, error_message, e)

        url = f"{self.base_url}/users/me/messages/send"
        data = {"raw": raw_message}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, headers=self.get_headers(), json=data)

                if response.status_code == 200:
                    logger.info(f"Message sent successfully to {to_email}!")
                    return response.json()
                else:
                    error_type = self.analyze_error_response(response, "send_email")
                    error_message = f"Failed to send message to {to_email}: {response.status_code} - {response.text}"
                    logger.error(error_message)
                    raise GmailError(error_type, error_message, response)

        except httpx.RequestError as e:
            error_message = f"Network error while sending email: {str(e)}"
            logger.error(error_message)
            raise GmailError(ErrorType.NETWORK_ERROR, error_message, e)

    async def health_check(self):
        """Check if Gmail API is accessible with detailed error info"""
        try:
            await self.ensure_valid_token()
            url = f"{self.base_url}/users/me/profile"

            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=self.get_headers())

                if response.status_code == 200:
                    logger.info("Gmail API health check: OK")
                    return {"status": "healthy", "api_accessible": True}
                else:
                    error_type = self.analyze_error_response(response)
                    logger.warning(
                        f"Gmail API health check failed: {response.status_code}"
                    )
                    return {
                        "status": "degraded",
                        "api_accessible": False,
                        "error_type": error_type.value,
                        "status_code": response.status_code,
                        "details": response.text,
                    }

        except GmailError as e:
            logger.error(f"Gmail API health check error: {e.message}")
            return {
                "status": "unhealthy",
                "api_accessible": False,
                "error_type": e.error_type.value,
                "error": e.message,
            }
        except Exception as e:
            logger.error(f"Gmail API health check unexpected error: {str(e)}")
            return {
                "status": "unhealthy",
                "api_accessible": False,
                "error_type": ErrorType.UNKNOWN_ERROR.value,
                "error": str(e),
            }
