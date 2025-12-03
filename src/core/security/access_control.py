# src/core/security/access_control.py

from src.core.config.settings import ROLE_PERMISSIONS
from src.database.models.user import UserRole


class AccessControlManager:
    """Multi-layer access control manager"""

    @staticmethod
    def has_role_permission(user_role: UserRole, required_permission: str) -> bool:
        """Check if a role has a specific permission"""
        role_perms = ROLE_PERMISSIONS.get(user_role.value, [])
        return required_permission in role_perms

    @staticmethod
    def has_resource_access(
        user_permissions: list,
        resource: str,
        action: str,
        resource_id: str | None = None,
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
