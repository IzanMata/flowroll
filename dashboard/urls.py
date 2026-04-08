from django.urls import path

from .views import AcademyDashboardView

urlpatterns = [
    path("", AcademyDashboardView.as_view(), name="academy-dashboard"),
]
