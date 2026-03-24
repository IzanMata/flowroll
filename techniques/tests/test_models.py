"""Tests for Technique, TechniqueCategory, TechniqueFlow, TechniqueVariation."""

import pytest
from django.db import IntegrityError

from factories import (TechniqueCategoryFactory, TechniqueFactory,
                       TechniqueFlowFactory)
from techniques.models import Technique, TechniqueFlow, TechniqueVariation


class TestTechniqueCategory:
    def test_create_category(self, db):
        cat = TechniqueCategoryFactory(name="Guard Passes")
        assert cat.pk is not None
        assert cat.name == "Guard Passes"

    def test_slug_auto_generated(self, db):
        cat = TechniqueCategoryFactory(name="Guard Passes")
        assert cat.slug == "guard-passes"

    def test_name_is_unique(self, db):
        TechniqueCategoryFactory(name="Test Category")
        with pytest.raises(IntegrityError):
            TechniqueCategoryFactory(name="Test Category")

    def test_str_is_name(self, db):
        cat = TechniqueCategoryFactory(name="Test Takedowns")
        assert str(cat) == "Test Takedowns"


class TestTechnique:
    def test_create_technique(self, db):
        t = TechniqueFactory(name="Triangle Choke")
        assert t.pk is not None
        assert t.name == "Triangle Choke"

    def test_slug_auto_generated(self, db):
        t = TechniqueFactory(name="Rear Naked Choke")
        assert t.slug == "rear-naked-choke"

    def test_name_is_unique(self, db):
        TechniqueFactory(name="Armbar")
        with pytest.raises(IntegrityError):
            TechniqueFactory(name="Armbar")

    def test_default_min_belt_is_white(self, db):
        t = TechniqueFactory()
        assert t.min_belt == "white"

    def test_categories_many_to_many(self, db):
        t = TechniqueFactory(categories=[])  # Disable auto-generated categories
        t.categories.clear()  # Ensure no pre-existing categories
        c1 = TechniqueCategoryFactory(name="Test Category A")
        c2 = TechniqueCategoryFactory(name="Test Category B")
        t.categories.add(c1, c2)
        assert t.categories.count() == 2

    def test_str_is_name(self, db):
        t = TechniqueFactory(name="Omoplata")
        assert str(t) == "Omoplata"

    def test_difficulty_default_one(self, db):
        t = TechniqueFactory()
        assert t.difficulty == 1


class TestTechniqueFlow:
    def test_create_flow(self, db):
        t1 = TechniqueFactory()
        t2 = TechniqueFactory()
        flow = TechniqueFlow.objects.create(
            from_technique=t1, to_technique=t2, transition_type="chain"
        )
        assert flow.pk is not None

    def test_from_leads_to_accessor(self, db):
        t1 = TechniqueFactory()
        t2 = TechniqueFactory()
        TechniqueFlow.objects.create(
            from_technique=t1, to_technique=t2, transition_type="chain"
        )
        assert t2 in Technique.objects.filter(comes_from__from_technique=t1)

    def test_unique_from_to_pair(self, db):
        flow = TechniqueFlowFactory()
        with pytest.raises(IntegrityError):
            TechniqueFlow.objects.create(
                from_technique=flow.from_technique,
                to_technique=flow.to_technique,
                transition_type="counter",
            )

    def test_str_shows_arrow(self, db):
        flow = TechniqueFlowFactory()
        assert "→" in str(flow)

    def test_transition_types(self, db):
        valid = {"chain", "counter", "escape", "setup"}
        choices = {c for c, _ in TechniqueFlow.TransitionTypes.choices}
        assert choices == valid


class TestTechniqueVariation:
    def test_create_variation(self, db):
        t = TechniqueFactory()
        v = TechniqueVariation.objects.create(
            technique=t, name="Closed Guard Variation"
        )
        assert v.pk is not None

    def test_unique_per_technique(self, db):
        t = TechniqueFactory()
        TechniqueVariation.objects.create(technique=t, name="Variation A")
        with pytest.raises(IntegrityError):
            TechniqueVariation.objects.create(technique=t, name="Variation A")

    def test_str_shows_parent_technique(self, db):
        t = TechniqueFactory(name="Armbar")
        v = TechniqueVariation.objects.create(technique=t, name="From Guard")
        assert "Armbar" in str(v)
        assert "From Guard" in str(v)
