from .views import extra_urls, router

urlpatterns = router.urls + extra_urls
