import os

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (SpectacularAPIView, SpectacularRedocView,
                                   SpectacularSwaggerView)
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
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

_is_production = os.environ.get("DJANGO_ENV") == "production"


@api_view(["GET"])
@permission_classes([AllowAny])
def api_root(request):
    """
    FlowRoll API entry point.

    Returns available API versions and relevant links so that clients
    hitting the root URL get a meaningful response instead of a 404.
    """
    payload = {
        "name": "FlowRoll API",
        "current_version": "v1",
        "status": "ok",
        "endpoints": {
            "auth": request.build_absolute_uri("/api/auth/"),
            "v1": request.build_absolute_uri("/api/v1/"),
        },
    }
    if not _is_production:
        payload["docs"] = request.build_absolute_uri("/api/docs/")

    return Response(payload)


urlpatterns = [
    path("", api_root, name="api-root"),
    path(_admin_url, admin.site.urls),

    # ── Auth (unversioned — stable infrastructure) ───────────────────────────
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
    path("api/auth/", include("accounts.urls")),

    # ── Domain apps (versioned) ───────────────────────────────────────────────
    path("api/v1/", include("config.urls_v1")),
]

# API docs are only exposed outside production to avoid leaking the full
# endpoint surface to potential attackers.
if not _is_production:
    urlpatterns += [
        path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
        path(
            "api/docs/",
            SpectacularSwaggerView.as_view(url_name="schema"),
            name="swagger-ui",
        ),
        path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    ]
