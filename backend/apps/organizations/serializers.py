from django.utils.text import slugify
from rest_framework import serializers

from .models import Membership, Organization


class OrganizationSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = ("id", "name", "slug", "is_active", "role", "created_at")
        read_only_fields = ("id", "slug", "is_active", "role", "created_at")

    def get_role(self, obj):
        user = self.context["request"].user
        if not user.is_authenticated:
            return None
        m = obj.memberships.filter(user=user).first()
        return m.role if m else None

    def create(self, validated_data):
        request = self.context["request"]
        name = validated_data["name"]
        base_slug = slugify(name) or "org"
        slug = base_slug
        i = 1
        while Organization.objects.filter(slug=slug).exists():
            i += 1
            slug = f"{base_slug}-{i}"
        org = Organization.objects.create(name=name, slug=slug)
        Membership.objects.create(
            user=request.user, organization=org, role=Membership.Role.OWNER
        )
        return org


class MembershipSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = Membership
        fields = ("id", "organization", "user", "user_email", "role", "created_at")
        read_only_fields = ("id", "user_email", "created_at")
