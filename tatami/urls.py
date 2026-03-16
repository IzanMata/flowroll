from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import MatchupViewSet, TimerPresetViewSet, TimerSessionViewSet, WeightClassViewSet

router = DefaultRouter()
router.register("weight-classes", WeightClassViewSet, basename="weight-class")
router.register("timer-presets", TimerPresetViewSet, basename="timer-preset")
router.register("timer-sessions", TimerSessionViewSet, basename="timer-session")
router.register("matchups", MatchupViewSet, basename="matchup")

urlpatterns = [path("", include(router.urls))]
