"""
Business logic for technique management.
"""

from __future__ import annotations

from django.db import transaction

from .models import Technique, TechniqueCategory, TechniqueFlow, TechniqueVideo


class TechniqueService:
    """Handles creation and linkage of techniques and their metadata."""

    @staticmethod
    @transaction.atomic
    def create_technique(
        name: str,
        description: str = "",
        difficulty: int = 1,
        min_belt: str = "white",
        categories: list = None,
        **kwargs,
    ) -> Technique:
        """Create a technique and assign categories in a single transaction."""
        technique = Technique.objects.create(
            name=name,
            description=description,
            difficulty=difficulty,
            min_belt=min_belt,
            **kwargs,
        )
        if categories:
            technique.categories.set(categories)
        return technique

    @staticmethod
    @transaction.atomic
    def add_flow(
        from_technique: Technique,
        to_technique: Technique,
        transition_type: str = TechniqueFlow.TransitionTypes.CHAIN,
        description: str = "",
    ) -> TechniqueFlow:
        """
        Link two techniques via a directional flow (chain, counter, escape, setup).

        Raises ValueError if the techniques are the same or the link already exists.
        """
        if from_technique.pk == to_technique.pk:
            raise ValueError("A technique cannot flow to itself.")
        flow, created = TechniqueFlow.objects.get_or_create(
            from_technique=from_technique,
            to_technique=to_technique,
            defaults={"transition_type": transition_type, "description": description},
        )
        if not created:
            raise ValueError(
                f"A flow from '{from_technique}' to '{to_technique}' already exists."
            )
        return flow

    @staticmethod
    @transaction.atomic
    def add_video(
        technique: Technique,
        url: str,
        title: str = "",
        source: str = "YouTube",
        duration_seconds: int = None,
        tags: str = "",
    ) -> TechniqueVideo:
        """Attach a video to a technique."""
        return TechniqueVideo.objects.create(
            technique=technique,
            url=url,
            title=title,
            source=source,
            duration_seconds=duration_seconds,
            tags=tags,
        )
