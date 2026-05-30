from rest_framework import serializers

from .models import DetectionEvent


class DetectionEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetectionEvent
        fields = (
            "id",
            "organization",
            "camera",
            "event_type",
            "people_count",
            "confidence",
            "metadata",
            "created_at",
        )
        read_only_fields = ("id", "created_at")
