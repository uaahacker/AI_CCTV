from rest_framework import permissions, serializers, viewsets
from rest_framework.routers import DefaultRouter

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = AuditLog
        fields = (
            "id",
            "created_at",
            "user",
            "user_email",
            "organization",
            "action",
            "ip_address",
            "user_agent",
            "metadata",
        )
        read_only_fields = fields


class IsOrgAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AuditLogSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Visible to any member of the org; admins see superset via Django admin.
        return AuditLog.objects.filter(
            organization__memberships__user=self.request.user,
            organization__memberships__role__in=["owner", "admin"],
        ).distinct()


router = DefaultRouter()
router.register(r"logs", AuditLogViewSet, basename="audit-log")
