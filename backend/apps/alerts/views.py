from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions, viewsets
from rest_framework.routers import DefaultRouter

from apps.audit.utils import log_action

from .models import Alert, AlertRule
from .serializers import AlertRuleSerializer, AlertSerializer


class AlertRuleViewSet(viewsets.ModelViewSet):
    serializer_class = AlertRuleSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["organization", "camera", "rule_type", "is_active"]

    def get_queryset(self):
        return AlertRule.objects.filter(
            organization__memberships__user=self.request.user
        ).distinct()

    def perform_create(self, serializer):
        rule = serializer.save()
        log_action(
            user=self.request.user,
            action="alert_rule.create",
            request=self.request,
            organization=rule.organization,
            metadata={"rule_id": str(rule.id), "name": rule.name},
        )

    def perform_update(self, serializer):
        rule = serializer.save()
        log_action(
            user=self.request.user,
            action="alert_rule.update",
            request=self.request,
            organization=rule.organization,
            metadata={"rule_id": str(rule.id)},
        )


class AlertViewSet(viewsets.ModelViewSet):
    serializer_class = AlertSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["organization", "camera", "severity", "status"]
    http_method_names = ["get", "patch", "head", "options"]  # read + acknowledge/resolve

    def get_queryset(self):
        return Alert.objects.filter(
            organization__memberships__user=self.request.user
        ).distinct()


router = DefaultRouter()
router.register(r"rules", AlertRuleViewSet, basename="alert-rule")
router.register(r"", AlertViewSet, basename="alert")
