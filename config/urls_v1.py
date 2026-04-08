"""
URL configuration for API v1.

All tenant-scoped domain endpoints live here. Auth endpoints are
intentionally kept outside versioning (see config/urls.py).
"""

from django.urls import include, path

urlpatterns = [
    path("athletes/", include("athletes.urls")),
    path("techniques/", include("techniques.urls")),
    path("matches/", include("matches.urls")),
    path("academies/", include("academies.urls")),
    path("attendance/", include("attendance.urls")),
    path("tatami/", include("tatami.urls")),
    path("membership/", include("membership.urls")),
    path("community/", include("community.urls")),
    path("learning/", include("learning.urls")),
    path("competitions/", include("competitions.urls")),
    path("stats/", include("stats.urls")),
    path("payments/", include("payments.urls")),
    path("notifications/", include("notifications.urls")),
]
