from django.urls import path

from .views import CancelSubscriptionView, EnrollView, LeaveAcademyView

urlpatterns = [
    path("enroll/", EnrollView.as_view(), name="membership-enroll"),
    path("<int:academy_id>/leave/", LeaveAcademyView.as_view(), name="membership-leave"),
    path("subscriptions/<int:subscription_id>/cancel/", CancelSubscriptionView.as_view(), name="subscription-cancel"),
]
