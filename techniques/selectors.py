"""
Read-only querysets and filters for the techniques domain.
"""

from __future__ import annotations

from django.db.models import Count, Prefetch, QuerySet

from .models import Technique, TechniqueCategory, TechniqueFlow, TechniqueVideo


def get_techniques(
    search: str = None,
    category_slug: str = None,
    min_belt: str = None,
    difficulty: int = None,
) -> QuerySet:
    """
    Return the full technique library with optional filters.

    All filters are additive (AND). Returns techniques ordered by name.
    """
    qs = (
        Technique.objects.prefetch_related(
            "categories",
            "variations",
            Prefetch("videos", queryset=TechniqueVideo.objects.order_by("id")),
            Prefetch(
                "leads_to",
                queryset=TechniqueFlow.objects.select_related("to_technique"),
            ),
        )
    )

    if search:
        from django.db.models import Q

        qs = qs.filter(
            Q(name__icontains=search)
            | Q(description__icontains=search)
            | Q(categories__name__icontains=search)
            | Q(videos__tags__icontains=search)
        ).distinct()

    if category_slug:
        qs = qs.filter(categories__slug=category_slug)

    if min_belt:
        qs = qs.filter(min_belt=min_belt)

    if difficulty is not None:
        qs = qs.filter(difficulty=difficulty)

    return qs


def get_technique_by_slug(slug: str) -> Technique:
    """Return a single technique by slug with all relations prefetched."""
    return (
        Technique.objects.prefetch_related("categories", "variations", "videos", "leads_to")
        .get(slug=slug)
    )


def get_categories_with_technique_counts() -> QuerySet:
    """Return all categories annotated with the number of associated techniques."""
    return TechniqueCategory.objects.annotate(
        technique_count=Count("techniques", distinct=True)
    ).order_by("name")


def get_flows_for_technique(technique_pk: int) -> QuerySet:
    """Return all outgoing flows from a technique."""
    return TechniqueFlow.objects.filter(from_technique_id=technique_pk).select_related(
        "to_technique"
    )


def get_videos_for_technique(technique_pk: int) -> QuerySet:
    """Return all videos for a technique ordered by id."""
    return TechniqueVideo.objects.filter(technique_id=technique_pk).order_by("id")
