"""Explainable 'Why?' cards: a tool-using agent that must cite event evidence."""
import json
from collections import Counter

from . import llm

SYSTEM = """You are a Premier League tactical analyst. Explain WHY a key moment happened.
Call tools to gather evidence before answering. Only state facts supported by tool output.
Return JSON: {"headline": str, "explanation": str (2-4 sentences), "tactical_pattern": str,
"evidence": [event ids], "confidence": "high"|"medium"|"low"}"""


class Tools:
    def __init__(self, match: dict):
        self.match = match
        self.events = match["events"]

    def events_before(self, minute: int, seconds: int = 90):
        t = minute * 60 + 59
        return [e for e in self.events if t - seconds <= e["minute"] * 60 + e["second"] <= t]

    def team_stats(self, team: str, from_minute: int = 0, to_minute: int = 95):
        evs = [e for e in self.events if e["team"] == team and from_minute <= e["minute"] <= to_minute]
        c = Counter(e["type"] for e in evs)
        return {"team": self.match["teams"][team], "events": len(evs), **c,
                "xg": round(sum(e.get("xg", 0) for e in evs), 2)}

    def player_involvement(self, player: str, to_minute: int = 95):
        evs = [e for e in self.events if e["player"] == player and e["minute"] <= to_minute]
        return {"player": player, "actions": len(evs), **Counter(e["type"] for e in evs)}


TOOL_SPECS = [
    {"type": "function", "function": {"name": "events_before", "description": "Raw events in the N seconds before (and including) a minute",
     "parameters": {"type": "object", "properties": {"minute": {"type": "integer"}, "seconds": {"type": "integer"}}, "required": ["minute"]}}},
    {"type": "function", "function": {"name": "team_stats", "description": "Aggregated team stats in a minute range. team is 'home' or 'away'",
     "parameters": {"type": "object", "properties": {"team": {"type": "string", "enum": ["home", "away"]},
                    "from_minute": {"type": "integer"}, "to_minute": {"type": "integer"}}, "required": ["team"]}}},
    {"type": "function", "function": {"name": "player_involvement", "description": "A player's action counts up to a minute",
     "parameters": {"type": "object", "properties": {"player": {"type": "string"}, "to_minute": {"type": "integer"}}, "required": ["player"]}}},
]


def _mock(moment: dict, tools: Tools) -> dict:
    before = tools.events_before(moment["minute"])
    team = moment["team"]
    own = [e for e in before if e["team"] == team]
    c = Counter(e["type"] for e in own)
    name = tools.match["teams"][team]
    return {
        "headline": f"{moment['kind'].replace('_', ' ').title()} for {name} at {moment['minute']}'",
        "explanation": f"In the 90 seconds before, {name} logged {len(own)} of {len(before)} actions "
                       f"({c.get('pass_final_third', 0)} final-third passes, {c.get('dribble', 0)} dribbles, {c.get('press', 0)} presses). "
                       f"Sustained territorial pressure created the opening. [mock mode - add Azure keys for AI analysis]",
        "tactical_pattern": "sustained pressure" if len(own) > len(before) / 2 else "counter-attack",
        "evidence": [e["id"] for e in own[-5:]],
        "confidence": "medium",
    }


def explain(match: dict, moment: dict) -> dict:
    tools = Tools(match)

    def run():
        if llm.is_mock():
            return _mock(moment, tools)
        ctx = {**moment, "teams": match["teams"]}
        msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": json.dumps(ctx)}]
        for _ in range(6):
            r = llm.chat(msgs, model=llm.MODEL_SMART, tools=TOOL_SPECS)
            m = r.choices[0].message
            if not m.tool_calls:
                break
            msgs.append(m)
            for tc in m.tool_calls:
                out = getattr(tools, tc.function.name)(**json.loads(tc.function.arguments))
                msgs.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(out)})
        msgs.append({"role": "user", "content": "Now return the final JSON."})
        r = llm.chat(msgs, model=llm.MODEL_SMART, response_format={"type": "json_object"})
        return json.loads(r.choices[0].message.content)

    card = llm.cached(["why", match["match_id"], moment], run)
    by_id = {e["id"]: e for e in match["events"]}
    card["evidence_events"] = [by_id[i] for i in card.get("evidence", []) if i in by_id]
    return card
