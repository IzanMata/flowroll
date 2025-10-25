from rest_framework import serializers
from .models import Belt, TechniqueCategory, Technique, TechniqueVariation, TechniqueFlow

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
        fields = ["id", "to_technique", "description", "probability"]

class TechniqueSerializer(serializers.ModelSerializer):
    categories = TechniqueCategorySerializer(many=True, read_only=True)
    variations = TechniqueVariationSerializer(many=True, read_only=True)
    leads_to = TechniqueFlowSerializer(many=True, read_only=True)
    min_belt = BeltSerializer(read_only=True)

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
