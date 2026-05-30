from rest_framework import serializers

from .models import Alert, AlertRule, VALID_CHANNELS


class AlertRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = AlertRule
        fields = (
            "id",
            "organization",
            "camera",
            "name",
            "rule_type",
            "threshold_value",
            "condition",
            "notification_email",
            "channels",
            "channel_config",
            "active_from",
            "active_to",
            "days_of_week",
            "is_active",
            "cooldown_seconds",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_channels(self, value):
        if value is None:
            return []
        bad = [c for c in value if c not in VALID_CHANNELS]
        if bad:
            raise serializers.ValidationError(
                f"Unknown channels: {bad}. Allowed: {sorted(VALID_CHANNELS)}"
            )
        return value

    def validate_channel_config(self, value):
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("channel_config must be an object.")
        return value

    def validate_days_of_week(self, value):
        if value is None:
            return []
        if not isinstance(value, list):
            raise serializers.ValidationError("days_of_week must be a list.")
        bad = [d for d in value if not isinstance(d, int) or not 1 <= d <= 7]
        if bad:
            raise serializers.ValidationError("days_of_week entries must be ints 1..7.")
        return value


class AlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = Alert
        fields = (
            "id",
            "organization",
            "camera",
            "alert_rule",
            "title",
            "message",
            "severity",
            "status",
            "metadata",
            "ai_summary",
            "clip_path",
            "clip_duration_s",
            "delivery_log",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id", "created_at", "updated_at",
            "ai_summary", "delivery_log",
        )
