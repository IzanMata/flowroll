# techniques/urls.py
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import TechniqueViewSet

router = DefaultRouter()
router.register(r"techniques", TechniqueViewSet)

urlpatterns = [
    path("api/", include(router.urls)),
]
