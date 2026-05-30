"""Auth endpoints with rate-limit throttles, JWT blacklisting on logout,
and a two-step MFA login flow.

Endpoints exposed via this module:
- POST /api/auth/register/        — create a user (throttled).
- GET  /api/auth/me/              — current user profile.
- POST /api/auth/token/           — login. Returns either a real JWT pair
                                    OR an MFA challenge if TOTP is enabled.
- POST /api/auth/token/refresh/   — refresh access token (throttled).
- POST /api/auth/logout/          — blacklist the caller's refresh token.
- POST /api/auth/mfa/verify/      — second leg of the two-step login.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import generics, permissions, status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.audit.utils import log_action

from .mfa import (
    build_mfa_challenge,
    issue_tokens_for_user,
    user_has_active_mfa,
    verify_mfa_challenge,
)
from .serializers import RegisterSerializer, UserSerializer

User = get_user_model()


class _ScopedThrottleMixin:
    """Apply DRF's ScopedRateThrottle with the scope set on the view class."""

    throttle_classes = (ScopedRateThrottle,)


class RegisterView(_ScopedThrottleMixin, generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth_register"

    def perform_create(self, serializer):
        user = serializer.save()
        log_action(
            user=user,
            action="user.register",
            request=self.request,
            metadata={"email": user.email},
        )


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class ThrottledTokenObtainPairView(_ScopedThrottleMixin, TokenObtainPairView):
    """Standard JWT login, but if the user has MFA enabled we never hand out
    the JWT pair directly. Instead we return a short-lived ``mfa_token``;
    the client must POST it together with the TOTP code to
    ``/auth/mfa/verify/`` to receive the real tokens.
    """

    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth_login"

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except Exception:
            log_action(
                user=None,
                action="auth.login.failed",
                request=request,
                metadata={"email": str(request.data.get("email", ""))[:150]},
            )
            raise

        user = serializer.user  # type: ignore[attr-defined]

        if user_has_active_mfa(user):
            challenge = build_mfa_challenge(user)
            log_action(
                user=user,
                action="auth.login.mfa_required",
                request=request,
                metadata={},
            )
            return Response(
                {
                    "mfa_required": True,
                    "mfa_token": challenge,
                    "detail": (
                        "Multi-factor authentication required. POST this "
                        "mfa_token together with your 6-digit code to "
                        "/api/auth/mfa/verify/."
                    ),
                },
                status=status.HTTP_200_OK,
            )

        log_action(
            user=user, action="auth.login.success", request=request, metadata={}
        )
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class ThrottledTokenRefreshView(_ScopedThrottleMixin, TokenRefreshView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth_token_refresh"


class LogoutView(APIView):
    """POST ``{"refresh": "..."}`` to blacklist the refresh token.

    Returns 205 on success, 400 on malformed/expired token. The access token
    itself stays usable until it naturally expires (<= 60 min by default);
    the client should also discard it immediately.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        token = request.data.get("refresh")
        if not token:
            return Response(
                {"detail": "Missing 'refresh' field."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            RefreshToken(token).blacklist()
        except TokenError as exc:
            return Response(
                {"detail": f"Invalid refresh token: {exc}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        log_action(
            user=request.user, action="auth.logout", request=request, metadata={}
        )
        return Response(status=status.HTTP_205_RESET_CONTENT)


class MFAVerifyView(_ScopedThrottleMixin, APIView):
    """Second leg of the two-step login.

    Body::

        { "mfa_token": "<from /auth/token/>", "code": "123456" }

    Returns the standard ``{ access, refresh }`` payload on success.
    """

    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth_mfa_verify"

    def post(self, request):
        mfa_token = request.data.get("mfa_token")
        code = (request.data.get("code") or "").strip()
        if not mfa_token or not code:
            return Response(
                {"detail": "Both 'mfa_token' and 'code' are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            user = verify_mfa_challenge(mfa_token, code)
        except AuthenticationFailed as exc:
            log_action(
                user=None,
                action="auth.mfa.failed",
                request=request,
                metadata={"reason": str(exc.detail)},
            )
            return Response(
                {"detail": str(exc.detail)}, status=status.HTTP_401_UNAUTHORIZED
            )

        tokens = issue_tokens_for_user(user)
        log_action(
            user=user, action="auth.mfa.success", request=request, metadata={}
        )
        return Response(tokens, status=status.HTTP_200_OK)
