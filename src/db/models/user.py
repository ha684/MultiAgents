# src/db/models/user.py
from sqlalchemy import (
    Column,
    String,
    DateTime,
    Boolean,
    Text,
    Enum,
    Integer,
    ForeignKey,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from src.connector.database_conn import Base
from datetime import datetime, timezone
from uuid_extensions import uuid7
import enum


class UserRole(enum.Enum):
    ADMIN = "admin"
    USER = "user"
    MODERATOR = "moderator"


class UserStatus(enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING_VERIFICATION = "pending_verification"


class User(Base):
    """User model for authentication and authorization"""

    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(50), nullable=False)
    full_name = Column(String(100), nullable=True)
    hashed_password = Column(String(255), nullable=False)

    # Role and permissions
    role = Column(Enum(UserRole), default=UserRole.USER, nullable=False)
    status = Column(
        Enum(UserStatus), default=UserStatus.PENDING_VERIFICATION, nullable=False
    )

    # Timestamps
    created_at = Column(
        DateTime(timezone=True), default=datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=datetime.now(timezone.utc),
        onupdate=datetime.now(timezone.utc),
        nullable=False,
    )
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    # Account verification
    email_verified = Column(Boolean, default=False, nullable=False)
    email_verification_token = Column(String(255), nullable=True)
    email_verification_expires = Column(DateTime(timezone=True), nullable=True)

    # Password reset
    password_reset_token = Column(String(255), nullable=True)
    password_reset_expires = Column(DateTime(timezone=True), nullable=True)

    # OAuth integration
    google_id = Column(String(100), nullable=True, unique=True)
    github_id = Column(String(100), nullable=True, unique=True)

    # Security
    failed_login_attempts = Column(Integer, default=0)
    account_locked_until = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    refresh_tokens = relationship(
        "RefreshToken", back_populates="user", cascade="all, delete-orphan"
    )
    user_sessions = relationship(
        "UserSession", back_populates="user", cascade="all, delete-orphan"
    )
    user_permissions = relationship(
        "UserPermission", back_populates="user", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_user_email_status", "email", "status"),
        Index("idx_user_role_status", "role", "status"),
        Index("idx_user_last_login", "last_login_at"),
        Index("idx_user_oauth_google", "google_id"),
        Index("idx_user_oauth_github", "github_id"),
    )

    def __repr__(self):
        return f"<User(id={self.id}, email={self.email}, role={self.role.value})>"


class RefreshToken(Base):
    """Refresh token model for JWT token management"""

    __tablename__ = "refresh_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7, index=True)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash = Column(String(255), nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(
        DateTime(timezone=True), default=datetime.now(timezone.utc), nullable=False
    )
    is_revoked = Column(Boolean, default=False, nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", back_populates="refresh_tokens")

    __table_args__ = (
        Index("idx_refresh_token_user", "user_id", "is_revoked"),
        Index("idx_refresh_token_expires", "expires_at"),
        Index("idx_refresh_token_hash", "token_hash"),
    )

    def __repr__(self):
        return f"<RefreshToken(id={self.id}, user_id={self.user_id}, expires_at={self.expires_at})>"


class UserSession(Base):
    """User session tracking"""

    __tablename__ = "user_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7, index=True)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id = Column(String(255), nullable=False, unique=True, index=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=datetime.now(timezone.utc), nullable=False
    )
    last_activity = Column(
        DateTime(timezone=True), default=datetime.now(timezone.utc), nullable=False
    )
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    # Relationships
    user = relationship("User", back_populates="user_sessions")

    __table_args__ = (
        Index("idx_session_user_active", "user_id", "is_active"),
        Index("idx_session_expires", "expires_at"),
        Index("idx_session_activity", "last_activity"),
    )


class Permission(Base):
    """Permission model for fine-grained access control"""

    __tablename__ = "permissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    resource = Column(
        String(50), nullable=False
    )  # e.g., 'document', 'chat', 'knowledge_base'
    action = Column(
        String(50), nullable=False
    )  # e.g., 'read', 'write', 'delete', 'manage'
    created_at = Column(
        DateTime(timezone=True), default=datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    user_permissions = relationship(
        "UserPermission", back_populates="permission", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("idx_permission_resource_action", "resource", "action"),)

    def __repr__(self):
        return f"<Permission(name={self.name}, resource={self.resource}, action={self.action})>"


class UserPermission(Base):
    """User-specific permissions (many-to-many relationship)"""

    __tablename__ = "user_permissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7, index=True)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    permission_id = Column(
        UUID(as_uuid=True),
        ForeignKey("permissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    granted_by = Column(
        UUID(as_uuid=True), nullable=True
    )  # Who granted this permission
    granted_at = Column(
        DateTime(timezone=True), default=datetime.now(timezone.utc), nullable=False
    )
    expires_at = Column(DateTime(timezone=True), nullable=True)  # Optional expiration

    # Resource-specific permissions (for multi-layer access control)
    resource_id = Column(
        String(255), nullable=True
    )  # Specific resource ID (e.g., document ID)

    # Relationships
    user = relationship("User", back_populates="user_permissions")
    permission = relationship("Permission", back_populates="user_permissions")

    __table_args__ = (
        Index("idx_user_permission_lookup", "user_id", "permission_id"),
        Index("idx_user_permission_expires", "expires_at"),
        Index("idx_user_permission_resource", "resource_id"),
    )

    def __repr__(self):
        return f"<UserPermission(user_id={self.user_id}, permission_id={self.permission_id})>"


class LoginAttempt(Base):
    """Login attempt tracking for security"""

    __tablename__ = "login_attempts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7, index=True)
    email = Column(String(255), nullable=False, index=True)
    success = Column(Boolean, nullable=False)
    failure_reason = Column(String(100), nullable=True)
    attempted_at = Column(
        DateTime(timezone=True), default=datetime.now(timezone.utc), nullable=False
    )

    __table_args__ = (
        Index("idx_login_attempt_email_time", "email", "attempted_at"),
        Index("idx_login_attempt_success", "success", "attempted_at"),
    )

    def __repr__(self):
        return f"<LoginAttempt(email={self.email}, success={self.success}, attempted_at={self.attempted_at})>"
