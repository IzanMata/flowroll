from django.contrib import admin

from .models import ClassTechniqueJournal, SparringNote, VideoLibraryItem


@admin.register(ClassTechniqueJournal)
class ClassTechniqueJournalAdmin(admin.ModelAdmin):
    list_display = ["technique", "training_class", "created_at"]


@admin.register(VideoLibraryItem)
class VideoLibraryItemAdmin(admin.ModelAdmin):
    list_display = ["title", "academy", "source", "visibility", "technique"]
    list_filter = ["source", "visibility"]


@admin.register(SparringNote)
class SparringNoteAdmin(admin.ModelAdmin):
    list_display = ["athlete", "session_date", "opponent_name", "performance_rating"]
    list_filter = ["performance_rating"]
