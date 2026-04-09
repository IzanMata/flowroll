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


class ThrottledTokenObtainPairView(TokenObtainPairView):
    """
    Email/password login with 2FA support and session tracking.

    - If the user has an active TOTP device: returns
      {"requires_2fa": true, "partial_token": "..."}  (HTTP 200, no JWT yet).
      The client then POSTs to /api/auth/2fa/challenge/ to complete login.
    - Otherwise: returns the normal JWT pair and creates a session record.
    """

    throttle_classes = [LoginRateThrottle]

    def post(self, request, *args, **kwargs):
        from accounts.services import TwoFactorService, SessionService, LoginEventService
        from rest_framework_simplejwt.tokens import RefreshToken as RT

        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except Exception:
            # Log failed attempt (user may not be identifiable)
            from django.contrib.auth.models import User
            try:
                u = User.objects.get(username=request.data.get("username", ""))
                LoginEventService.log(user=u, method="email", request=request, success=False)
            except User.DoesNotExist:
                LoginEventService.log(user=None, method="email", request=request, success=False)
            raise

        user = serializer.user
        device = getattr(user, "totp_device", None)

        if device and device.is_active:
            partial_token = TwoFactorService.issue_partial_token(user)
            return Response({"requires_2fa": True, "partial_token": partial_token}, status=200)

        # No 2FA — issue tokens and create session
        refresh = RT.for_user(user)
        session = SessionService.create(
            user=user, jti=str(refresh["jti"]), request=request, login_method="email"
        )
        refresh["session_id"] = session.pk
        refresh.access_token["session_id"] = session.pk
        LoginEventService.log(user=user, method="email", request=request, success=True)

        return Response({"access": str(refresh.access_token), "refresh": str(refresh)}, status=200)


class ThrottledTokenRefreshView(TokenRefreshView):
    """
    Token refresh with session JTI rotation and token-family reuse detection.

    On successful rotation the session record is updated with the new JTI.
    If the incoming refresh token is already blacklisted (reuse detected),
    all sessions for that user are revoked as a theft response.
    """

    throttle_classes = [TokenRefreshRateThrottle]

    def post(self, request, *args, **kwargs):
        import jwt as pyjwt
        from accounts.services import SessionService
        from rest_framework_simplejwt.exceptions import TokenError

        old_refresh_raw = request.data.get("refresh", "")

        # Decode without verification to read old JTI (verification happens inside super())
        try:
            old_claims = pyjwt.decode(old_refresh_raw, options={"verify_signature": False})
            old_jti = old_claims.get("jti")
        except Exception:
            old_jti = None

        try:
            response = super().post(request, *args, **kwargs)
        except TokenError as exc:
            # Blacklisted token reused → possible token theft; nuke all sessions
            if old_jti and "blacklisted" in str(exc).lower():
                try:
                    from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
                    outstanding = OutstandingToken.objects.filter(jti=old_jti).first()
                    if outstanding:
                        SessionService.revoke_all(outstanding.user)
                except Exception:
                    pass
            raise

        # Rotation succeeded — update session with new JTI
        if old_jti and response.status_code == 200:
            new_refresh_raw = response.data.get("refresh", "")
            try:
                new_claims = pyjwt.decode(new_refresh_raw, options={"verify_signature": False})
                new_jti = new_claims.get("jti")
                if new_jti:
                    SessionService.rotate_jti(old_jti, new_jti)
            except Exception:
                pass

        return response


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
