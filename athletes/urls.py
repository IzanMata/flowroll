from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AthleteProfileViewSet

router = DefaultRouter()
router.register(r"", AthleteProfileViewSet, basename="athlete")

urlpatterns = [
    path("", include(router.urls)),
]
