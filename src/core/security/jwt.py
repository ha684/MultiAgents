# src/core/security/jwt.py
from datetime import datetime, timedelta
from typing import Optional
import uuid
from zoneinfo import ZoneInfo

import jwt

from src.core.config.settings import settings
from src.database.models.user import UserRole
from src.domain.schemas.auth import TokenData


class JWTManager:
    """JWT token management"""

    def __init__(self):
        self.secret_key = settings.jwt_secret_key
        self.algorithm = settings.jwt_algorithm
        self.issuer = settings.jwt_issuer

    def create_access_token(
        self,
        user_id: str,
        email: str,
        role: UserRole,
        session_id: str,
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        """Create a JWT access token"""
        now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))

        if expires_delta:
            expire = now + expires_delta
        else:
            expire = now + timedelta(minutes=settings.jwt_access_token_expire_minutes)

        to_encode = {
            "user_id": user_id,
            "email": email,
            "role": role.value,
            "session_id": session_id,
            "exp": int(expire.timestamp()),
            "iat": int(now.timestamp()),
            "iss": self.issuer,
            "jti": str(uuid.uuid4()),
        }

        return jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)

    def verify_token(self, token: str) -> Optional[TokenData]:
        """Verify and decode a JWT token"""
        try:
            payload = jwt.decode(
                token, self.secret_key, algorithms=[self.algorithm], issuer=self.issuer
            )

            required_fields = [
                "user_id",
                "email",
                "role",
                "session_id",
                "exp",
                "iat",
                "jti",
            ]
            for field in required_fields:
                if field not in payload:
                    return None

            return TokenData(
                user_id=payload["user_id"],
                email=payload["email"],
                role=UserRole(payload["role"]),
                session_id=payload["session_id"],
                exp=payload["exp"],
                iat=payload["iat"],
                jti=payload["jti"],
            )
        except Exception:
            return None

    def get_token_expiry(self, token: str) -> Optional[datetime]:
        """Get the expiry time of a token without full validation"""
        try:
            payload = jwt.decode(
                token, options={"verify_signature": False, "verify_exp": False}
            )
            exp_timestamp = payload.get("exp")
            if exp_timestamp:
                return datetime.fromtimestamp(
                    exp_timestamp, tz=ZoneInfo("Asia/Ho_Chi_Minh")
                )
            return None
        except Exception:
            return None
