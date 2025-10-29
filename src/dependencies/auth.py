# src/auth/dependencies.py
import os
from datetime import datetime
from typing import List, Optional
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.core.config.settings import ROLE_PERMISSIONS
from src.core.exceptions.auth_exceptions import (
    InsufficientPermissionsException,
    InvalidTokenException,
    RoleNotAuthorizedException,
    SessionExpiredException,
    TokenNotFoundException,
    UserNotFoundException,
)
from src.core.security import AccessControlManager, JWTManager
from src.database.models.user import User, UserStatus
from src.database.repositories.user_repository import UserRepository
from src.domain.schemas.auth import AccessControlContext, TokenData, UserRole

load_dotenv()

security = HTTPBearer(
    auto_error=False,
    scheme_name="Bearer",
    description="Bearer token for authentication",
)
user_repo = UserRepository()
APP_ENV = os.getenv("APP_ENV", "production")
API_KEY = os.getenv("API_KEY", "1234567890")


async def get_current_user_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> TokenData:
    """Extract and validate JWT token from request"""
    if APP_ENV == "development" or credentials.credentials == API_KEY:
        print("--- ⚠️ DEV MODE: Bypassing token auth ---")
        return TokenData(
            user_id="hafizh",
            email="hafizh@gmail.com",
            role=UserRole.ADMIN,
            session_id="1234567890",
            exp=1730150400,
            iat=1730150400,
            jti="1234567890",
        )

    if not credentials:
        raise TokenNotFoundException()

    token_data = JWTManager.verify_token(credentials.credentials)
    if not token_data:
        raise InvalidTokenException()
    return token_data


async def get_current_user(
    token_data: TokenData = Depends(get_current_user_token),
) -> User:
    """Get current authenticated user"""
    if APP_ENV == "development":
        print("--- ⚠️ DEV MODE: Bypassing token auth ---")
        return User(
            id="hafizh",
            email="hafizh@gmail.com",
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
        )

    user = await user_repo.get_user_by_id(token_data.user_id)

    if not user:
        raise UserNotFoundException("User not found")

    if user.status != UserStatus.ACTIVE:
        raise SessionExpiredException("User account is not active")

    return user


def require_role(required_role: UserRole):
    """Dependency factory for role-based access control"""

    async def role_dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role != required_role and current_user.role != UserRole.ADMIN:
            raise RoleNotAuthorizedException(required_role.value)
        return current_user

    return role_dependency


def require_roles(required_roles: List[UserRole]):
    """Dependency factory for multiple role access control"""

    async def roles_dependency(current_user: User = Depends(get_current_user)) -> User:
        if (
            current_user.role not in required_roles
            and current_user.role != UserRole.ADMIN
        ):
            role_names = [role.value for role in required_roles]
            raise RoleNotAuthorizedException(f"one of: {', '.join(role_names)}")
        return current_user

    return roles_dependency


def require_permission(resource: str, action: str):
    """Dependency factory for permission-based access control"""

    async def permission_dependency(
        current_user: User = Depends(get_current_user),
    ) -> User:
        # Check role-based permission first
        required_permission = f"{resource}:{action}"
        if AccessControlManager.has_role_permission(
            current_user.role, required_permission
        ):
            return current_user

        # Check user-specific permissions
        user_repo = UserRepository()
        user_with_perms = await user_repo.get_user_with_permissions(
            str(current_user.id)
        )

        user_permissions = [
            f"{up.permission.resource}:{up.permission.action}"
            for up in user_with_perms.user_permissions
            if up.expires_at is None
            or up.expires_at > datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
        ]

        if not AccessControlManager.has_resource_access(
            user_permissions, resource, action
        ):
            raise InsufficientPermissionsException(
                f"Permission required: {required_permission}"
            )

        return current_user

    return permission_dependency


def require_resource_access(
    resource: str, action: str, resource_id_param: str = "resource_id"
):
    """Dependency factory for resource-specific access control"""

    async def resource_access_dependency(
        request: Request,
        current_user: User = Depends(get_current_user),
    ) -> User:
        # Get resource ID from path parameters
        resource_id = request.path_params.get(resource_id_param)

        # Check role-based permission first
        required_permission = f"{resource}:{action}"
        if AccessControlManager.has_role_permission(
            current_user.role, required_permission
        ):
            return current_user

        # Check if user can access this specific resource
        if not AccessControlManager.can_access_user_data(
            str(current_user.id), resource_id, current_user.role
        ):
            raise InsufficientPermissionsException(
                f"Access denied to {resource} {resource_id}"
            )

        return current_user

    return resource_access_dependency


# Admin-only dependencies
require_admin = require_role(UserRole.ADMIN)
require_moderator_or_admin = require_roles([UserRole.MODERATOR, UserRole.ADMIN])

# Common permission dependencies
require_user_read = require_permission("user", "read")
require_user_write = require_permission("user", "write")
require_document_read = require_permission("document", "read")
require_document_write = require_permission("document", "write")
require_chat_read = require_permission("chat", "read")
require_chat_write = require_permission("chat", "write")


# Context creation for access control
async def get_access_context(
    current_user: User = Depends(get_current_user),
) -> AccessControlContext:
    """Create access control context for complex authorization"""
    user_repo = UserRepository()
    user_with_perms = await user_repo.get_user_with_permissions(str(current_user.id))

    # Get user permissions
    permissions = []
    resource_permissions = {}

    for user_perm in user_with_perms.user_permissions:
        if user_perm.expires_at is None or user_perm.expires_at > datetime.now(
            ZoneInfo("Asia/Ho_Chi_Minh")
        ):
            perm_name = f"{user_perm.permission.resource}:{user_perm.permission.action}"
            permissions.append(perm_name)

            # Track resource-specific permissions
            if user_perm.resource_id:
                if user_perm.resource_id not in resource_permissions:
                    resource_permissions[user_perm.resource_id] = []
                resource_permissions[user_perm.resource_id].append(perm_name)

    # Add role-based permissions
    role_perms = ROLE_PERMISSIONS.get(current_user.role.value, [])
    permissions.extend(role_perms)

    return AccessControlContext(
        user_id=str(current_user.id),
        role=current_user.role,
        permissions=permissions,
        resource_permissions=resource_permissions,
    )
