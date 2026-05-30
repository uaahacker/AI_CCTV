from rest_framework import serializers

from apps.common.security import mask_rtsp_url, validate_rtsp_url
from apps.organizations.models import Organization

from .models import Camera, CameraHealthCheck, Zone


class CameraSerializer(serializers.ModelSerializer):
    rtsp_url = serializers.CharField(write_only=True)
    rtsp_url_masked = serializers.SerializerMethodField(read_only=True)
    organization = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.none())

    class Meta:
        model = Camera
        fields = (
            "id",
            "organization",
            "name",
            "location",
            "rtsp_url",
            "rtsp_url_masked",
            "is_active",
            "status",
            "last_seen_at",
            "last_error",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "status", "last_seen_at", "last_error", "created_at", "updated_at")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            self.fields["organization"].queryset = Organization.objects.filter(
                memberships__user=request.user
            ).distinct()

    def get_rtsp_url_masked(self, obj):
        return mask_rtsp_url(obj.rtsp_url)

    def validate_rtsp_url(self, value):
        if not validate_rtsp_url(value):
            raise serializers.ValidationError(
                "Must be a valid rtsp://, rtsps://, http:// or https:// URL."
            )
        return value

    def create(self, validated_data):
        rtsp = validated_data.pop("rtsp_url")
        cam = Camera(**validated_data)
        cam.rtsp_url = rtsp
        cam.save()
        return cam

    def update(self, instance, validated_data):
        rtsp = validated_data.pop("rtsp_url", None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        if rtsp is not None:
            instance.rtsp_url = rtsp
        instance.save()
        return instance


class CameraHealthCheckSerializer(serializers.ModelSerializer):
    class Meta:
        model = CameraHealthCheck
        fields = ("id", "camera", "status", "latency_ms", "error_message", "checked_at")
        read_only_fields = fields


class ZoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Zone
        fields = (
            "id",
            "camera",
            "name",
            "kind",
            "geometry",
            "direction",
            "is_active",
            "config",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate(self, attrs):
        # Re-use the model's clean() rules so the API gets the same
        # validation as the admin and ORM.
        instance = Zone(**{**({"camera": self.instance.camera} if self.instance else {}), **attrs})
        instance.clean()
        return attrs

