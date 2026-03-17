from rest_framework import serializers

from core.models import Belt

from .models import (Technique, TechniqueCategory, TechniqueFlow,
                     TechniqueVariation)


class BeltSerializer(serializers.ModelSerializer):
    class Meta:
        model = Belt
        fields = ["id", "color", "order"]


class TechniqueCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = TechniqueCategory
        fields = ["id", "name", "description"]


class TechniqueVariationSerializer(serializers.ModelSerializer):
    class Meta:
        model = TechniqueVariation
        fields = ["id", "name", "description"]


class TechniqueFlowSerializer(serializers.ModelSerializer):
    to_technique = serializers.StringRelatedField()

    class Meta:
        model = TechniqueFlow
        fields = ["id", "to_technique", "description"]


class TechniqueSerializer(serializers.ModelSerializer):
    categories = TechniqueCategorySerializer(many=True, read_only=True)
    variations = TechniqueVariationSerializer(many=True, read_only=True)
    leads_to = TechniqueFlowSerializer(many=True, read_only=True)
    # P5 fix: min_belt is a CharField on Technique (not a FK to Belt),
    # so use CharField instead of BeltSerializer to avoid a broken nested lookup.
    min_belt = serializers.CharField(read_only=True)

    class Meta:
        model = Technique
        fields = [
            "id",
            "name",
            "description",
            "difficulty",
            "min_belt",
            "categories",
            "variations",
            "leads_to",
        ]
