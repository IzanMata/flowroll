"""
Tests for techniques/services.py: TechniqueService.

Covers:
  - create_technique: creates with categories, saves to DB
  - add_flow: links techniques, detects self-loops, rejects duplicate links
  - add_video: attaches video with optional duration/tags
"""

import pytest

from techniques.models import Technique, TechniqueFlow, TechniqueVideo
from techniques.services import TechniqueService
from factories import TechniqueCategoryFactory, TechniqueFactory


# ─── create_technique ─────────────────────────────────────────────────────────


class TestTechniqueServiceCreate:
    def test_create_technique_persists(self, db):
        t = TechniqueService.create_technique(name="Armbar", difficulty=3)
        assert t.pk is not None
        assert t.name == "Armbar"
        assert t.difficulty == 3

    def test_create_technique_assigns_categories(self, db):
        cat1 = TechniqueCategoryFactory(name="Submissions")
        cat2 = TechniqueCategoryFactory(name="Guard")
        t = TechniqueService.create_technique(name="Triangle", categories=[cat1, cat2])
        assert set(t.categories.all()) == {cat1, cat2}

    def test_create_technique_without_categories(self, db):
        t = TechniqueService.create_technique(name="Shrimping")
        assert t.categories.count() == 0

    def test_create_technique_sets_defaults(self, db):
        t = TechniqueService.create_technique(name="Base technique")
        assert t.min_belt == "white"
        assert t.difficulty == 1

    def test_create_technique_custom_belt(self, db):
        t = TechniqueService.create_technique(name="Berimbolo", min_belt="purple", difficulty=4)
        assert t.min_belt == "purple"

    def test_create_technique_auto_slug(self, db):
        t = TechniqueService.create_technique(name="Guard Pass")
        assert t.slug == "guard-pass"


# ─── add_flow ─────────────────────────────────────────────────────────────────


class TestTechniqueServiceAddFlow:
    def test_add_flow_links_techniques(self, db):
        t1 = TechniqueFactory(name="Closed Guard")
        t2 = TechniqueFactory(name="Armbar from Guard")
        flow = TechniqueService.add_flow(t1, t2, transition_type="chain")
        assert flow.pk is not None
        assert flow.from_technique == t1
        assert flow.to_technique == t2
        assert flow.transition_type == "chain"

    def test_add_flow_different_types(self, db):
        for ttype in ["chain", "counter", "escape", "setup"]:
            t1 = TechniqueFactory()
            t2 = TechniqueFactory()
            flow = TechniqueService.add_flow(t1, t2, transition_type=ttype)
            assert flow.transition_type == ttype

    def test_add_flow_self_loop_raises(self, db):
        t = TechniqueFactory()
        with pytest.raises(ValueError, match="itself"):
            TechniqueService.add_flow(t, t)

    def test_add_flow_duplicate_raises(self, db):
        t1 = TechniqueFactory()
        t2 = TechniqueFactory()
        TechniqueService.add_flow(t1, t2)
        with pytest.raises(ValueError, match="already exists"):
            TechniqueService.add_flow(t1, t2)

    def test_add_flow_reverse_is_allowed(self, db):
        t1 = TechniqueFactory()
        t2 = TechniqueFactory()
        TechniqueService.add_flow(t1, t2)
        # Reverse direction should not raise
        flow_rev = TechniqueService.add_flow(t2, t1)
        assert flow_rev.pk is not None


# ─── add_video ────────────────────────────────────────────────────────────────


class TestTechniqueServiceAddVideo:
    def test_add_video_creates_record(self, db):
        technique = TechniqueFactory()
        video = TechniqueService.add_video(
            technique=technique,
            url="https://youtube.com/watch?v=abc123",
            title="Armbar Tutorial",
        )
        assert video.pk is not None
        assert video.technique == technique
        assert video.title == "Armbar Tutorial"

    def test_add_video_with_duration_and_tags(self, db):
        technique = TechniqueFactory()
        video = TechniqueService.add_video(
            technique=technique,
            url="https://youtube.com/watch?v=xyz",
            duration_seconds=420,
            tags="guard,sweep,gi",
        )
        assert video.duration_seconds == 420
        assert video.tags == "guard,sweep,gi"

    def test_add_video_default_source(self, db):
        technique = TechniqueFactory()
        video = TechniqueService.add_video(technique=technique, url="https://youtube.com/watch?v=1")
        assert video.source == "YouTube"

    def test_add_video_custom_source(self, db):
        technique = TechniqueFactory()
        video = TechniqueService.add_video(
            technique=technique,
            url="https://vimeo.com/123",
            source="Vimeo",
        )
        assert video.source == "Vimeo"

    def test_add_multiple_videos_to_same_technique(self, db):
        technique = TechniqueFactory()
        TechniqueService.add_video(technique=technique, url="https://youtube.com/1")
        TechniqueService.add_video(technique=technique, url="https://youtube.com/2")
        assert TechniqueVideo.objects.filter(technique=technique).count() == 2
