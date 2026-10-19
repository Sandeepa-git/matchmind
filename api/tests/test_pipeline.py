"""Pipeline tests. Run in mock mode (no Azure keys needed): `cd api && pytest`."""
import asyncio
import os

import pytest

os.environ["MATCHMIND_MOCK"] = "1"      # never call Azure from tests
os.environ["TRANSLATOR_KEY"] = ""

from matchmind import agents, ask  # noqa: E402
from matchmind.data import generate_match  # noqa: E402
from matchmind.metrics import analyse  # noqa: E402


@pytest.fixture(scope="module")
def match():
    return generate_match(seed=7)


def test_generator_is_deterministic_and_synthetic(match):
    assert generate_match(seed=7) == match
    assert match["teams"] == {"home": "Riverside Athletic", "away": "Northgate United"}
    assert [e["id"] for e in match["events"]] == list(range(len(match["events"])))


def test_metrics_score_matches_goal_events(match):
    st = analyse(match["events"])
    goals = [e for e in match["events"] if e["type"] == "goal"]
    assert sum(st.score.values()) == len(goals)
    assert st.score == match["final_score"]
    assert [m["kind"] for m in st.moments].count("goal") == len(goals)
    assert len(st.series) > 90


def test_fact_checker_accepts_true_and_rejects_false(match):
    st = analyse(match["events"])
    c = agents.MatchContext(match=match, moments=st.moments, summary=st.summary())
    s = st.score
    assert agents.check_claims(f"It finished {s['home']}-{s['away']}.", c) == []
    issues = agents.check_claims("A 9-0 rout, decided in the 12th minute.", c)
    assert any("9-0" in i for i in issues) and any("12" in i for i in issues)


def test_workflow_happy_path(match):
    c = asyncio.run(agents.produce(match))
    assert c.verified and c.attempts == 1
    assert [t["agent"] for t in c.trace] == ["Detector", "Analyst", "Narrator", "FactChecker", "Localizer"]
    assert c.final


def test_workflow_recovers_from_hallucination(match):
    c = asyncio.run(agents.produce(match, inject_error=True))
    statuses = [(t["agent"], t["status"]) for t in c.trace]
    assert ("FactChecker", "reject") in statuses
    assert statuses[-2] == ("FactChecker", "pass")
    assert c.verified and c.attempts == 2
    assert "4-0" not in c.final


def test_workflow_falls_back_after_max_retries(match, monkeypatch):
    monkeypatch.setattr(agents, "check_claims", lambda text, c: [] if text.startswith(c.match["teams"]["home"]) else ["forced"])
    c = asyncio.run(agents.produce(match))
    assert any(t["agent"] == "Fallback" for t in c.trace)
    assert c.attempts == agents.MAX_RETRIES + 1 and c.verified


def test_ask_retrieves_by_minute(match):
    r = ask.ask(match, "what happened in minute 62?")
    assert r["citations"][0] == "60-65"
