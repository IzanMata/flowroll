from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (TechniqueCategoryListView, TechniqueDetailView,
                    TechniqueListView, TechniqueViewSet)

router = DefaultRouter()
router.register(r"techniques", TechniqueViewSet)

urlpatterns = [
    path("techniques/", TechniqueListView.as_view(), name="technique-list"),
    path(
        "techniques/<int:pk>/", TechniqueDetailView.as_view(), name="technique-detail"
    ),
    path("categories/", TechniqueCategoryListView.as_view(), name="category-list"),
]
