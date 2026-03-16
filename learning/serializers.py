from rest_framework import serializers

from .models import ClassTechniqueJournal, SparringNote, VideoLibraryItem


class ClassTechniqueJournalSerializer(serializers.ModelSerializer):
    technique_name = serializers.CharField(source="technique.name", read_only=True)

    class Meta:
        model = ClassTechniqueJournal
        fields = [
            "id", "training_class", "technique", "technique_name",
            "professor_notes", "created_at",
        ]
        read_only_fields = ["created_at"]


class VideoLibraryItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = VideoLibraryItem
        fields = [
            "id", "academy", "title", "url", "source", "visibility",
            "technique", "belt_level", "description", "created_at",
        ]
        read_only_fields = ["created_at"]


class SparringNoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = SparringNote
        fields = [
            "id", "athlete", "training_class", "opponent_name", "session_date",
            "submission_log", "performance_rating", "notes", "created_at",
        ]
        read_only_fields = ["created_at"]
