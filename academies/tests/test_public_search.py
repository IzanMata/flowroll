"""
Tests for GET /api/academies/public/ — search and filter
"""

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from factories import AcademyFactory

URL = "/api/academies/public/"


@pytest.fixture
def academies(db):
    return [
        AcademyFactory(name="Alliance Madrid", city="Madrid", country="Spain", is_active=True),
        AcademyFactory(name="Gracie Barcelona", city="Barcelona", country="Spain", is_active=True),
        AcademyFactory(name="Atos New York", city="New York", country="USA", is_active=True),
        AcademyFactory(name="Closed Gym", city="Madrid", country="Spain", is_active=False),
    ]


@pytest.fixture
def client():
    return APIClient()


class TestPublicAcademyList:
    def test_returns_only_active_academies(self, client, academies):
        response = client.get(URL)
        assert response.status_code == status.HTTP_200_OK
        names = [a["name"] for a in response.data["results"]]
        assert "Closed Gym" not in names
        assert len(names) == 3

    def test_search_by_name(self, client, academies):
        response = client.get(URL, {"search": "Alliance"})
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        assert len(results) == 1
        assert results[0]["name"] == "Alliance Madrid"

    def test_search_is_case_insensitive(self, client, academies):
        response = client.get(URL, {"search": "alliance"})
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

    def test_search_by_city(self, client, academies):
        response = client.get(URL, {"search": "Barcelona"})
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["city"] == "Barcelona"

    def test_filter_by_country(self, client, academies):
        response = client.get(URL, {"country": "Spain"})
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        assert len(results) == 2
        assert all(a["country"] == "Spain" for a in results)

    def test_filter_by_city_partial(self, client, academies):
        response = client.get(URL, {"city": "new"})
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["city"] == "New York"

    def test_filter_country_and_search_combined(self, client, academies):
        response = client.get(URL, {"country": "Spain", "search": "Gracie"})
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["name"] == "Gracie Barcelona"

    def test_no_match_returns_empty_list(self, client, academies):
        response = client.get(URL, {"search": "zzz_nonexistent"})
        assert response.data["results"] == []

    def test_response_is_paginated(self, client, db):
        AcademyFactory.create_batch(25, is_active=True)
        response = client.get(URL)
        assert "results" in response.data
        assert "count" in response.data
        assert len(response.data["results"]) <= 20

    def test_no_auth_required(self, db):
        AcademyFactory(is_active=True)
        response = APIClient().get(URL)
        assert response.status_code == status.HTTP_200_OK
