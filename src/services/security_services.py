# src/utils/security.py
import secrets
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Optional
from passlib.context import CryptContext
from src.config.auth_settings import auth_settings
from src.models.auth import TokenData, UserRole
import hashlib
import hmac
import jwt

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class SecurityManager:
    """Centralized security operations manager"""

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password using bcrypt"""
        return pwd_context.hash(password)

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash"""
        return pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    def generate_secure_token(length: int = 32) -> str:
        """Generate a cryptographically secure random token"""
        return secrets.token_urlsafe(length)

    @staticmethod
    def generate_session_id() -> str:
        """Generate a unique session ID"""
        return str(uuid.uuid4())

    @staticmethod
    def hash_token(token: str) -> str:
        """Hash a token for secure storage"""
        return hashlib.sha256(token.encode()).hexdigest()

    @staticmethod
    def verify_token_hash(token: str, token_hash: str) -> bool:
        """Verify a token against its hash"""
        return hmac.compare_digest(SecurityManager.hash_token(token), token_hash)


class JWTManager:
    """JWT token management"""

    def __init__(self):
        self.secret_key = auth_settings.jwt_secret_key
        self.algorithm = auth_settings.jwt_algorithm
        self.issuer = auth_settings.jwt_issuer

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
            expire = now + timedelta(
                minutes=auth_settings.jwt_access_token_expire_minutes
            )

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

    def create_refresh_token(self) -> str:
        """Create a refresh token (just a secure random string)"""
        return SecurityManager.generate_secure_token(64)

    def verify_token(self, token: str) -> Optional[TokenData]:
        """Verify and decode a JWT token"""
        try:
            payload = jwt.decode(
                token, self.secret_key, algorithms=[self.algorithm], issuer=self.issuer
            )

            # Validate required fields
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


class TokenManager:
    """Manage various types of tokens (verification, reset, etc.)"""

    @staticmethod
    def create_verification_token() -> tuple[str, datetime]:
        """Create an verification token with expiry"""
        token = f"{int(secrets.token_hex(4), 16) % 900000 + 100000}"
        expires_at = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")) + timedelta(
            minutes=auth_settings.email_verification_token_expire_minutes
        )
        return token, expires_at

    @staticmethod
    def is_token_expired(expires_at: datetime) -> bool:
        """Check if a token has expired"""
        return datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")) > expires_at


class AccessControlManager:
    """Multi-layer access control manager"""

    @staticmethod
    def has_role_permission(user_role: UserRole, required_permission: str) -> bool:
        """Check if a role has a specific permission"""
        from src.config.auth_settings import ROLE_PERMISSIONS

        role_perms = ROLE_PERMISSIONS.get(user_role.value, [])
        return required_permission in role_perms

    @staticmethod
    def has_resource_access(
        user_permissions: list,
        resource: str,
        action: str,
        resource_id: Optional[str] = None,
    ) -> bool:
        """Check if user has access to a specific resource"""
        # Check for general resource permission
        general_permission = f"{resource}:{action}"
        if general_permission in user_permissions:
            return True

        # Check for resource-specific permission if resource_id provided
        if resource_id:
            specific_permission = f"{resource}:{action}:{resource_id}"
            if specific_permission in user_permissions:
                return True

        return False

    @staticmethod
    def can_access_user_data(
        current_user_id: str, target_user_id: str, user_role: UserRole
    ) -> bool:
        """Check if user can access another user's data"""
        # Users can always access their own data
        if current_user_id == target_user_id:
            return True

        # Admins can access any user's data
        if user_role == UserRole.ADMIN:
            return True

        # Moderators can access regular users' data but not other moderators or admins
        if user_role == UserRole.MODERATOR:
            raise NotImplementedError("Moderator access is not implemented")
            return True

        return False

    @staticmethod
    def get_accessible_resources(
        user_id: str, user_role: UserRole, resource_type: str
    ) -> list:
        """Get list of resource IDs that user can access"""
        # This is a placeholder - in real implementation, you'd query the database
        # for resources owned by or shared with the user
        if user_role == UserRole.ADMIN:
            return ["*"]  # Admin can access all resources

        # Return user's own resources and shared resources
        return [f"user_{user_id}_*"]


# Create global instances
security_manager = SecurityManager()
jwt_manager = JWTManager()
token_manager = TokenManager()
access_control = AccessControlManager()
