from django.contrib import admin

from .models import (Belt, Technique, TechniqueCategory, TechniqueFlow,
                     TechniqueVariation)


@admin.register(Belt)
class BeltAdmin(admin.ModelAdmin):
    list_display = ("color", "order")
    ordering = ("order",)


@admin.register(TechniqueCategory)
class TechniqueCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "description")
    search_fields = ("name", "description")


@admin.register(Technique)
class TechniqueAdmin(admin.ModelAdmin):
    list_display = ("name", "difficulty", "min_belt")
    list_filter = ("difficulty", "min_belt")
    filter_horizontal = ("categories",)


@admin.register(TechniqueVariation)
class TechniqueVariationAdmin(admin.ModelAdmin):
    list_display = ("name", "technique")
    search_fields = ("name", "description")


@admin.register(TechniqueFlow)
class TechniqueFlowAdmin(admin.ModelAdmin):
    list_display = ("from_technique", "to_technique", "probability")
    search_fields = ("from_technique__name", "to_technique__name", "description")
    list_filter = ("from_technique", "to_technique")
