from datetime import timedelta

from django.db.models import Avg, Max, Sum
from django.db.models.functions import TruncDate, TruncHour
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions, viewsets
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter
from rest_framework.views import APIView

from .models import DetectionEvent
from .serializers import DetectionEventSerializer


class DetectionEventViewSet(viewsets.ModelViewSet):
    serializer_class = DetectionEventSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["organization", "camera", "event_type"]

    def get_queryset(self):
        return DetectionEvent.objects.filter(
            organization__memberships__user=self.request.user
        ).distinct()


class ReportsView(APIView):
    """Aggregate reports for dashboard charts. Query params: ?days=7&camera=<uuid>"""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        days = int(request.query_params.get("days", "7") or 7)
        camera_id = request.query_params.get("camera")
        since = timezone.now() - timedelta(days=days)

        qs = DetectionEvent.objects.filter(
            organization__memberships__user=request.user,
            created_at__gte=since,
        )
        if camera_id:
            qs = qs.filter(camera_id=camera_id)

        daily = (
            qs.annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(total=Sum("people_count"), peak=Max("people_count"))
            .order_by("day")
        )
        hourly = (
            qs.annotate(hour=TruncHour("created_at"))
            .values("hour")
            .annotate(total=Sum("people_count"), avg=Avg("people_count"))
            .order_by("hour")
        )
        per_camera = (
            qs.values("camera", "camera__name")
            .annotate(total=Sum("people_count"), peak=Max("people_count"))
            .order_by("-total")
        )

        return Response(
            {
                "range_days": days,
                "daily": list(daily),
                "hourly": list(hourly),
                "per_camera": list(per_camera),
            }
        )


router = DefaultRouter()
router.register(r"events", DetectionEventViewSet, basename="detection-event")

from django.urls import path  # noqa: E402


class ReportsAISummaryView(APIView):
    """
    Generate (or regenerate) an LLM summary of the same aggregate report.

    Uses the organization's active AI provider. If no provider is configured,
    returns a deterministic fallback string — never errors.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from apps.ai.services import AIProviderFactory
        from apps.organizations.models import Organization

        # Build the same payload the GET endpoint returns.
        report = ReportsView().get(request).data

        # Pick the org for AI routing — prefer ?organization=, else first membership.
        org_id = request.query_params.get("organization")
        if org_id:
            org = Organization.objects.filter(
                id=org_id, memberships__user=request.user
            ).first()
        else:
            org = Organization.objects.filter(memberships__user=request.user).first()

        if not org:
            return Response({"summary": "", "detail": "No organization."}, status=400)

        provider = AIProviderFactory.for_organization(org)
        summary = provider.generate_daily_report_summary(report)
        return Response({"summary": summary, "provider": provider.__class__.__name__})


extra_urls = [
    path("reports/", ReportsView.as_view(), name="reports"),
    path("reports/ai-summary/", ReportsAISummaryView.as_view(), name="reports-ai-summary"),
]
