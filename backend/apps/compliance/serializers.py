from rest_framework import serializers

from .models import DataProcessingConsent


class DataProcessingConsentSerializer(serializers.ModelSerializer):
    is_valid = serializers.BooleanField(read_only=True)

    class Meta:
        model = DataProcessingConsent
        fields = (
            "id",
            "organization",
            "accepted_by",
            "written_consent",
            "camera_ownership",
            "data_processing_terms",
            "terms_version",
            "ip_address",
            "user_agent",
            "notes",
            "revoked_at",
            "is_valid",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id", "accepted_by", "ip_address", "user_agent",
            "is_valid", "created_at", "updated_at",
        )

    def validate(self, attrs):
        required = ("written_consent", "camera_ownership", "data_processing_terms")
        missing = [k for k in required if not attrs.get(k, False)]
        if missing:
            raise serializers.ValidationError(
                {k: "Must be true to record valid consent." for k in missing}
            )
        return attrs
