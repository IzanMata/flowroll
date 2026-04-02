from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (AcademyMemberDetailView, AcademyMemberListView,
                    AcademyViewSet, PublicAcademyListView, PublicAcademyPlansView)

router = DefaultRouter()
router.register(r"", AcademyViewSet, basename="academy")

urlpatterns = [
    path("public/", PublicAcademyListView.as_view(), name="academy-public-list"),
    path("public/<int:pk>/plans/", PublicAcademyPlansView.as_view(), name="academy-public-plans"),
    path("<int:pk>/members/", AcademyMemberListView.as_view(), name="academy-members"),
    path("<int:pk>/members/<int:user_id>/", AcademyMemberDetailView.as_view(), name="academy-member-detail"),
    path("", include(router.urls)),
]
