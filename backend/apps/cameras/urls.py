from django.urls import path

from .views import CameraDiscoveryView, router

urlpatterns = router.urls + [
    path("discover/", CameraDiscoveryView.as_view(), name="camera-discover"),
]
