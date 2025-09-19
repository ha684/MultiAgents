import httpx
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import base64
import os
from src.utils.logger_conf import logger


class GmailAPI:
    def __init__(self, client_id, client_secret, refresh_token):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.access_token = None
        self.token_expires_at = None
        self.base_url = "https://gmail.googleapis.com/gmail/v1"

    async def get_access_token(self):
        """Get a new access token using refresh token"""
        url = "https://oauth2.googleapis.com/token"
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
        }

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
                logger.error(f"Error getting access token: {response.status_code}")
                logger.error(response.text)
                return None

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
        """Send an email message"""
        await self.ensure_valid_token()

        message = MIMEMultipart()
        message["to"] = to_email
        message["subject"] = subject

        message.attach(MIMEText(body, "plain"))

        if attachments:
            for file_path in attachments:
                if os.path.exists(file_path):
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

        url = f"{self.base_url}/users/me/messages/send"
        data = {"raw": raw_message}

        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=self.get_headers(), json=data)

            if response.status_code == 200:
                logger.info(f"Message sent successfully to {to_email}!")
                return response.json()
            else:
                logger.error(
                    f"Error sending message to {to_email}: {response.status_code}"
                )
                logger.error(response.text)
                return None

    async def health_check(self):
        """Check if Gmail API is accessible"""
        try:
            await self.ensure_valid_token()
            url = f"{self.base_url}/users/me/profile"
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=self.get_headers())

                if response.status_code == 200:
                    logger.info("Gmail API health check: OK")
                    return {"status": "healthy", "api_accessible": True}
                else:
                    logger.warning(
                        f"Gmail API health check failed: {response.status_code}"
                    )
                    return {
                        "status": "degraded",
                        "api_accessible": False,
                        "error": response.status_code,
                    }
        except Exception as e:
            logger.error(f"Gmail API health check error: {str(e)}")
            return {"status": "unhealthy", "api_accessible": False, "error": str(e)}
