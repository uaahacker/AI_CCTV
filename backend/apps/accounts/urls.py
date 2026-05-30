from django.urls import path

from .mfa_views import (
    MFAConfirmView,
    MFADisableView,
    MFAEnrollView,
    MFAStatusView,
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
]
