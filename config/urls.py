import os

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (SpectacularAPIView, SpectacularRedocView,
                                   SpectacularSwaggerView)
from rest_framework_simplejwt.views import (TokenObtainPairView,
                                            TokenRefreshView)

from config.throttles import LoginRateThrottle, TokenRefreshRateThrottle
from core.views import me


# L-4 fix: apply tight per-endpoint throttles to the auth views so brute-force
# login and token-refresh attacks are rate-limited independently.
class ThrottledTokenObtainPairView(TokenObtainPairView):
    throttle_classes = [LoginRateThrottle]


class ThrottledTokenRefreshView(TokenRefreshView):
    throttle_classes = [TokenRefreshRateThrottle]


# Admin panel: served at a secret URL in production to prevent enumeration.
# Set ADMIN_URL env var to a hard-to-guess path (e.g. "s3cr3t-admin/").
# Falls back to the standard "admin/" in development.
_admin_url = os.environ.get("ADMIN_URL", "admin/")

urlpatterns = [
    path(_admin_url, admin.site.urls),

    path(
        "api/auth/token/",
        ThrottledTokenObtainPairView.as_view(),
        name="token_obtain_pair",
    ),
    path(
        "api/auth/token/refresh/",
        ThrottledTokenRefreshView.as_view(),
        name="token_refresh",
    ),
    path("api/auth/me/", me, name="auth_me"),
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
]

# API docs are only exposed outside production to avoid leaking the full
# endpoint surface to potential attackers.
if os.environ.get("DJANGO_ENV") != "production":
    urlpatterns += [
        path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
        path(
            "api/docs/",
            SpectacularSwaggerView.as_view(url_name="schema"),
            name="swagger-ui",
        ),
        path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    ]
