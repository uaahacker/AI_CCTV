"""Shared pytest fixtures.

Keep these tiny \u2014 the goal is smoke coverage in CI, not exhaustive testing.
Slow / network-dependent fixtures (real RTSP, ffmpeg, Sentry) go in the
per-app conftest if/when they are needed.
"""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model


@pytest.fixture
def user(db):
    """A plain authenticated user with a known password."""
    User = get_user_model()
    return User.objects.create_user(
        email="u@example.com", password="pw-pw-pw-pw", full_name="U"
    )


@pytest.fixture
def org(db, user):
    """An organisation with `user` as the owner."""
    from apps.organizations.models import Membership, Organization

    o = Organization.objects.create(name="Acme", slug="acme")
    Membership.objects.create(user=user, organization=o, role=Membership.Role.OWNER)
    return o


@pytest.fixture
def api_client():
    from rest_framework.test import APIClient

    return APIClient()


@pytest.fixture
def auth_client(api_client, user):
    api_client.force_authenticate(user=user)
    return api_client
