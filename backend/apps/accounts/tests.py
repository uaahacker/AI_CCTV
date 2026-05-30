"""Tests for registration, JWT login, and /me endpoint."""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

User = get_user_model()


class AccountsAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_register_creates_user(self):
        r = self.client.post(
            "/api/auth/register/",
            {"email": "new@x.io", "password": "supersecret123", "full_name": "New User"},
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(User.objects.filter(email="new@x.io").exists())

    def test_register_rejects_weak_password(self):
        r = self.client.post(
            "/api/auth/register/",
            {"email": "new@x.io", "password": "123", "full_name": "x"},
            format="json",
        )
        self.assertEqual(r.status_code, 400)

    def test_register_rejects_duplicate_email(self):
        User.objects.create_user(email="dup@x.io", password="pw12345678")
        r = self.client.post(
            "/api/auth/register/",
            {"email": "dup@x.io", "password": "anotherpw123", "full_name": "x"},
            format="json",
        )
        self.assertEqual(r.status_code, 400)

    def test_jwt_login_returns_tokens(self):
        User.objects.create_user(email="ok@x.io", password="pw12345678")
        r = self.client.post(
            "/api/auth/token/",
            {"email": "ok@x.io", "password": "pw12345678"},
            format="json",
        )
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertIn("access", body)
        self.assertIn("refresh", body)

    def test_me_requires_auth(self):
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)

    def test_me_returns_current_user(self):
        u = User.objects.create_user(email="me@x.io", password="pw12345678")
        self.client.force_authenticate(user=u)
        r = self.client.get("/api/auth/me/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["email"], "me@x.io")


class SchemaDocsTests(TestCase):
    """Smoke-test that the OpenAPI schema renders without exceptions."""

    def test_schema_is_served(self):
        client = APIClient()
        r = client.get("/api/schema/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"openapi", r.content[:200].lower())
