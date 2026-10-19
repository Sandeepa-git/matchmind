"""Load match events. Includes a synthetic generator until the official dataset arrives.

Event schema used throughout the project (adapt `normalize` to the real dataset):
    id, minute, second, team ("home"|"away"), player, type, x, y, xg (shots only), outcome
"""
import json
import random
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

TEAMS = {
    "home": {"name": "Riverside Athletic", "players": ["Okafor", "Brennan", "Castillo", "Lindqvist", "Mensah", "Varga", "Ashdown", "Takeda", "Ribeiro", "Kowalski", "Adeyemi"]},
    "away": {"name": "Northgate United", "players": ["Halvorsen", "Duarte", "Nakamura", "Fitzgerald", "Osei", "Petrov", "Lambert", "Moreau", "Quinn", "Abara", "Sorensen"]},
}

EVENT_TYPES = ["pass", "pass", "pass", "pass", "pass_final_third", "dribble", "tackle", "interception", "press", "shot", "corner", "foul"]


def generate_match(seed: int = 7) -> dict:
    rng = random.Random(seed)
    events, eid = [], 0
    score = {"home": 0, "away": 0}
    for minute in range(0, 95):
        # momentum phases: home dominant early, away surge 55-70, home late
        home_bias = 0.6 if minute < 50 else 0.35 if minute < 72 else 0.58
        for _ in range(rng.randint(8, 14)):
            team = "home" if rng.random() < home_bias else "away"
            etype = rng.choice(EVENT_TYPES)
            ev = {
                "id": eid, "minute": minute, "second": rng.randint(0, 59), "team": team,
                "player": rng.choice(TEAMS[team]["players"][1:]), "type": etype,
                "x": round(rng.uniform(0, 100), 1), "y": round(rng.uniform(0, 100), 1), "outcome": "success",
            }
            if etype == "shot":
                ev["x"] = round(rng.uniform(78, 99), 1)
                ev["xg"] = round(min(0.85, rng.expovariate(9) + 0.02), 2)
                if rng.random() < ev["xg"] * 0.9:
                    ev["type"] = "goal"
                    score[team] += 1
                else:
                    ev["outcome"] = rng.choice(["saved", "off_target", "blocked"])
            events.append(ev)
            eid += 1
    events.sort(key=lambda e: (e["minute"], e["second"]))
    for i, e in enumerate(events):
        e["id"] = i
    return {"match_id": f"synthetic-{seed}", "teams": {k: v["name"] for k, v in TEAMS.items()},
            "final_score": score, "events": events}


def normalize(raw: dict) -> dict:
    """Map the official hackathon dataset to our schema. Edit once you see the real format."""
    return raw


def load_match(name: str = "sample_match.json") -> dict:
    path = DATA_DIR / name
    if not path.exists():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(generate_match(), indent=1), encoding="utf-8")
    return normalize(json.loads(path.read_text(encoding="utf-8")))
