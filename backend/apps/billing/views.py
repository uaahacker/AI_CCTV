"""Billing views — read-only plan/subscription endpoints plus optional
Stripe Checkout, Customer Portal, and Webhook handlers.

If ``STRIPE_SECRET_KEY`` isn't configured, the Stripe endpoints return
HTTP 503 with a helpful message rather than crashing.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.audit.utils import log_action

from . import stripe_adapter as stripe_adapter
from .models import OrganizationSubscription, SubscriptionPlan
from .serializers import OrganizationSubscriptionSerializer, SubscriptionPlanSerializer

logger = logging.getLogger(__name__)


class SubscriptionPlanViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SubscriptionPlan.objects.filter(is_active=True)
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [permissions.IsAuthenticated]


class OrganizationSubscriptionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrganizationSubscriptionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return OrganizationSubscription.objects.filter(
            organization__memberships__user=self.request.user
        ).distinct()

    @action(detail=True, methods=["post"], url_path="checkout")
    def checkout(self, request, pk=None):
        """Create a Stripe Checkout Session for this subscription.

        Body::

            { "plan_id": "<plan uuid>", "quantity": 5 }
        """
        if not stripe_adapter.is_enabled():
            return Response(
                {"detail": "Stripe billing is not configured on this server."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        subscription = self.get_object()
        plan_id = request.data.get("plan_id")
        quantity = int(request.data.get("quantity") or subscription.seats_cameras or 1)
        if not plan_id:
            return Response(
                {"detail": "Missing 'plan_id'."}, status=status.HTTP_400_BAD_REQUEST
            )
        try:
            plan = SubscriptionPlan.objects.get(pk=plan_id, is_active=True)
        except SubscriptionPlan.DoesNotExist:
            return Response(
                {"detail": "Unknown plan."}, status=status.HTTP_404_NOT_FOUND
            )
        if not plan.stripe_price_id:
            return Response(
                {"detail": "This plan has no Stripe price configured."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        success_url = (
            request.data.get("success_url")
            or settings.STRIPE_SUCCESS_URL
            or "https://example.com/billing/success"
        )
        cancel_url = (
            request.data.get("cancel_url")
            or settings.STRIPE_CANCEL_URL
            or "https://example.com/billing/cancel"
        )

        try:
            payload = stripe_adapter.create_checkout_session(
                subscription,
                price_id=plan.stripe_price_id,
                quantity=quantity,
                success_url=success_url,
                cancel_url=cancel_url,
            )
        except stripe_adapter.StripeNotConfigured as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as exc:  # noqa: BLE001 - Stripe SDK has many error types
            logger.exception("Stripe checkout creation failed")
            return Response(
                {"detail": f"Stripe error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        log_action(
            user=request.user,
            action="billing.checkout.create",
            request=request,
            metadata={"plan": plan.tier, "quantity": quantity},
        )
        return Response(payload, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="portal")
    def portal(self, request, pk=None):
        """Return a one-time URL to Stripe's customer billing portal."""
        if not stripe_adapter.is_enabled():
            return Response(
                {"detail": "Stripe billing is not configured on this server."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        subscription = self.get_object()
        return_url = request.data.get("return_url") or settings.STRIPE_SUCCESS_URL or "/"
        try:
            payload = stripe_adapter.create_billing_portal_session(
                subscription, return_url=return_url
            )
        except stripe_adapter.StripeNotConfigured as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Stripe portal session failed")
            return Response(
                {"detail": f"Stripe error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(payload, status=status.HTTP_200_OK)


class StripeWebhookView(APIView):
    """``POST /api/billing/webhook/`` — Stripe → us.

    Authenticated by HMAC signature, not by JWT. Idempotent: replaying the
    same event leaves state unchanged.
    """

    permission_classes = [permissions.AllowAny]
    authentication_classes: list = []
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "stripe_webhook"

    # No CSRF because Stripe is not a browser.
    def dispatch(self, request, *args, **kwargs):
        setattr(request, "_dont_enforce_csrf_checks", True)
        return super().dispatch(request, *args, **kwargs)

    def post(self, request):
        if not stripe_adapter.is_enabled():
            return Response(
                {"detail": "Stripe billing is not configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        sig = request.META.get("HTTP_STRIPE_SIGNATURE", "")
        try:
            event = stripe_adapter.verify_webhook_signature(request.body, sig)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Rejected Stripe webhook: %s", exc)
            return Response(
                {"detail": f"Invalid webhook: {exc}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        event_type = event.get("type", "")
        data = event.get("data", {}).get("object", {})
        try:
            _handle_event(event_type, data)
        except Exception:  # noqa: BLE001
            logger.exception("Stripe webhook handler failed for %s", event_type)
            return Response(
                {"detail": "Handler error."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return Response({"received": True}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------
def _find_sub_by_customer(customer_id: str):
    if not customer_id:
        return None
    return OrganizationSubscription.objects.filter(
        stripe_customer_id=customer_id
    ).first()


def _set_status(sub, new_status, *, current_period_end=None, stripe_sub_id=None):
    update_fields = ["status", "updated_at"]
    sub.status = new_status
    if stripe_sub_id and not sub.stripe_subscription_id:
        sub.stripe_subscription_id = stripe_sub_id
        update_fields.append("stripe_subscription_id")
    if current_period_end:
        # current_period_end on Stripe is unix-seconds.
        sub.current_period_end = timezone.datetime.fromtimestamp(
            current_period_end, tz=timezone.utc
        )
        update_fields.append("current_period_end")
    sub.save(update_fields=update_fields)


def _handle_event(event_type: str, obj: dict) -> None:
    if event_type == "checkout.session.completed":
        customer = obj.get("customer")
        sub = _find_sub_by_customer(customer)
        if sub is not None:
            _set_status(
                sub,
                OrganizationSubscription.Status.ACTIVE,
                stripe_sub_id=obj.get("subscription"),
            )
        return

    if event_type in {"customer.subscription.created", "customer.subscription.updated"}:
        sub = _find_sub_by_customer(obj.get("customer"))
        if sub is None:
            return
        stripe_status = obj.get("status", "")
        mapping = {
            "trialing": OrganizationSubscription.Status.TRIAL,
            "active": OrganizationSubscription.Status.ACTIVE,
            "past_due": OrganizationSubscription.Status.PAST_DUE,
            "unpaid": OrganizationSubscription.Status.PAST_DUE,
            "canceled": OrganizationSubscription.Status.CANCELED,
            "incomplete_expired": OrganizationSubscription.Status.CANCELED,
        }
        _set_status(
            sub,
            mapping.get(stripe_status, sub.status),
            current_period_end=obj.get("current_period_end"),
            stripe_sub_id=obj.get("id"),
        )
        return

    if event_type == "customer.subscription.deleted":
        sub = _find_sub_by_customer(obj.get("customer"))
        if sub is not None:
            _set_status(sub, OrganizationSubscription.Status.CANCELED)
        return

    if event_type == "invoice.payment_failed":
        sub = _find_sub_by_customer(obj.get("customer"))
        if sub is not None:
            _set_status(sub, OrganizationSubscription.Status.PAST_DUE)
        return

    # All other events are acknowledged but ignored.
    logger.debug("Ignoring Stripe event %s", event_type)
