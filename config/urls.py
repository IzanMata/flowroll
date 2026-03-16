from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path("admin/", admin.site.urls),
    # Auth
    path("api/auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    # Domain apps
    path("api/athletes/", include("athletes.urls")),
    path("api/techniques/", include("techniques.urls")),
    path("api/matches/", include("matches.urls")),
    path("api/academies/", include("academies.urls")),
    path("api/attendance/", include("attendance.urls")),
    path("api/tatami/", include("tatami.urls")),
    path("api/membership/", include("membership.urls")),
    path("api/community/", include("community.urls")),
    path("api/learning/", include("learning.urls")),
    # Schema
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]
