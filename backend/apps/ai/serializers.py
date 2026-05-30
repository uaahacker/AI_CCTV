from rest_framework import serializers

from apps.organizations.models import Organization

from .models import AIProviderSetting


class AIProviderSettingSerializer(serializers.ModelSerializer):
    """
    The plaintext `api_key` is WRITE-ONLY. Reads only ever return:
      - has_api_key  → boolean
      - masked_api_key  → 'sk-or-****abcd' (or empty string)
    The raw key never leaves the backend.
    """

    api_key = serializers.CharField(
        write_only=True, required=False, allow_blank=True, style={"input_type": "password"}
    )
    has_api_key = serializers.BooleanField(read_only=True)
    masked_api_key = serializers.CharField(read_only=True)
    organization = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.none())

    class Meta:
        model = AIProviderSetting
        fields = (
            "id",
            "organization",
            "provider_type",
            "display_name",
            "base_url",
            "model_name",
            "api_key",          # write-only
            "has_api_key",      # read-only
            "masked_api_key",   # read-only
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            self.fields["organization"].queryset = Organization.objects.filter(
                memberships__user=request.user
            ).distinct()

    def create(self, validated_data):
        api_key = validated_data.pop("api_key", "")
        obj = AIProviderSetting(**validated_data)
        if api_key:
            obj.api_key = api_key
        obj.save()
        return obj

    def update(self, instance, validated_data):
        api_key = validated_data.pop("api_key", None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        # Only overwrite the key when explicitly provided AND non-empty.
        # An empty string in PATCH means "don't change" — to clear, send null.
        if api_key:
            instance.api_key = api_key
        elif api_key is None and "api_key" in self.initial_data and self.initial_data["api_key"] is None:
            instance.api_key = ""
        instance.save()
        return instance
