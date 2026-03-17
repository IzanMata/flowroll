---
name: testing
triggers: ["test", "tests", "pytest", "coverage", "unit test", "integration test", "test fixture", "conftest"]
description: "Invoke when running tests, writing tests, debugging test failures, or checking coverage."
---

# Testing

## Commands

```bash
# Activate venv first
source venv/bin/activate

pytest                                        # all tests
pytest <app>/tests/test_<module>.py           # single file
pytest -k "TestClassName"                     # single class or keyword
pytest --cov=. --cov-report=term-missing      # with coverage report
pytest -x                                     # stop on first failure
pytest -v                                     # verbose output
```

## Config

`pytest.ini` / `setup.cfg` — django settings module is set via `DJANGO_SETTINGS_MODULE`.
No `manage.py test` — always use `pytest` directly.

## Global fixtures (`conftest.py`)

Available in every test file without import:

| Fixture | Type | Description |
|---|---|---|
| `belt_white` … `belt_black` | `Belt` | Belt instances for all 5 colours |
| `academy` | `Academy` | Single test academy |
| `make_user` | factory | Creates `User` with unique auto-generated username |
| `make_athlete(belt, stripes, weight, **kwargs)` | factory | `make_user` + `AthleteProfile` |

## Writing tests

- Use `factory-boy` for complex object graphs
- Tests that hit the DB must use `@pytest.mark.django_db`
- **Do not mock the database** — integration tests must hit real DB (mocked tests have masked real migration failures before)
- Service tests: call the service directly, assert DB state
- API tests: use DRF `APIClient`, assert status codes and response shape
- Always scope fixtures to the smallest necessary fixture (function > class > module)

## Coverage targets

- Services: 90%+
- ViewSets: 80%+
- Selectors: covered implicitly by service/API tests
