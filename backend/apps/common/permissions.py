"""DRF permission helpers for org-scoped RBAC."""
from __future__ import annotations

from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsOrgMember(BasePermission):
    """User must belong to the object's organization."""

    def has_object_permission(self, request, view, obj):
        org = getattr(obj, "organization", obj)
        user = request.user
        if not user.is_authenticated:
            return False
        return user.memberships.filter(organization=org).exists()


class IsOrgAdminOrReadOnly(BasePermission):
    """Read for any org member; write only for owner/admin."""

    WRITE_ROLES = {"owner", "admin"}

    def has_object_permission(self, request, view, obj):
        org = getattr(obj, "organization", obj)
        user = request.user
        if not user.is_authenticated:
            return False
        membership = user.memberships.filter(organization=org).first()
        if not membership:
            return False
        if request.method in SAFE_METHODS:
            return True
        return membership.role in self.WRITE_ROLES
