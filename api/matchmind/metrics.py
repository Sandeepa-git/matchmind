"""Momentum, xG and key-moment detection over a stream of events."""
from collections import deque

THREAT = {"shot": 3, "goal": 5, "pass_final_third": 1, "dribble": 0.5, "corner": 1, "press": 0.3}


class MatchState:
    def __init__(self, window: int = 40):
        self.window = deque(maxlen=window)
        self.xg = {"home": 0.0, "away": 0.0}
        self.score = {"home": 0, "away": 0}
        self.momentum = 0.0
        self.series: list[dict] = []
        self.moments: list[dict] = []
        self._last_minute = -1

    def update(self, ev: dict) -> dict | None:
        self.window.append(ev)
        if ev["type"] in ("shot", "goal"):
            self.xg[ev["team"]] += ev.get("xg", 0.05)
        prev = self.momentum
        self.momentum = sum(THREAT.get(e["type"], 0) * (1 if e["team"] == "home" else -1) for e in self.window)

        if ev["minute"] != self._last_minute:
            self._last_minute = ev["minute"]
            self.series.append({"minute": ev["minute"], "momentum": round(self.momentum, 1),
                                "xg_home": round(self.xg["home"], 2), "xg_away": round(self.xg["away"], 2)})

        moment = None
        if ev["type"] == "goal":
            self.score[ev["team"]] += 1
            moment = {"kind": "goal", "team": ev["team"], "player": ev["player"]}
        elif ev["type"] == "shot" and ev.get("xg", 0) >= 0.3:
            moment = {"kind": "big_chance", "team": ev["team"], "player": ev["player"]}
        elif prev * self.momentum < 0 and abs(self.momentum) >= 6 and not self._recent("momentum_flip", ev["minute"], 8):
            moment = {"kind": "momentum_flip", "team": "home" if self.momentum > 0 else "away"}

        if moment:
            moment.update({"id": len(self.moments), "minute": ev["minute"], "event_id": ev["id"],
                           "score": dict(self.score), "momentum": round(self.momentum, 1)})
            self.moments.append(moment)
        return moment

    def _recent(self, kind: str, minute: int, gap: int) -> bool:
        return any(m["kind"] == kind and minute - m["minute"] < gap for m in self.moments)

    def summary(self) -> dict:
        return {"score": self.score, "xg": {k: round(v, 2) for k, v in self.xg.items()},
                "moments": len(self.moments)}


def analyse(events: list[dict]) -> MatchState:
    st = MatchState()
    for ev in events:
        st.update(ev)
    return st
