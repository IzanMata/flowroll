"""
FlowRoll API Performance Tests
================================
Run with:
    cd /home/user/flowroll
    python manage.py setup_perf_data        # once — creates test accounts
    locust -f performance_tests/locustfile.py --headless \
           -u 20 -r 5 -t 60s --host http://127.0.0.1:8001

Flags:
    -u  total virtual users
    -r  spawn rate (users/sec)
    -t  test duration
    --headless  no web UI (HTML report saved to performance_tests/report.html)

Web UI:
    locust -f performance_tests/locustfile.py --host http://127.0.0.1:8001
    then open http://localhost:8089
"""

import random

from locust import HttpUser, between, events, tag, task

# ── Test accounts created by `python manage.py setup_perf_data` ──────────────
OWNER_CREDS = {"username": "perf_owner", "password": "PerfTest123!"}
PROF_CREDS = {"username": "perf_professor", "password": "PerfTest123!"}
STUDENT_CREDS = {"username": "perf_student", "password": "PerfTest123!"}

# Populated at runtime after the first login
_STATE = {
    "academy_id": None,
    "athlete_ids": [],
    "technique_ids": [],
    "class_ids": [],
    "matchup_ids": [],
    "timer_preset_ids": [],
    "weight_class_ids": [],
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _login(client, credentials: dict) -> str | None:
    """Return a Bearer token or None on failure."""
    with client.post(
        "/api/auth/token/",
        json=credentials,
        catch_response=True,
        name="POST /api/auth/token/",
    ) as resp:
        if resp.status_code == 200:
            return resp.json().get("access")
        resp.failure(f"Login failed: {resp.status_code} {resp.text[:200]}")
        return None


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _pick(lst: list):
    return random.choice(lst) if lst else None


# ── Shared state seeder (runs once before any user starts) ────────────────────

@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Pre-fetch IDs needed by tasks so individual users don't have to."""
    import requests

    base = environment.host.rstrip("/")
    token = None

    # Login as professor to read data
    r = requests.post(f"{base}/api/auth/token/", json=PROF_CREDS, timeout=10)
    if r.status_code != 200:
        print(f"[setup] WARNING: could not log in as professor: {r.text[:200]}")
        return

    token = r.json()["access"]
    hdrs = _auth_headers(token)

    # Academy — first result (perf academy)
    r = requests.get(f"{base}/api/academies/", headers=hdrs, timeout=10)
    if r.status_code == 200 and r.json().get("results"):
        for acad in r.json()["results"]:
            if "Perf" in acad["name"]:
                _STATE["academy_id"] = acad["id"]
                break
        if not _STATE["academy_id"]:
            _STATE["academy_id"] = r.json()["results"][0]["id"]

    academy_id = _STATE["academy_id"]
    if not academy_id:
        print("[setup] WARNING: no academy found — scoped endpoints may fail")
        return

    aq = f"?academy={academy_id}"

    # Athletes
    r = requests.get(f"{base}/api/athletes/{aq}", headers=hdrs, timeout=10)
    if r.status_code == 200:
        _STATE["athlete_ids"] = [a["id"] for a in r.json().get("results", [])]

    # Techniques
    r = requests.get(f"{base}/api/techniques/techniques/", headers=hdrs, timeout=10)
    if r.status_code == 200:
        _STATE["technique_ids"] = [t["id"] for t in r.json().get("results", [])]

    # Training classes
    r = requests.get(f"{base}/api/attendance/classes/{aq}", headers=hdrs, timeout=10)
    if r.status_code == 200:
        _STATE["class_ids"] = [c["id"] for c in r.json().get("results", [])]

    # Matchups
    r = requests.get(f"{base}/api/tatami/matchups/{aq}", headers=hdrs, timeout=10)
    if r.status_code == 200:
        _STATE["matchup_ids"] = [m["id"] for m in r.json().get("results", [])]

    # Timer presets
    r = requests.get(f"{base}/api/tatami/timer-presets/{aq}", headers=hdrs, timeout=10)
    if r.status_code == 200:
        _STATE["timer_preset_ids"] = [p["id"] for p in r.json().get("results", [])]

    # Weight classes
    r = requests.get(f"{base}/api/tatami/weight-classes/", headers=hdrs, timeout=10)
    if r.status_code == 200:
        _STATE["weight_class_ids"] = [w["id"] for w in r.json().get("results", [])]

    print(
        f"[setup] academy={academy_id} | "
        f"athletes={len(_STATE['athlete_ids'])} | "
        f"techniques={len(_STATE['technique_ids'])} | "
        f"classes={len(_STATE['class_ids'])} | "
        f"matchups={len(_STATE['matchup_ids'])}"
    )


# ── Base user ─────────────────────────────────────────────────────────────────

class FlowRollBaseUser(HttpUser):
    abstract = True
    wait_time = between(0.3, 1.0)

    _credentials: dict = {}
    _token: str | None = None

    def on_start(self):
        self._token = _login(self.client, self._credentials)

    @property
    def _hdrs(self) -> dict:
        return _auth_headers(self._token) if self._token else {}

    @property
    def _aq(self) -> str:
        return f"?academy={_STATE['academy_id']}" if _STATE["academy_id"] else ""

    def _get(self, url: str, name: str = None, **kwargs):
        with self.client.get(
            url,
            headers=self._hdrs,
            catch_response=True,
            name=name or url,
            **kwargs,
        ) as resp:
            if resp.status_code not in (200, 404):
                resp.failure(f"HTTP {resp.status_code}: {resp.text[:300]}")
            return resp

    def _post(self, url: str, payload: dict, name: str = None, expected: int = 201):
        with self.client.post(
            url,
            json=payload,
            headers=self._hdrs,
            catch_response=True,
            name=name or url,
        ) as resp:
            if resp.status_code != expected:
                resp.failure(f"HTTP {resp.status_code}: {resp.text[:300]}")
            return resp


# ── Student user (read-heavy) ─────────────────────────────────────────────────

class StudentUser(FlowRollBaseUser):
    """Simulates a student browsing the academy — pure read workload."""
    weight = 60  # 60 % of virtual users
    _credentials = STUDENT_CREDS

    # ── Academies ─────────────────────────────────────────────────────────────

    @tag("academies")
    @task(3)
    def list_academies(self):
        self._get("/api/academies/", name="GET /api/academies/ [list]")

    @tag("academies")
    @task(2)
    def get_academy(self):
        aid = _STATE["academy_id"]
        if aid:
            self._get(f"/api/academies/{aid}/", name="GET /api/academies/:id/")

    # ── Athletes ──────────────────────────────────────────────────────────────

    @tag("athletes")
    @task(5)
    def list_athletes(self):
        self._get(f"/api/athletes/{self._aq}", name="GET /api/athletes/ [list]")

    @tag("athletes")
    @task(2)
    def get_athlete(self):
        aid = _pick(_STATE["athlete_ids"])
        if aid and _STATE["academy_id"]:
            self._get(
                f"/api/athletes/{aid}/{self._aq}",
                name="GET /api/athletes/:id/",
            )

    # ── Techniques ────────────────────────────────────────────────────────────

    @tag("techniques")
    @task(6)
    def list_techniques(self):
        self._get("/api/techniques/techniques/", name="GET /api/techniques/ [list]")

    @tag("techniques")
    @task(3)
    def get_technique(self):
        tid = _pick(_STATE["technique_ids"])
        if tid:
            self._get(
                f"/api/techniques/techniques/{tid}/",
                name="GET /api/techniques/:id/",
            )

    @tag("techniques")
    @task(2)
    def list_categories(self):
        self._get("/api/techniques/categories/", name="GET /api/techniques/categories/")

    @tag("techniques")
    @task(2)
    def list_belts(self):
        self._get("/api/techniques/belts/", name="GET /api/techniques/belts/")

    # ── Attendance ────────────────────────────────────────────────────────────

    @tag("attendance")
    @task(4)
    def list_classes(self):
        self._get(
            f"/api/attendance/classes/{self._aq}",
            name="GET /api/attendance/classes/ [list]",
        )

    @tag("attendance")
    @task(2)
    def get_class(self):
        cid = _pick(_STATE["class_ids"])
        if cid and _STATE["academy_id"]:
            self._get(
                f"/api/attendance/classes/{cid}/{self._aq}",
                name="GET /api/attendance/classes/:id/",
            )

    # ── Tatami ────────────────────────────────────────────────────────────────

    @tag("tatami")
    @task(3)
    def list_weight_classes(self):
        self._get("/api/tatami/weight-classes/", name="GET /api/tatami/weight-classes/")

    @tag("tatami")
    @task(3)
    def list_matchups(self):
        self._get(
            f"/api/tatami/matchups/{self._aq}",
            name="GET /api/tatami/matchups/ [list]",
        )

    @tag("tatami")
    @task(2)
    def get_matchup(self):
        mid = _pick(_STATE["matchup_ids"])
        if mid and _STATE["academy_id"]:
            self._get(
                f"/api/tatami/matchups/{mid}/{self._aq}",
                name="GET /api/tatami/matchups/:id/",
            )

    # ── Matches ───────────────────────────────────────────────────────────────

    @tag("matches")
    @task(2)
    def list_matches(self):
        self._get(
            f"/api/matches/{self._aq}",
            name="GET /api/matches/ [list]",
        )

    # ── Auth ──────────────────────────────────────────────────────────────────

    @tag("auth")
    @task(1)
    def token_refresh(self):
        """Simulate periodic token refresh."""
        self._token = _login(self.client, self._credentials)


# ── Professor user (read + write) ─────────────────────────────────────────────

class ProfessorUser(FlowRollBaseUser):
    """Simulates a professor — reads + creates content."""
    weight = 30
    _credentials = PROF_CREDS

    @tag("attendance")
    @task(3)
    def list_drop_ins(self):
        self._get(
            f"/api/attendance/drop-ins/{self._aq}",
            name="GET /api/attendance/drop-ins/ [list]",
        )

    @tag("attendance")
    @task(2)
    def list_classes(self):
        self._get(
            f"/api/attendance/classes/{self._aq}",
            name="GET /api/attendance/classes/ [list] (prof)",
        )

    @tag("tatami")
    @task(3)
    def list_timer_presets(self):
        self._get(
            f"/api/tatami/timer-presets/{self._aq}",
            name="GET /api/tatami/timer-presets/ [list]",
        )

    @tag("tatami")
    @task(2)
    def list_timer_sessions(self):
        self._get(
            f"/api/tatami/timer-sessions/{self._aq}",
            name="GET /api/tatami/timer-sessions/ [list]",
        )

    @tag("tatami", "write")
    @task(1)
    def create_timer_preset(self):
        if not _STATE["academy_id"]:
            return
        from django.utils.crypto import get_random_string

        self._post(
            f"/api/tatami/timer-presets/{self._aq}",
            payload={
                "academy": _STATE["academy_id"],
                "name": f"Load Test Preset {get_random_string(6)}",
                "format": "CUSTOM",
                "round_duration_seconds": 300,
                "rest_duration_seconds": 30,
                "overtime_seconds": 0,
                "rounds": 3,
            },
            name="POST /api/tatami/timer-presets/",
        )

    @tag("athletes")
    @task(3)
    def list_athletes(self):
        self._get(f"/api/athletes/{self._aq}", name="GET /api/athletes/ [list] (prof)")

    @tag("tatami", "write")
    @task(1)
    def pair_athletes(self):
        if not _STATE["academy_id"] or len(_STATE["athlete_ids"]) < 2:
            return
        ids = random.sample(_STATE["athlete_ids"], min(4, len(_STATE["athlete_ids"])))
        self._post(
            f"/api/tatami/matchups/pair_athletes/{self._aq}",
            payload={"athlete_ids": ids, "match_format": "TOURNAMENT"},
            name="POST /api/tatami/matchups/pair_athletes/",
        )


# ── Owner user (10 %) ─────────────────────────────────────────────────────────

class OwnerUser(FlowRollBaseUser):
    """Simulates an academy owner — admin reads."""
    weight = 10
    _credentials = OWNER_CREDS

    @tag("academies")
    @task(3)
    def get_my_academy(self):
        aid = _STATE["academy_id"]
        if aid:
            self._get(f"/api/academies/{aid}/", name="GET /api/academies/:id/ (owner)")

    @tag("athletes")
    @task(4)
    def list_all_athletes(self):
        self._get(f"/api/athletes/{self._aq}", name="GET /api/athletes/ [list] (owner)")

    @tag("attendance")
    @task(3)
    def list_drop_ins(self):
        self._get(
            f"/api/attendance/drop-ins/{self._aq}",
            name="GET /api/attendance/drop-ins/ [list] (owner)",
        )
