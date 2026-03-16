from __future__ import annotations

from django.db import transaction

from .models import ClassTechniqueJournal, SparringNote, VideoLibraryItem


class TechniqueJournalService:
    @staticmethod
    @transaction.atomic
    def log_technique(training_class, technique, professor_notes: str = "") -> ClassTechniqueJournal:
        journal, created = ClassTechniqueJournal.objects.get_or_create(
            training_class=training_class,
            technique=technique,
            defaults={"professor_notes": professor_notes},
        )
        if not created and professor_notes:
            journal.professor_notes = professor_notes
            journal.save(update_fields=["professor_notes"])
        return journal


class SparringNoteService:
    @staticmethod
    def create_note(athlete, **kwargs) -> SparringNote:
        return SparringNote.objects.create(athlete=athlete, **kwargs)
