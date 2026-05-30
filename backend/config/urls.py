"""Root URL configuration."""
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)


api_v1_patterns = [
    # All auth (register, login, refresh, logout, MFA) lives in apps.accounts.urls.
    path("auth/", include("apps.accounts.urls")),
    path("organizations/", include("apps.organizations.urls")),
    path("cameras/", include("apps.cameras.urls")),
    path("analytics/", include("apps.analytics.urls")),
    path("alerts/", include("apps.alerts.urls")),
    path("audit/", include("apps.audit.urls")),
    path("ai/", include("apps.ai.urls")),
    path("compliance/", include("apps.compliance.urls")),
    # OpenAPI 3 schema + interactive docs
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include(api_v1_patterns)),
]
