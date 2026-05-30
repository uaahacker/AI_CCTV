"""Tests for camera RTSP encryption, masking, and org-scoped access."""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.common.security import mask_rtsp_url, validate_rtsp_url
from apps.organizations.models import Membership, Organization

from .models import Camera

User = get_user_model()


def _make_user(email):
    return User.objects.create_user(email=email, password="pw12345678")


def _make_org(user, name="Acme", role=Membership.Role.OWNER):
    org = Organization.objects.create(name=name, slug=name.lower())
    Membership.objects.create(user=user, organization=org, role=role)
    return org


class SecurityHelperTests(TestCase):
    def test_mask_strips_credentials(self):
        masked = mask_rtsp_url("rtsp://admin:secret@10.0.0.1:554/stream")
        self.assertNotIn("admin", masked)
        self.assertNotIn("secret", masked)
        self.assertIn("***:***@10.0.0.1:554", masked)

    def test_mask_passthrough_when_no_credentials(self):
        self.assertEqual(
            mask_rtsp_url("rtsp://10.0.0.1:554/stream"),
            "rtsp://10.0.0.1:554/stream",
        )

    def test_mask_handles_empty(self):
        self.assertEqual(mask_rtsp_url(""), "")

    def test_validate_rtsp_url(self):
        self.assertTrue(validate_rtsp_url("rtsp://10.0.0.1/s"))
        self.assertTrue(validate_rtsp_url("rtsps://host/s"))
        self.assertTrue(validate_rtsp_url("https://cam.local/feed"))
        self.assertFalse(validate_rtsp_url("ftp://10.0.0.1/s"))
        self.assertFalse(validate_rtsp_url("not a url"))
        self.assertFalse(validate_rtsp_url(""))


class CameraModelEncryptionTests(TestCase):
    def test_rtsp_url_round_trip(self):
        user = _make_user("e@x.io")
        org = _make_org(user)
        cam = Camera(organization=org, name="c")
        cam.rtsp_url = "rtsp://u:p@10.0.0.1:554/s"
        cam.save()

        cam.refresh_from_db()
        self.assertEqual(cam.rtsp_url, "rtsp://u:p@10.0.0.1:554/s")
        # Stored value should not equal plaintext when encryption key is set.
        from django.conf import settings
        if settings.FIELD_ENCRYPTION_KEY:
            self.assertNotEqual(cam.rtsp_url_encrypted, "rtsp://u:p@10.0.0.1:554/s")


class CameraAPITests(TestCase):
    def setUp(self):
        self.alice = _make_user("alice@x.io")
        self.bob = _make_user("bob@x.io")
        self.org_a = _make_org(self.alice, "OrgA")
        self.org_b = _make_org(self.bob, "OrgB")

        self.cam_a = Camera(organization=self.org_a, name="A-Cam")
        self.cam_a.rtsp_url = "rtsp://u:p@10.0.0.1/s"
        self.cam_a.save()

        self.client = APIClient()

    def _login(self, user):
        self.client.force_authenticate(user=user)

    def test_unauthenticated_blocked(self):
        r = self.client.get("/api/cameras/")
        self.assertEqual(r.status_code, 401)

    def test_member_sees_only_own_org_cameras(self):
        self._login(self.bob)
        r = self.client.get("/api/cameras/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["count"], 0)

        self._login(self.alice)
        r = self.client.get("/api/cameras/")
        self.assertEqual(r.json()["count"], 1)

    def test_response_never_leaks_raw_rtsp(self):
        self._login(self.alice)
        r = self.client.get(f"/api/cameras/{self.cam_a.id}/")
        body = r.json()
        self.assertNotIn("rtsp_url", body)  # write-only
        self.assertIn("rtsp_url_masked", body)
        self.assertNotIn("u:p", body["rtsp_url_masked"])

    def test_cross_org_camera_404(self):
        self._login(self.bob)
        r = self.client.get(f"/api/cameras/{self.cam_a.id}/")
        self.assertEqual(r.status_code, 404)

    def test_viewer_role_cannot_write(self):
        carol = _make_user("carol@x.io")
        Membership.objects.create(
            user=carol, organization=self.org_a, role=Membership.Role.VIEWER
        )
        self._login(carol)
        r = self.client.patch(f"/api/cameras/{self.cam_a.id}/", {"name": "renamed"}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_invalid_rtsp_url_rejected(self):
        self._login(self.alice)
        r = self.client.post(
            "/api/cameras/",
            {
                "organization": str(self.org_a.id),
                "name": "bad",
                "rtsp_url": "ftp://nope",
            },
            format="json",
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("rtsp_url", r.json())
