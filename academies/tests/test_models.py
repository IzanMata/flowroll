"""Tests for the Academy model."""
import pytest

from academies.models import Academy
from factories import AcademyFactory


class TestAcademy:
    def test_create_academy(self, db):
        academy = AcademyFactory(name="Gracie Barra", city="São Paulo")
        assert academy.pk is not None
        assert academy.name == "Gracie Barra"
        assert academy.city == "São Paulo"

    def test_str_is_name(self, db):
        academy = AcademyFactory(name="Alliance HQ")
        assert str(academy) == "Alliance HQ"

    def test_created_at_is_set(self, db):
        academy = AcademyFactory()
        assert academy.created_at is not None

    def test_city_can_be_blank(self, db):
        academy = Academy.objects.create(name="No City Academy")
        assert academy.city == ""

    def test_multiple_academies_can_exist(self, db):
        AcademyFactory.create_batch(5)
        assert Academy.objects.count() == 5
