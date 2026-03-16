from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import DropInVisitorViewSet, TrainingClassViewSet

router = DefaultRouter()
router.register("classes", TrainingClassViewSet, basename="training-class")
router.register("drop-ins", DropInVisitorViewSet, basename="drop-in-visitor")

urlpatterns = [path("", include(router.urls))]
