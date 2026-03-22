"""Tests for the Academy model."""

from academies.models import Academy
from factories import AcademyFactory


class TestAcademy:
    def test_create_academy(self, db):
        academy = AcademyFactory(name="Gracie Barra", city="São Paulo")
        assert academy.pk is not None
        assert academy.name == "Gracie Barra"
        assert academy.city == "São Paulo"

    def test_str_is_name(self, db):
        academy = AcademyFactory(name="Alliance HQ", city="")
        assert str(academy) == "Alliance HQ"

    def test_str_includes_city_when_set(self, db):
        academy = AcademyFactory(name="Alliance HQ", city="Atlanta")
        assert str(academy) == "Alliance HQ (Atlanta)"

    def test_created_at_is_set(self, db):
        academy = AcademyFactory()
        assert academy.created_at is not None

    def test_updated_at_is_set(self, db):
        academy = AcademyFactory()
        assert academy.updated_at is not None

    def test_is_active_defaults_to_true(self, db):
        academy = Academy.objects.create(name="New Academy")
        assert academy.is_active is True

    def test_city_can_be_blank(self, db):
        academy = Academy.objects.create(name="No City Academy")
        assert academy.city == ""

    def test_optional_fields_default_to_blank(self, db):
        academy = Academy.objects.create(name="Minimal Academy")
        assert academy.country == ""
        assert academy.description == ""
        assert academy.email == ""
        assert academy.phone == ""
        assert academy.website == ""

    def test_multiple_academies_can_exist(self, db):
        before = Academy.objects.count()
        AcademyFactory.create_batch(5)
        assert Academy.objects.count() == before + 5

    def test_ordering_is_by_name(self, db):
        AcademyFactory(name="Zenith BJJ")
        AcademyFactory(name="Alliance HQ")
        AcademyFactory(name="Marcelo Garcia Academy")
        names = list(Academy.objects.values_list("name", flat=True))
        assert names == sorted(names)
