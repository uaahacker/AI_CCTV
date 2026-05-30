"""Smoke tests \u2014 verify the API surface boots and basic flows work.

CI runs these against real Postgres + Redis. They are intentionally narrow
so the suite stays under 30s.
"""
from __future__ import annotations

import pytest


@pytest.mark.django_db
def test_health_endpoint(api_client):
    resp = api_client.get("/api/health/")
    assert resp.status_code in (200, 503)  # 503 only if redis is down
    assert "checks" in resp.json()


@pytest.mark.django_db
def test_register_then_me(api_client):
    resp = api_client.post(
        "/api/auth/register/",
        {"email": "new@example.com", "password": "supersafe123", "full_name": "New"},
        format="json",
    )
    assert resp.status_code == 201

    login = api_client.post(
        "/api/auth/token/",
        {"email": "new@example.com", "password": "supersafe123"},
        format="json",
    )
    assert login.status_code == 200
    assert "access" in login.json()

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['access']}")
    me = api_client.get("/api/auth/me/")
    assert me.status_code == 200
    assert me.json()["email"] == "new@example.com"


@pytest.mark.django_db
def test_password_reset_request_is_silent_for_unknown_email(api_client):
    """Must always return 202 to avoid email-enumeration."""
    resp = api_client.post(
        "/api/auth/password/reset/request/",
        {"email": "nobody@example.com"},
        format="json",
    )
    assert resp.status_code == 202


@pytest.mark.django_db
def test_password_reset_full_flow(api_client, user):
    from datetime import timedelta
    import secrets

    from django.utils import timezone

    from apps.accounts.models import PasswordResetToken
    from apps.accounts.password_reset import _hash

    plain = secrets.token_urlsafe(32)
    PasswordResetToken.objects.create(
        user=user,
        token_hash=_hash(plain),
        expires_at=timezone.now() + timedelta(hours=1),
    )
    resp = api_client.post(
        "/api/auth/password/reset/confirm/",
        {"token": plain, "new_password": "another-strong-pw-77"},
        format="json",
    )
    assert resp.status_code == 200
    user.refresh_from_db()
    assert user.check_password("another-strong-pw-77")


@pytest.mark.django_db
def test_organization_create_and_soft_delete(auth_client):
    create = auth_client.post("/api/organizations/", {"name": "Test Org"}, format="json")
    assert create.status_code == 201
    org_id = create.json()["id"]

    delete = auth_client.delete(f"/api/organizations/{org_id}/")
    assert delete.status_code == 202
    assert delete.json()["deleted_at"]


@pytest.mark.django_db
def test_camera_create_auto_zone(auth_client, org):
    from apps.cameras.models import Zone

    resp = auth_client.post(
        "/api/cameras/",
        {
            "organization": str(org.id),
            "name": "Front door",
            "rtsp_url": "rtsp://user:pass@192.0.2.1:554/stream",
        },
        format="json",
    )
    assert resp.status_code == 201
    cam_id = resp.json()["id"]
    assert Zone.objects.filter(camera_id=cam_id).count() == 1


@pytest.mark.django_db
def test_media_sign_url_round_trip(auth_client, org):
    from apps.cameras.models import Camera

    cam = Camera.objects.create(
        organization=org, name="cam", rtsp_url_encrypted="x"
    )
    rel = f"hls/{cam.id}/index.m3u8"
    resp = auth_client.post("/api/media/sign/", {"path": rel}, format="json")
    assert resp.status_code == 200
    body = resp.json()
    assert body["token"]
    assert body["expires"] > 0
    assert rel in body["url"]


@pytest.mark.django_db
def test_audit_log_visible_to_owner(auth_client, org):
    from apps.audit.models import AuditLog

    AuditLog.objects.create(
        organization=org, action="test.event", metadata={"a": 1}
    )
    resp = auth_client.get("/api/audit/logs/")
    assert resp.status_code == 200
    assert resp.json()["count"] >= 1


@pytest.mark.django_db
def test_alert_delivery_model_attached_to_alert(auth_client, org):
    from apps.alerts.models import Alert, AlertDelivery, AlertRule

    rule = AlertRule.objects.create(
        organization=org, name="r", rule_type="people_count",
        threshold_value=1, condition="greater_than",
    )
    alert = Alert.objects.create(
        organization=org, alert_rule=rule, title="t", severity="warning",
    )
    AlertDelivery.objects.create(
        alert=alert, channel="email", status=AlertDelivery.Status.SENT, attempts=1,
    )
    resp = auth_client.get(f"/api/alerts/{alert.id}/")
    assert resp.status_code == 200
    assert resp.json()["deliveries"][0]["channel"] == "email"


@pytest.mark.django_db
def test_purge_expired_data_runs(org):
    """Smoke \u2014 the task must run without errors on an empty database."""
    from apps.common.tasks import purge_expired_data

    out = purge_expired_data()
    assert isinstance(out, dict)
    assert "alerts" in out
