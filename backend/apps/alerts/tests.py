"""Tests for the rules engine — conditions, cooldown, severity, email side-effect."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.analytics.models import DetectionEvent
from apps.cameras.models import Camera
from apps.organizations.models import Membership, Organization

from .models import Alert, AlertRule
from .tasks import _condition_matches, _infer_severity, check_offline_cameras, evaluate_event

User = get_user_model()


def _make_org(name="Acme"):
    user = User.objects.create_user(email=f"u_{name.lower()}@x.io", password="pw12345678")
    org = Organization.objects.create(name=name, slug=name.lower())
    Membership.objects.create(user=user, organization=org, role=Membership.Role.OWNER)
    return user, org


def _make_camera(org, name="Cam 1"):
    cam = Camera(organization=org, name=name, location="lobby")
    cam.rtsp_url = "rtsp://user:pass@10.0.0.1:554/stream"
    cam.save()
    return cam


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
                   ALERT_COOLDOWN_SECONDS=0)
class RulesEngineTests(TestCase):
    def setUp(self):
        _, self.org = _make_org()
        self.cam = _make_camera(self.org)

    # --- Pure helpers ---------------------------------------------------
    def test_condition_matches_gt(self):
        self.assertTrue(_condition_matches("greater_than", 10, 5))
        self.assertFalse(_condition_matches("greater_than", 5, 5))

    def test_condition_matches_lt_eq(self):
        self.assertTrue(_condition_matches("less_than", 2, 5))
        self.assertTrue(_condition_matches("equals", 5, 5))
        self.assertFalse(_condition_matches("equals", 4, 5))

    def test_infer_severity_doubles_to_critical(self):
        rule = AlertRule(
            rule_type=AlertRule.RuleType.PEOPLE_COUNT,
            condition=AlertRule.Condition.GT,
            threshold_value=10,
        )
        self.assertEqual(_infer_severity(rule, 25), Alert.Severity.CRITICAL)
        self.assertEqual(_infer_severity(rule, 12), Alert.Severity.WARNING)

    # --- evaluate_event -------------------------------------------------
    def test_evaluate_event_triggers_and_emails(self):
        rule = AlertRule.objects.create(
            organization=self.org,
            camera=self.cam,
            name="Crowd > 5",
            rule_type=AlertRule.RuleType.PEOPLE_COUNT,
            threshold_value=5,
            condition=AlertRule.Condition.GT,
            notification_email="ops@example.com",
            cooldown_seconds=0,
        )
        event = DetectionEvent.objects.create(
            organization=self.org, camera=self.cam,
            event_type=DetectionEvent.EventType.PEOPLE_COUNT,
            people_count=12, confidence=0.9,
        )

        n = evaluate_event(str(event.id))

        self.assertEqual(n, 1)
        self.assertEqual(Alert.objects.filter(alert_rule=rule).count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Crowd > 5", mail.outbox[0].subject)
        # HTML alternative attached
        self.assertTrue(any("text/html" in p[1] for p in mail.outbox[0].alternatives))

    def test_evaluate_event_skips_below_threshold(self):
        AlertRule.objects.create(
            organization=self.org, camera=self.cam, name="r",
            rule_type=AlertRule.RuleType.PEOPLE_COUNT,
            threshold_value=10, condition=AlertRule.Condition.GT,
            cooldown_seconds=0,
        )
        event = DetectionEvent.objects.create(
            organization=self.org, camera=self.cam,
            event_type=DetectionEvent.EventType.PEOPLE_COUNT, people_count=3,
        )
        self.assertEqual(evaluate_event(str(event.id)), 0)
        self.assertEqual(Alert.objects.count(), 0)

    def test_cooldown_prevents_duplicate(self):
        rule = AlertRule.objects.create(
            organization=self.org, camera=self.cam, name="r",
            rule_type=AlertRule.RuleType.PEOPLE_COUNT,
            threshold_value=5, condition=AlertRule.Condition.GT,
            cooldown_seconds=3600,
        )
        # Pre-existing alert within cooldown window.
        Alert.objects.create(
            organization=self.org, camera=self.cam, alert_rule=rule,
            title="old", message="", severity=Alert.Severity.WARNING,
        )
        event = DetectionEvent.objects.create(
            organization=self.org, camera=self.cam,
            event_type=DetectionEvent.EventType.PEOPLE_COUNT, people_count=20,
        )
        with override_settings(ALERT_COOLDOWN_SECONDS=3600):
            self.assertEqual(evaluate_event(str(event.id)), 0)
        self.assertEqual(Alert.objects.count(), 1)  # no new alert created

    def test_rule_scoped_to_other_camera_does_not_fire(self):
        other = _make_camera(self.org, name="Cam 2")
        AlertRule.objects.create(
            organization=self.org, camera=other, name="r",
            rule_type=AlertRule.RuleType.PEOPLE_COUNT,
            threshold_value=1, condition=AlertRule.Condition.GT,
            cooldown_seconds=0,
        )
        event = DetectionEvent.objects.create(
            organization=self.org, camera=self.cam,
            event_type=DetectionEvent.EventType.PEOPLE_COUNT, people_count=99,
        )
        self.assertEqual(evaluate_event(str(event.id)), 0)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
                   ALERT_COOLDOWN_SECONDS=0)
class OfflineCheckerTests(TestCase):
    def setUp(self):
        _, self.org = _make_org("Beta")
        self.cam = _make_camera(self.org, name="Front Door")

    def test_offline_camera_raises_alert(self):
        # Camera last seen 30 minutes ago.
        self.cam.last_seen_at = timezone.now() - timedelta(minutes=30)
        self.cam.status = Camera.Status.OFFLINE
        self.cam.save()

        AlertRule.objects.create(
            organization=self.org, camera=None, name="offline",
            rule_type=AlertRule.RuleType.CAMERA_OFFLINE,
            threshold_value=1, condition=AlertRule.Condition.GT,
            cooldown_seconds=0,
        )
        n = check_offline_cameras(max_age_minutes=5)
        self.assertEqual(n, 1)
        alert = Alert.objects.get()
        self.assertEqual(alert.severity, Alert.Severity.CRITICAL)

    def test_recent_camera_does_not_alert(self):
        self.cam.last_seen_at = timezone.now()
        self.cam.status = Camera.Status.ONLINE
        self.cam.save()
        AlertRule.objects.create(
            organization=self.org, camera=None, name="offline",
            rule_type=AlertRule.RuleType.CAMERA_OFFLINE,
            threshold_value=1, condition=AlertRule.Condition.GT,
        )
        self.assertEqual(check_offline_cameras(max_age_minutes=5), 0)
