"""Tests for AI provider settings: encryption, write-only key, RBAC, fallbacks."""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.organizations.models import Membership, Organization

from .models import AIProviderSetting
from .services import (
    AIProviderFactory,
    DisabledProvider,
    LocalOllamaProvider,
    OpenRouterProvider,
)

User = get_user_model()


def _user(email):
    return User.objects.create_user(email=email, password="pw12345678")


def _org(user, name="Acme", role=Membership.Role.OWNER):
    org = Organization.objects.create(name=name, slug=name.lower())
    Membership.objects.create(user=user, organization=org, role=role)
    return org


class AIProviderModelTests(TestCase):
    def test_api_key_encrypted_round_trip(self):
        u = _user("a@x.io")
        org = _org(u)
        cfg = AIProviderSetting(organization=org, provider_type="openrouter")
        cfg.api_key = "sk-or-test-1234567890abcd"
        cfg.save()

        cfg.refresh_from_db()
        self.assertEqual(cfg.api_key, "sk-or-test-1234567890abcd")
        self.assertTrue(cfg.has_api_key)
        self.assertTrue(cfg.masked_api_key.startswith("sk-or-"))
        self.assertTrue(cfg.masked_api_key.endswith("abcd"))
        self.assertIn("****", cfg.masked_api_key)

    def test_masked_when_short(self):
        u = _user("b@x.io")
        org = _org(u)
        cfg = AIProviderSetting(organization=org, provider_type="openrouter")
        cfg.api_key = "shorty"
        cfg.save()
        self.assertEqual(cfg.masked_api_key, "****")


class AIProviderFactoryTests(TestCase):
    def test_disabled_when_no_config(self):
        u = _user("c@x.io")
        org = _org(u)
        provider = AIProviderFactory.for_organization(org)
        self.assertIsInstance(provider, DisabledProvider)

    def test_openrouter_selected(self):
        u = _user("d@x.io")
        org = _org(u)
        AIProviderSetting.objects.create(
            organization=org, provider_type="openrouter", is_active=True,
            base_url="https://openrouter.ai/api/v1", model_name="openrouter/auto",
        )
        self.assertIsInstance(AIProviderFactory.for_organization(org), OpenRouterProvider)

    def test_ollama_selected(self):
        u = _user("e@x.io")
        org = _org(u)
        AIProviderSetting.objects.create(
            organization=org, provider_type="local_ollama", is_active=True,
            model_name="llama3.1",
        )
        self.assertIsInstance(AIProviderFactory.for_organization(org), LocalOllamaProvider)

    def test_inactive_falls_back_to_disabled(self):
        u = _user("f@x.io")
        org = _org(u)
        AIProviderSetting.objects.create(
            organization=org, provider_type="openrouter", is_active=False,
        )
        self.assertIsInstance(AIProviderFactory.for_organization(org), DisabledProvider)


class AIProviderFallbackTests(TestCase):
    def test_disabled_alert_summary_is_safe_string(self):
        p = DisabledProvider()
        out = p.generate_alert_summary({"title": "Crowd", "severity": "critical", "camera_name": "Lobby"})
        self.assertIn("Crowd", out)
        self.assertIn("CRITICAL", out)

    def test_disabled_test_connection_returns_false(self):
        ok, msg = DisabledProvider().test_connection()
        self.assertFalse(ok)


class AIProviderAPITests(TestCase):
    def setUp(self):
        self.owner = _user("own@x.io")
        self.viewer = _user("view@x.io")
        self.outsider = _user("out@x.io")
        self.org = _org(self.owner, "OrgA")
        Membership.objects.create(user=self.viewer, organization=self.org, role=Membership.Role.VIEWER)
        _org(self.outsider, "OrgB")
        self.client = APIClient()

    def test_unauthenticated_blocked(self):
        self.assertEqual(self.client.get("/api/ai/providers/").status_code, 401)

    def test_owner_can_create(self):
        self.client.force_authenticate(self.owner)
        r = self.client.post(
            "/api/ai/providers/",
            {
                "organization": str(self.org.id),
                "provider_type": "openrouter",
                "display_name": "Prod LLM",
                "base_url": "https://openrouter.ai/api/v1",
                "model_name": "openrouter/auto",
                "api_key": "sk-or-secret-key-1234567890",
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.content)
        body = r.json()
        self.assertNotIn("api_key", body)            # write-only
        self.assertTrue(body["has_api_key"])
        self.assertIn("****", body["masked_api_key"])

    def test_viewer_cannot_create(self):
        # First create as owner so an instance exists, then viewer tries to PATCH.
        cfg = AIProviderSetting.objects.create(
            organization=self.org, provider_type="openrouter",
        )
        self.client.force_authenticate(self.viewer)
        r = self.client.patch(
            f"/api/ai/providers/{cfg.id}/", {"model_name": "x"}, format="json"
        )
        self.assertEqual(r.status_code, 403)

    def test_outsider_cannot_see(self):
        AIProviderSetting.objects.create(organization=self.org, provider_type="openrouter")
        self.client.force_authenticate(self.outsider)
        r = self.client.get("/api/ai/providers/")
        self.assertEqual(r.json()["count"], 0)
