"""
Custom JWT authentication that checks a Redis JTI blocklist.

When a user logs out, the current access token's JTI is stored in Redis with
a TTL equal to its remaining lifetime.  This class rejects any access token
whose JTI appears in that blocklist, providing immediate logout invalidation
without requiring short token lifetimes.
"""

from django.core.cache import cache
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken


class BlocklistJWTAuthentication(JWTAuthentication):
    """JWTAuthentication subclass that also enforces the Redis JTI blocklist."""

    def get_validated_token(self, raw_token):
        token = super().get_validated_token(raw_token)
        jti = token.get("jti")
        if jti and cache.get(f"revoked_jti:{jti}"):
            raise InvalidToken("Token has been revoked.")
        return token
