from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from academies.models import Academy

from .serializers import EnrollmentSerializer, MembershipPlanSerializer, SubscriptionSerializer
from .models import Subscription
from .services import EnrollmentService, LeaveAcademyService, SubscriptionService


class EnrollView(APIView):
    """
    Join an academy and subscribe to one of its membership plans.

    Creates an AcademyMembership (STUDENT role), an AthleteProfile if the user
    does not have one yet, and a Subscription to the chosen plan.

    Request body:
        academy  — int, ID of the academy to join
        plan     — int, ID of an active MembershipPlan belonging to that academy
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = EnrollmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        academy = serializer.validated_data["academy"]
        plan = serializer.validated_data["plan"]

        try:
            result = EnrollmentService.enroll(
                user=request.user, academy=academy, plan=plan
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        return Response(
            {
                "academy_id": result["membership"].academy_id,
                "role": result["membership"].role,
                "subscription": SubscriptionSerializer(result["subscription"]).data,
            },
            status=201,
        )


class LeaveAcademyView(APIView):
    """
    Leave an academy voluntarily.

    Deactivates the caller's AcademyMembership and cancels any active
    subscriptions at that academy.  OWNER role cannot leave — they must
    transfer ownership first.

    POST /api/membership/{academy_id}/leave/
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, academy_id):
        try:
            academy = Academy.objects.get(pk=academy_id)
        except Academy.DoesNotExist:
            return Response({"detail": "Academy not found."}, status=404)

        try:
            LeaveAcademyService.leave(user=request.user, academy=academy)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        return Response({"detail": "You have left the academy."}, status=200)


class CancelSubscriptionView(APIView):
    """
    Cancel an active subscription.

    POST /api/membership/subscriptions/{id}/cancel/
    Returns 200 with the updated subscription.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, subscription_id):
        try:
            subscription = Subscription.objects.select_related("athlete__user").get(
                pk=subscription_id
            )
        except Subscription.DoesNotExist:
            return Response({"detail": "Subscription not found."}, status=404)

        try:
            updated = SubscriptionService.cancel(subscription, user=request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        return Response(SubscriptionSerializer(updated).data, status=200)
