import csv

from django.http import HttpResponse
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, permissions, serializers, viewsets
from rest_framework.decorators import action
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


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """List + retrieve audit events for an organisation.

    Visible to owners/admins only. Supports filtering by action, user and
    date range, plus a CSV export at ``/api/audit/logs/export/``.
    """
    serializer_class = AuditLogSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["organization", "action", "user"]
    search_fields = ["action", "user__email"]
    ordering_fields = ["created_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = AuditLog.objects.filter(
            organization__memberships__user=self.request.user,
            organization__memberships__role__in=["owner", "admin"],
        ).select_related("user", "organization").distinct()
        params = self.request.query_params
        if params.get("date_from"):
            qs = qs.filter(created_at__gte=params["date_from"])
        if params.get("date_to"):
            qs = qs.filter(created_at__lte=params["date_to"])
        return qs

    @action(detail=False, methods=["get"], url_path="export")
    def export_csv(self, request):
        """Stream a CSV of (up to 10k) filtered audit rows."""
        qs = self.filter_queryset(self.get_queryset())[:10000]
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="audit-log.csv"'
        writer = csv.writer(response)
        writer.writerow(["timestamp", "user", "organization", "action", "ip", "metadata"])
        for row in qs:
            writer.writerow([
                row.created_at.isoformat(),
                row.user.email if row.user_id else "",
                row.organization.name if row.organization_id else "",
                row.action,
                row.ip_address or "",
                row.metadata or {},
            ])
        return response


router = DefaultRouter()
router.register(r"logs", AuditLogViewSet, basename="audit-log")
