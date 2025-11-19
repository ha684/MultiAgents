"""
Unit tests for authentication endpoints.
"""

from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.database.models.user import UserRole, UserStatus


@pytest.mark.unit
@pytest.mark.auth
class TestAuthEndpoints:
    """Test authentication endpoints."""

    @pytest.mark.asyncio
    async def test_register_success(self, async_client):
        """Test successful user registration."""
        with patch(
            "src.api.auth.auth_service.register_user", new_callable=AsyncMock
        ) as mock_register:
            mock_user = MagicMock()
            mock_user.model_dump.return_value = {
                "id": "test-user-id",
                "email": "newuser@example.com",
                "username": "newuser",
                "role": "user",
            }
            mock_register.return_value = mock_user

            response = await async_client.post(
                "/auth/register",
                json={
                    "email": "newuser@example.com",
                    "username": "newuser",
                    "password": "SecurePassword123!",
                    "full_name": "New User",
                },
            )

            assert response.status_code == 200
            assert mock_register.await_count == 1
            mock_register.assert_awaited()

            mock_register.assert_awaited_once_with(ANY)
            data = response.json()
            assert "data" in data
            assert (
                data["message"]
                == "User registered successfully. Please check your email for verification."
            )

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, async_client):
        """Test registration with duplicate email."""
        with patch("src.api.auth.auth_service.register_user") as mock_register:
            mock_register.side_effect = HTTPException(
                status_code=400, detail="Email already registered"
            )

            response = await async_client.post(
                "/auth/register",
                json={
                    "email": "existing@example.com",
                    "username": "newuser",
                    "password": "SecurePassword123!",
                    "full_name": "New User",
                },
            )

            assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_login_success(self, async_client):
        """Test successful login."""
        with patch("src.api.auth.auth_service.authenticate_user") as mock_auth:
            mock_user = MagicMock()
            mock_user.id = "test-user-id"
            mock_user.email = "test@example.com"
            mock_user.username = "testuser"
            mock_user.full_name = "Test User"
            mock_user.avatar_url = None
            mock_user.auth_provider = "local"

            mock_token = MagicMock()
            mock_token.model_dump.return_value = {
                "access_token": "test-access-token",
                "refresh_token": "test-refresh-token",
                "token_type": "bearer",
            }

            mock_auth.return_value = (mock_user, mock_token)

            response = await async_client.post(
                "/auth/login",
                json={
                    "email": "test@example.com",
                    "password": "TestPassword123!",
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert "data" in data
            assert "user" in data
            assert data["message"] == "Login successful"
            assert data["user"]["email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_login_invalid_credentials(self, async_client):
        """Test login with invalid credentials."""
        with patch("src.api.auth.auth_service.authenticate_user") as mock_auth:
            mock_auth.side_effect = HTTPException(
                status_code=401, detail="Invalid credentials"
            )

            response = await async_client.post(
                "/auth/login",
                json={
                    "email": "test@example.com",
                    "password": "WrongPassword",
                },
            )

            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_token_success(self, async_client):
        """Test successful token refresh."""
        with patch("src.api.auth.auth_service.refresh_access_token") as mock_refresh:
            mock_token = MagicMock()
            mock_token.model_dump.return_value = {
                "access_token": "new-access-token",
                "refresh_token": "new-refresh-token",
                "token_type": "bearer",
            }
            mock_refresh.return_value = mock_token

            response = await async_client.post(
                "/auth/refresh",
                json={"refresh_token": "valid-refresh-token"},
            )

            assert response.status_code == 200
            data = response.json()
            assert "data" in data
            assert data["message"] == "Token refreshed successfully"

    @pytest.mark.asyncio
    async def test_refresh_token_invalid(self, async_client):
        """Test token refresh with invalid token."""
        with patch("src.api.auth.auth_service.refresh_access_token") as mock_refresh:
            mock_refresh.side_effect = HTTPException(
                status_code=401, detail="Invalid refresh token"
            )

            response = await async_client.post(
                "/auth/refresh",
                json={"refresh_token": "invalid-token"},
            )

            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_logout_success(self, async_client):
        """Test successful logout."""
        with patch("src.api.auth.auth_service.logout_user") as mock_logout:
            mock_logout.return_value = True

            response = await async_client.post(
                "/auth/logout",
                json={"refresh_token": "valid-refresh-token"},
            )

            assert response.status_code == 200
            assert "Logout successful" in response.text

    @pytest.mark.asyncio
    async def test_get_me_success(self, async_client, test_user, auth_headers):
        """Test getting current user profile."""
        with patch("src.dependencies.auth.get_current_user") as mock_get_user:
            mock_get_user.return_value = test_user

            response = await async_client.get(
                "/auth/me",
                headers=auth_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert data["email"] == test_user.email
            assert data["username"] == test_user.username

    @pytest.mark.asyncio
    async def test_get_me_unauthorized(self, async_client):
        """Test getting profile without authentication."""
        response = await async_client.get("/auth/me")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_update_profile_success(self, async_client, test_user, auth_headers):
        """Test updating user profile."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_get_user,
            patch("src.api.auth.auth_service.update_user") as mock_update,
        ):
            mock_get_user.return_value = test_user

            updated_user = MagicMock()
            updated_user.id = test_user.id
            updated_user.email = test_user.email
            updated_user.username = "newusername"
            updated_user.full_name = "Updated Name"
            updated_user.role = test_user.role
            updated_user.status = test_user.status
            updated_user.email_verified = test_user.email_verified
            updated_user.created_at = test_user.created_at
            updated_user.last_login_at = test_user.last_login_at

            mock_update.return_value = updated_user

            response = await async_client.put(
                "/auth/profile",
                headers=auth_headers,
                json={
                    "full_name": "Updated Name",
                    "username": "newusername",
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["full_name"] == "Updated Name"
            assert data["username"] == "newusername"

    @pytest.mark.asyncio
    async def test_change_password_success(self, async_client, test_user, auth_headers):
        """Test changing password."""
        with (
            patch("src.dependencies.auth.get_current_user") as mock_get_user,
            patch("src.api.auth.auth_service.change_password") as mock_change,
        ):
            mock_get_user.return_value = test_user
            mock_change.return_value = True

            response = await async_client.post(
                "/auth/password/change",
                headers=auth_headers,
                json={
                    "current_password": "OldPassword123!",
                    "new_password": "NewPassword123!",
                },
            )

            assert response.status_code == 200
            assert "Password changed successfully" in response.text

    @pytest.mark.asyncio
    async def test_request_password_reset(self, async_client):
        """Test requesting password reset."""
        with patch("src.api.auth.auth_service.request_password_reset") as mock_reset:
            mock_reset.return_value = None

            response = await async_client.post(
                "/auth/password/reset",
                json={"email": "test@example.com"},
            )

            assert response.status_code == 200
            assert "password reset link" in response.text.lower()

    @pytest.mark.asyncio
    async def test_verify_email_success(self, async_client):
        """Test email verification."""
        with patch("src.api.auth.auth_service.verify_email") as mock_verify:
            mock_user = MagicMock()
            mock_user.model_dump.return_value = {
                "id": "test-user-id",
                "email": "test@example.com",
                "email_verified": True,
            }
            mock_verify.return_value = mock_user

            response = await async_client.post(
                "/auth/email/verify",
                json={"token": "valid-verification-token"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["email_verified"] is True

    @pytest.mark.asyncio
    async def test_list_users_admin_only(self, async_client, admin_auth_headers):
        """Test listing users (admin only)."""
        with (
            patch("src.dependencies.auth.require_admin"),
            patch("src.api.auth.auth_service.get_users") as mock_get_users,
        ):
            mock_users = [
                MagicMock(
                    id="user1",
                    email="user1@example.com",
                    username="user1",
                    full_name="User One",
                    role=UserRole.USER,
                    status=UserStatus.ACTIVE,
                    email_verified=True,
                    created_at=None,
                    last_login_at=None,
                )
            ]
            mock_get_users.return_value = mock_users

            response = await async_client.get(
                "/auth/users?page=1&size=10",
                headers=admin_auth_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_validate_token_success(self, async_client, test_user, auth_headers):
        """Test token validation."""
        with patch("src.dependencies.auth.get_current_user") as mock_get_user:
            mock_get_user.return_value = test_user

            response = await async_client.get(
                "/auth/validate",
                headers=auth_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert "data" in data
            assert data["message"] == "Token is valid"
            assert data["data"]["user_id"] == str(test_user.id)
