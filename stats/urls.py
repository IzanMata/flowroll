from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AthleteStatsViewSet

router = DefaultRouter()
router.register(r"", AthleteStatsViewSet, basename="athletestats")

urlpatterns = [
    path("", include(router.urls)),
]
