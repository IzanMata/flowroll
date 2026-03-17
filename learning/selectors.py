from django.db.models import QuerySet

from athletes.models import AthleteProfile


def get_journal_for_class(training_class_id: int) -> QuerySet:
    from .models import ClassTechniqueJournal

    return ClassTechniqueJournal.objects.filter(
        training_class_id=training_class_id
    ).select_related("technique")


def get_video_library(academy_id: int, visibility: str = None) -> QuerySet:
    from .models import VideoLibraryItem

    qs = VideoLibraryItem.objects.filter(academy_id=academy_id).select_related(
        "technique"
    )
    if visibility:
        qs = qs.filter(visibility=visibility)
    return qs


def get_sparring_notes_for_athlete(athlete: AthleteProfile) -> QuerySet:
    return athlete.sparring_notes.select_related("training_class")
