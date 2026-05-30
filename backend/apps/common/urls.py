from django.urls import path

from .views import HealthView, MediaFileView, MediaSignURLView, MetricsView

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("health/metrics/", MetricsView.as_view(), name="metrics"),
    path("media/sign/", MediaSignURLView.as_view(), name="media-sign"),
    path("media/file/", MediaFileView.as_view(), name="media-file"),
]
