from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AcademyViewSet

router = DefaultRouter()
router.register(r"", AcademyViewSet, basename="academy")
urlpatterns = [
    path("", include(router.urls)),
]
