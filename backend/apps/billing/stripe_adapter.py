"""Thin Stripe adapter.

This module is intentionally tolerant: if the ``stripe`` SDK isn't installed
or ``STRIPE_SECRET_KEY`` isn't configured, the helpers raise a clear
``StripeNotConfigured`` error rather than crashing imports. The rest of the
project can therefore import this module unconditionally.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import time
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)


class StripeNotConfigured(RuntimeError):
    """Raised when a caller tries to use Stripe without it being enabled."""


def is_enabled() -> bool:
    return bool(getattr(settings, "STRIPE_ENABLED", False))


def _client():
    if not is_enabled():
        raise StripeNotConfigured(
            "Stripe is disabled — set STRIPE_SECRET_KEY to enable billing."
        )
    try:
        import stripe  # noqa: WPS433 - optional dep
    except ImportError as exc:  # pragma: no cover - optional dep
        raise StripeNotConfigured(
            "The 'stripe' Python package isn't installed. "
            "Add it to requirements.txt or `pip install stripe`."
        ) from exc
    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe


# ---------------------------------------------------------------------------
# Customer + Checkout Session
# ---------------------------------------------------------------------------
def ensure_customer(subscription) -> str:
    """Return Stripe customer id, creating one if needed."""
    stripe = _client()
    if subscription.stripe_customer_id:
        return subscription.stripe_customer_id
    org = subscription.organization
    customer = stripe.Customer.create(
        name=org.name,
        metadata={"organization_id": str(org.id)},
    )
    subscription.stripe_customer_id = customer["id"]
    subscription.save(update_fields=["stripe_customer_id", "updated_at"])
    return customer["id"]


def create_checkout_session(
    subscription,
    *,
    price_id: str,
    quantity: int,
    success_url: str,
    cancel_url: str,
) -> dict[str, Any]:
    """Create a Stripe Checkout Session for a new subscription."""
    stripe = _client()
    customer_id = ensure_customer(subscription)
    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": price_id, "quantity": max(1, int(quantity))}],
        success_url=success_url,
        cancel_url=cancel_url,
        client_reference_id=str(subscription.organization_id),
        metadata={"organization_id": str(subscription.organization_id)},
    )
    return {"id": session["id"], "url": session["url"]}


def create_billing_portal_session(
    subscription, *, return_url: str
) -> dict[str, str]:
    stripe = _client()
    if not subscription.stripe_customer_id:
        raise StripeNotConfigured("No Stripe customer yet — start a checkout first.")
    portal = stripe.billing_portal.Session.create(
        customer=subscription.stripe_customer_id,
        return_url=return_url,
    )
    return {"url": portal["url"]}


# ---------------------------------------------------------------------------
# Webhook signature verification
# ---------------------------------------------------------------------------
def verify_webhook_signature(payload: bytes, sig_header: str, tolerance: int = 300) -> dict:
    """Validate the ``Stripe-Signature`` header (RFC-style ``t=..,v1=..``).

    We do this ourselves so the module stays usable even when ``stripe`` is
    not installed (e.g. read-only health check). Raises ``ValueError`` on
    any failure.
    """
    secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", "")
    if not secret:
        raise ValueError("STRIPE_WEBHOOK_SECRET is not configured.")
    if not sig_header:
        raise ValueError("Missing Stripe-Signature header.")

    parts = dict(p.strip().split("=", 1) for p in sig_header.split(",") if "=" in p)
    timestamp = parts.get("t")
    signature = parts.get("v1")
    if not timestamp or not signature:
        raise ValueError("Malformed Stripe-Signature header.")

    if abs(time.time() - int(timestamp)) > tolerance:
        raise ValueError("Webhook timestamp outside tolerance window.")

    signed_payload = f"{timestamp}.{payload.decode('utf-8')}".encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise ValueError("Invalid Stripe signature.")

    import json
    return json.loads(payload.decode("utf-8"))
