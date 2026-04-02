"""
Custom DRF throttle classes for FlowRoll.

L-4 fix: Apply tight rate limits to authentication endpoints so that
brute-force password / token attacks are slowed without affecting normal users.
"""

from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class LoginRateThrottle(AnonRateThrottle):
    """
    Hard limit for login attempts (POST /api/auth/token/).
    10 attempts per minute per IP address.
    """

    scope = "login"


class TokenRefreshRateThrottle(UserRateThrottle):
    """
    Limit token refresh calls (POST /api/auth/token/refresh/).
    20 refreshes per minute per user.
    """

    scope = "token_refresh"


class PasswordResetRateThrottle(AnonRateThrottle):
    """
    Prevent email bombing on the password-reset request endpoint.
    5 requests per minute per IP address.
    """

    scope = "password_reset"
