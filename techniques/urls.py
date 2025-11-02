from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (BeltDetailView, BeltsListView, TechniqueCategoryDetailView,
                    TechniqueCategoryListView, TechniqueDetailView,
                    TechniqueListView, TechniqueViewSet)

router = DefaultRouter()
router.register(r"techniques", TechniqueViewSet)

urlpatterns = [
    path("techniques/", TechniqueListView.as_view(), name="technique-list"),
    path(
        "techniques/<int:pk>/", TechniqueDetailView.as_view(), name="technique-detail"
    ),
    path("categories/", TechniqueCategoryListView.as_view(), name="category-list"),
    path(
        "categories/<int:pk>/",
        TechniqueCategoryDetailView.as_view(),
        name="category-detail",
    ),
    path("belts/", BeltsListView.as_view(), name="belts-list"),
    path("belts/<int:pk>", BeltDetailView.as_view(), name="betls-detail"),
]
