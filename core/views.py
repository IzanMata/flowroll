from allauth.account.models import EmailAddress
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import AcademyMembership


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    """Return the authenticated user's profile including academy memberships."""
    user = request.user
    memberships = (
        AcademyMembership.objects.filter(user=user, is_active=True)
        .select_related("academy")
        .order_by("academy__name")
    )
    email_verified = EmailAddress.objects.filter(
        user=user, email=user.email, verified=True
    ).exists()

    return Response(
        {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email_verified": email_verified,
            "academies": [
                {
                    "academy_id": m.academy_id,
                    "academy_name": m.academy.name,
                    "role": m.role,
                }
                for m in memberships
            ],
        }
    )
