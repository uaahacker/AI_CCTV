from datetime import timedelta

from django.db.models import Avg, Count, Max, Sum
from django.db.models.functions import TruncDate, TruncHour
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions, viewsets
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter
from rest_framework.views import APIView

from .models import DetectionEvent, HeatmapBucket, ParkingSlotState
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


class CountersView(APIView):
    """``GET /api/analytics/counters/?camera=<uuid>&hours=24``

    Rolling counters powering the dashboard widgets:

    - people/vehicle in/out (from ``line_crossing`` events, grouped by metadata.label)
    - loitering / abandoned_object totals
    - parking summary (free / occupied / illegal — current state, not windowed)
    """

    permission_classes = [permissions.IsAuthenticated]

    # Which YOLO labels count as a "vehicle" for line-crossing counters.
    VEHICLE_LABELS = {"car", "truck", "bus", "motorcycle", "motorbike", "vehicle"}

    def get(self, request):
        hours = max(1, min(int(request.query_params.get("hours") or 24), 24 * 30))
        since = timezone.now() - timedelta(hours=hours)
        camera_id = request.query_params.get("camera")

        events = DetectionEvent.objects.filter(
            organization__memberships__user=request.user,
            created_at__gte=since,
        )
        if camera_id:
            events = events.filter(camera_id=camera_id)

        counters = {
            "people_in": 0, "people_out": 0,
            "vehicles_in": 0, "vehicles_out": 0,
            "loitering": 0, "abandoned_object": 0,
        }

        # Line crossings — bucket by metadata.label + direction.
        line_qs = events.filter(event_type=DetectionEvent.EventType.LINE_CROSSING).values_list(
            "metadata", flat=True
        )
        for meta in line_qs:
            if not isinstance(meta, dict):
                continue
            label = str(meta.get("label", "")).lower()
            direction = str(meta.get("direction", "")).upper()
            is_vehicle = label in self.VEHICLE_LABELS
            is_person = label == "person"
            if direction == "IN":
                if is_person:
                    counters["people_in"] += 1
                elif is_vehicle:
                    counters["vehicles_in"] += 1
            elif direction == "OUT":
                if is_person:
                    counters["people_out"] += 1
                elif is_vehicle:
                    counters["vehicles_out"] += 1

        counters["loitering"] = events.filter(
            event_type=DetectionEvent.EventType.LOITERING
        ).count()
        counters["abandoned_object"] = events.filter(
            event_type=DetectionEvent.EventType.ABANDONED_OBJECT
        ).count()

        # Parking is "current state", not a time window — same logic as ParkingStatusView.
        parking_qs = ParkingSlotState.objects.filter(
            zone__camera__organization__memberships__user=request.user
        )
        if camera_id:
            parking_qs = parking_qs.filter(zone__camera_id=camera_id)
        parking = {"free": 0, "occupied": 0, "illegal": 0}
        for s in parking_qs.values_list("state", flat=True):
            parking[s] = parking.get(s, 0) + 1

        return Response(
            {
                "hours": hours,
                "camera": camera_id,
                "counters": counters,
                "parking": parking,
            }
        )


class HeatmapView(APIView):
    """``GET /api/analytics/heatmap/?camera=<uuid>&hours=24``

    Returns the aggregated occupancy heatmap for a single camera over the
    requested rolling window. The grid is always 16×16 (matches
    ``HeatmapBucket.GRID``); cells are normalised [0,1] for easy rendering.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        camera_id = request.query_params.get("camera")
        if not camera_id:
            return Response({"detail": "camera query param is required."}, status=400)
        hours = max(1, min(int(request.query_params.get("hours") or 24), 24 * 30))
        since = timezone.now() - timedelta(hours=hours)

        qs = HeatmapBucket.objects.filter(
            camera_id=camera_id,
            camera__organization__memberships__user=request.user,
            hour_bucket__gte=since,
        ).values("grid_x", "grid_y").annotate(weight=Sum("weight"))

        grid_size = HeatmapBucket.GRID
        grid = [[0 for _ in range(grid_size)] for _ in range(grid_size)]
        total = 0
        max_w = 0
        for row in qs:
            x, y, w = row["grid_x"], row["grid_y"], int(row["weight"] or 0)
            if 0 <= x < grid_size and 0 <= y < grid_size:
                grid[y][x] = w
                total += w
                if w > max_w:
                    max_w = w

        normalised = (
            [[(c / max_w) if max_w else 0.0 for c in row] for row in grid]
            if max_w
            else grid
        )
        return Response(
            {
                "camera": camera_id,
                "hours": hours,
                "grid_size": grid_size,
                "grid": normalised,
                "raw_max": max_w,
                "samples": total,
            }
        )


class ParkingStatusView(APIView):
    """``GET /api/analytics/parking/?camera=<uuid>`` — current parking slot map."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = ParkingSlotState.objects.filter(
            zone__camera__organization__memberships__user=request.user
        ).select_related("zone", "zone__camera")
        camera_id = request.query_params.get("camera")
        if camera_id:
            qs = qs.filter(zone__camera_id=camera_id)

        slots = [
            {
                "zone_id": str(s.zone_id),
                "zone_name": s.zone.name,
                "camera_id": str(s.zone.camera_id),
                "state": s.state,
                "since": s.since,
                "vehicle_track_id": s.vehicle_track_id,
                "geometry": s.zone.geometry,
            }
            for s in qs
        ]
        summary = {"free": 0, "occupied": 0, "illegal": 0}
        for s in slots:
            summary[s["state"]] = summary.get(s["state"], 0) + 1
        return Response({"slots": slots, "summary": summary})


extra_urls = [
    path("reports/", ReportsView.as_view(), name="reports"),
    path("reports/ai-summary/", ReportsAISummaryView.as_view(), name="reports-ai-summary"),
    path("heatmap/", HeatmapView.as_view(), name="heatmap"),
    path("parking/", ParkingStatusView.as_view(), name="parking-status"),
    path("counters/", CountersView.as_view(), name="counters"),
]
