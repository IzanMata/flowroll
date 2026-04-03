from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import TournamentDivisionViewSet, TournamentMatchViewSet, TournamentViewSet

router = DefaultRouter()
router.register(r"tournaments", TournamentViewSet, basename="tournament")
router.register(r"divisions", TournamentDivisionViewSet, basename="tournamentdivision")
router.register(r"matches", TournamentMatchViewSet, basename="tournamentmatch")

urlpatterns = [
    path("", include(router.urls)),
]
