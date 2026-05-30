from django.urls import path

from .mfa_views import (
    MFAConfirmView,
    MFADisableView,
    MFAEnrollView,
    MFAStatusView,
)
from .password_reset import (
    EmailVerifyConfirmView,
    EmailVerifyRequestView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
)
from .views import (
    LogoutView,
    MeView,
    MFAVerifyView,
    RegisterView,
    ThrottledTokenObtainPairView,
    ThrottledTokenRefreshView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="auth-register"),
    path("me/", MeView.as_view(), name="auth-me"),
    path("token/", ThrottledTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", ThrottledTokenRefreshView.as_view(), name="token_refresh"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    # MFA
    path("mfa/enroll/", MFAEnrollView.as_view(), name="mfa-enroll"),
    path("mfa/confirm/", MFAConfirmView.as_view(), name="mfa-confirm"),
    path("mfa/status/", MFAStatusView.as_view(), name="mfa-status"),
    path("mfa/disable/", MFADisableView.as_view(), name="mfa-disable"),
    path("mfa/verify/", MFAVerifyView.as_view(), name="mfa-verify"),
    # Password reset
    path("password/reset/request/", PasswordResetRequestView.as_view(),
         name="auth-password-reset-request"),
    path("password/reset/confirm/", PasswordResetConfirmView.as_view(),
         name="auth-password-reset-confirm"),
    # Email verification
    path("email/verify/request/", EmailVerifyRequestView.as_view(),
         name="auth-email-verify-request"),
    path("email/verify/confirm/", EmailVerifyConfirmView.as_view(),
         name="auth-email-verify-confirm"),
]
