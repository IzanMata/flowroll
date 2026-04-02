"""
Business logic for academy management.
"""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db import transaction

from core.models import AcademyMembership

from .models import Academy


class AcademyService:
    @staticmethod
    @transaction.atomic
    def create_academy(user, **academy_data) -> Academy:
        """
        Create a new Academy and assign the creator as its OWNER.

        The OWNER role carries full administrative access to the academy.
        The creator does not need to be a practitioner or professor — ownership
        is a business/administrative role, not a martial-arts one.
        """
        academy = Academy.objects.create(**academy_data)
        AcademyMembership.objects.create(
            user=user,
            academy=academy,
            role=AcademyMembership.Role.OWNER,
            is_active=True,
        )
        return academy


class AcademyMemberService:
    """
    OWNER-only operations for managing academy membership:
      - Add a user (by email) as PROFESSOR or STUDENT
      - Change a member's role
      - Remove a member (deactivate their membership)

    Invariant: an academy must always have at least one active OWNER.
    """

    @staticmethod
    @transaction.atomic
    def add_member(academy: Academy, email: str, role: str) -> AcademyMembership:
        """
        Add the user identified by *email* to *academy* with *role*.

        If the user is already an inactive member, reactivates them.
        If already an active member, updates their role.
        Raises ValueError if the email is not registered.
        """
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            raise ValueError(f"No registered user found with email '{email}'.")

        membership, created = AcademyMembership.objects.get_or_create(
            user=user,
            academy=academy,
            defaults={"role": role, "is_active": True},
        )
        if not created:
            membership.role = role
            membership.is_active = True
            membership.save(update_fields=["role", "is_active"])

        return membership

    @staticmethod
    @transaction.atomic
    def change_role(
        academy: Academy, target_user_id: int, new_role: str, requesting_user: User
    ) -> AcademyMembership:
        """
        Change *target_user*'s role in *academy*.

        Raises ValueError if:
        - The target user is not a member.
        - Demoting the last OWNER would leave the academy without one.
        - The requesting user tries to change their own role.
        """
        if target_user_id == requesting_user.pk:
            raise ValueError("You cannot change your own role.")

        try:
            membership = AcademyMembership.objects.get(
                user_id=target_user_id, academy=academy, is_active=True
            )
        except AcademyMembership.DoesNotExist:
            raise ValueError("That user is not an active member of this academy.")

        if membership.role == AcademyMembership.Role.OWNER and new_role != AcademyMembership.Role.OWNER:
            AcademyMemberService._ensure_another_owner(academy, exclude_user_id=target_user_id)

        membership.role = new_role
        membership.save(update_fields=["role"])
        return membership

    @staticmethod
    @transaction.atomic
    def remove_member(
        academy: Academy, target_user_id: int, requesting_user: User
    ) -> None:
        """
        Deactivate *target_user*'s membership in *academy*.

        Raises ValueError if:
        - The target user is not an active member.
        - Removing them would leave the academy without an OWNER.
        - The requesting user tries to remove themselves (use the leave endpoint).
        """
        if target_user_id == requesting_user.pk:
            raise ValueError("To leave an academy use the leave endpoint.")

        try:
            membership = AcademyMembership.objects.get(
                user_id=target_user_id, academy=academy, is_active=True
            )
        except AcademyMembership.DoesNotExist:
            raise ValueError("That user is not an active member of this academy.")

        if membership.role == AcademyMembership.Role.OWNER:
            AcademyMemberService._ensure_another_owner(academy, exclude_user_id=target_user_id)

        membership.is_active = False
        membership.save(update_fields=["is_active"])

    @staticmethod
    def _ensure_another_owner(academy: Academy, exclude_user_id: int) -> None:
        """Raise ValueError if no other active OWNER exists."""
        other_owner_exists = AcademyMembership.objects.filter(
            academy=academy,
            role=AcademyMembership.Role.OWNER,
            is_active=True,
        ).exclude(user_id=exclude_user_id).exists()

        if not other_owner_exists:
            raise ValueError(
                "Cannot remove the last owner. Assign another owner first."
            )
