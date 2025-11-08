"""
Integration tests for authentication flows.
"""

import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.integration
@pytest.mark.auth
@pytest.mark.requires_db
@pytest.mark.requires_redis
class TestAuthenticationFlow:
    """Test complete authentication workflows."""

    @pytest.mark.asyncio
    async def test_complete_registration_and_login_flow(self, async_client):
        """Test user registration followed by login."""
        with (
            patch("src.api.auth.auth_service.register_user") as mock_register,
            patch("src.api.auth.auth_service.authenticate_user") as mock_login,
        ):
            # Mock registration
            mock_user = MagicMock()
            mock_user.model_dump.return_value = {
                "id": "test-user-id",
                "email": "integration@example.com",
                "username": "integrationuser",
                "role": "user",
            }
            mock_register.return_value = mock_user

            # Step 1: Register
            register_response = await async_client.post(
                "/auth/register",
                json={
                    "email": "integration@example.com",
                    "username": "integrationuser",
                    "password": "SecurePass123!",
                    "full_name": "Integration User",
                },
            )

            assert register_response.status_code == 200

            # Mock login
            login_user = MagicMock()
            login_user.id = "test-user-id"
            login_user.email = "integration@example.com"
            login_user.username = "integrationuser"
            login_user.full_name = "Integration User"
            login_user.avatar_url = None
            login_user.auth_provider = "local"

            mock_token = MagicMock()
            mock_token.model_dump.return_value = {
                "access_token": "test-access-token",
                "refresh_token": "test-refresh-token",
                "token_type": "bearer",
            }

            mock_login.return_value = (login_user, mock_token)

            # Step 2: Login
            login_response = await async_client.post(
                "/auth/login",
                json={
                    "email": "integration@example.com",
                    "password": "SecurePass123!",
                },
            )

            assert login_response.status_code == 200
            login_data = login_response.json()
            assert "data" in login_data
            assert "access_token" in login_data["data"]

    @pytest.mark.asyncio
    async def test_login_profile_update_flow(self, async_client):
        """Test login, get profile, and update profile flow."""
        with (
            patch("src.api.auth.auth_service.authenticate_user") as mock_login,
            patch("src.dependencies.auth.get_current_user") as mock_get_user,
            patch("src.api.auth.auth_service.update_user") as mock_update,
        ):
            # Mock login
            user = MagicMock()
            user.id = "test-user-id"
            user.email = "test@example.com"
            user.username = "testuser"
            user.full_name = "Test User"
            user.avatar_url = None
            user.auth_provider = "local"
            user.role = MagicMock(value="user")
            user.status = MagicMock(value="active")
            user.email_verified = True
            user.created_at = None
            user.last_login_at = None

            mock_token = MagicMock()
            mock_token.model_dump.return_value = {
                "access_token": "test-token",
                "refresh_token": "refresh-token",
                "token_type": "bearer",
            }

            mock_login.return_value = (user, mock_token)
            mock_get_user.return_value = user

            # Step 1: Login
            login_response = await async_client.post(
                "/auth/login",
                json={
                    "email": "test@example.com",
                    "password": "TestPass123!",
                },
            )

            assert login_response.status_code == 200
            token = login_response.json()["data"]["access_token"]

            headers = {"Authorization": f"Bearer {token}"}

            # Step 2: Get profile
            profile_response = await async_client.get(
                "/auth/me",
                headers=headers,
            )

            assert profile_response.status_code == 200

            # Step 3: Update profile
            updated_user = MagicMock()
            updated_user.id = user.id
            updated_user.email = user.email
            updated_user.username = "updateduser"
            updated_user.full_name = "Updated User"
            updated_user.role = user.role
            updated_user.status = user.status
            updated_user.email_verified = user.email_verified
            updated_user.created_at = user.created_at
            updated_user.last_login_at = user.last_login_at

            mock_update.return_value = updated_user

            update_response = await async_client.put(
                "/auth/profile",
                headers=headers,
                json={
                    "full_name": "Updated User",
                    "username": "updateduser",
                },
            )

            assert update_response.status_code == 200
            assert update_response.json()["full_name"] == "Updated User"

    @pytest.mark.asyncio
    async def test_token_refresh_flow(self, async_client):
        """Test token refresh workflow."""
        with (
            patch("src.api.auth.auth_service.authenticate_user") as mock_login,
            patch("src.api.auth.auth_service.refresh_access_token") as mock_refresh,
        ):
            # Mock login
            user = MagicMock()
            user.id = "test-user-id"
            user.email = "test@example.com"
            user.username = "testuser"
            user.full_name = "Test User"
            user.avatar_url = None
            user.auth_provider = "local"

            mock_token = MagicMock()
            mock_token.model_dump.return_value = {
                "access_token": "original-token",
                "refresh_token": "refresh-token",
                "token_type": "bearer",
            }

            mock_login.return_value = (user, mock_token)

            # Step 1: Login
            login_response = await async_client.post(
                "/auth/login",
                json={
                    "email": "test@example.com",
                    "password": "TestPass123!",
                },
            )

            assert login_response.status_code == 200
            refresh_token = login_response.json()["data"]["refresh_token"]

            # Step 2: Refresh token
            new_mock_token = MagicMock()
            new_mock_token.model_dump.return_value = {
                "access_token": "new-token",
                "refresh_token": "new-refresh-token",
                "token_type": "bearer",
            }
            mock_refresh.return_value = new_mock_token

            refresh_response = await async_client.post(
                "/auth/refresh",
                json={"refresh_token": refresh_token},
            )

            assert refresh_response.status_code == 200
            new_token_data = refresh_response.json()
            assert new_token_data["data"]["access_token"] == "new-token"

    @pytest.mark.asyncio
    async def test_password_reset_flow(self, async_client):
        """Test complete password reset workflow."""
        with (
            patch("src.api.auth.auth_service.request_password_reset") as mock_request,
            patch("src.api.auth.auth_service.reset_password") as mock_reset,
        ):
            mock_request.return_value = None

            # Step 1: Request password reset
            request_response = await async_client.post(
                "/auth/password/reset",
                json={"email": "test@example.com"},
            )

            assert request_response.status_code == 200

            # Step 2: Confirm password reset with token
            mock_reset.return_value = True

            reset_response = await async_client.post(
                "/auth/password/reset/confirm",
                json={
                    "token": "reset-token",
                    "new_password": "NewSecurePass123!",
                },
            )

            assert reset_response.status_code == 200

    @pytest.mark.asyncio
    async def test_logout_all_sessions_flow(self, async_client):
        """Test logging out from all sessions."""
        with (
            patch("src.api.auth.auth_service.authenticate_user") as mock_login,
            patch("src.dependencies.auth.get_current_user") as mock_get_user,
            patch("src.api.auth.auth_service.logout_all_sessions") as mock_logout_all,
        ):
            # Mock login
            user = MagicMock()
            user.id = "test-user-id"
            user.email = "test@example.com"
            user.username = "testuser"
            user.full_name = "Test User"
            user.avatar_url = None
            user.auth_provider = "local"

            mock_token = MagicMock()
            mock_token.model_dump.return_value = {
                "access_token": "test-token",
                "refresh_token": "refresh-token",
                "token_type": "bearer",
            }

            mock_login.return_value = (user, mock_token)
            mock_get_user.return_value = user

            # Step 1: Login
            login_response = await async_client.post(
                "/auth/login",
                json={
                    "email": "test@example.com",
                    "password": "TestPass123!",
                },
            )

            assert login_response.status_code == 200
            token = login_response.json()["data"]["access_token"]

            headers = {"Authorization": f"Bearer {token}"}

            # Step 2: Logout from all sessions
            mock_logout_all.return_value = 3  # 3 sessions revoked

            logout_response = await async_client.post(
                "/auth/logout-all",
                headers=headers,
            )

            assert logout_response.status_code == 200
            assert "3 sessions" in logout_response.text
