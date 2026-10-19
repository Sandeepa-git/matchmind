"""Multi-agent match production pipeline on Microsoft Agent Framework workflows.

    Detector ─▶ Analyst ─▶ Narrator ─▶ FactChecker ──pass──▶ Localizer ─▶ output
                              ▲             │
                              └──reject─────┤ (with feedback, max 2 retries)
                                            └──give up──▶ Fallback ─▶ Localizer

All agents share one MatchContext (shared state) and append to its trace, which the UI
shows so judges and users can see every handoff, rejection and recovery.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler

from . import analyst, llm
from . import recap as recap_mod
from .metrics import analyse

MAX_RETRIES = 2


@dataclass
class MatchContext:
    match: dict
    minute: int = 95
    persona: str = "casual"
    fmt: str = "article"
    lang: str = "en"
    inject_error: bool = False          # stress test: force a hallucination to show recovery
    moments: list = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    cards: list = field(default_factory=list)
    draft: str = ""
    feedback: list = field(default_factory=list)
    attempts: int = 0
    verified: bool = False
    final: str = ""
    trace: list = field(default_factory=list)

    def log(self, agent: str, status: str, detail: str, started: float) -> None:
        self.trace.append({"agent": agent, "status": status, "detail": detail,
                           "ms": int((time.perf_counter() - started) * 1000)})


class Detector(Executor):
    """Turns the raw event stream into scored key moments."""

    @handler
    async def run(self, c: MatchContext, ctx: WorkflowContext[MatchContext]) -> None:
        t = time.perf_counter()
        events = [e for e in c.match["events"] if e["minute"] <= c.minute]
        st = analyse(events)
        c.moments, c.summary = st.moments, st.summary()
        # per-half team stats ground tactical claims for both the Narrator and the FactChecker
        tools = analyst.Tools({**c.match, "events": events})
        c.summary["stats"] = {f"{side}_{half}": tools.team_stats(side, lo, hi)
                              for side in ("home", "away") for half, (lo, hi) in {"1st_half": (0, 45), "2nd_half": (46, 95)}.items()}
        kinds = {k: sum(m["kind"] == k for m in c.moments) for k in {m["kind"] for m in c.moments}}
        c.log("Detector", "ok", f"{len(events)} events → {len(c.moments)} moments {kinds}", t)
        await ctx.send_message(c)


class Analyst(Executor):
    """Explains the most important moments with tool-gathered evidence."""

    @handler
    async def run(self, c: MatchContext, ctx: WorkflowContext[MatchContext]) -> None:
        t = time.perf_counter()
        key = [m for m in c.moments if m["kind"] == "goal"][:4] or c.moments[:2]
        c.cards = []
        for m in key:
            try:
                c.cards.append({"moment": m, **analyst.explain(c.match, m)})
            except Exception as ex:  # one failed card must not sink the pipeline
                c.log("Analyst", "warn", f"card for {m['minute']}' failed: {ex}", t)
        c.log("Analyst", "ok", f"{len(c.cards)} evidence-backed Why? cards", t)
        await ctx.send_message(c)


class Narrator(Executor):
    """Writes the recap for the requested persona/format, honouring FactChecker feedback."""

    @handler
    async def run(self, c: MatchContext, ctx: WorkflowContext[MatchContext]) -> None:
        t = time.perf_counter()
        c.attempts += 1
        if c.inject_error and c.attempts == 1:
            scorer = next((m["player"] for m in c.moments if m["kind"] == "goal"), "the striker")
            c.draft = (f"{c.match['teams']['home']} won 4-0 thanks to a hat-trick from {scorer} in the 12th minute. "
                       + recap_mod.recap(c.match, c.moments, c.summary, c.persona, c.fmt))
            c.log("Narrator", "ok", f"draft #{c.attempts} (stress test: hallucination injected)", t)
        elif c.feedback and not llm.is_mock():
            prompt = (f"Rewrite this {recap_mod.FORMATS[c.fmt]} fixing these fact-check errors: {c.feedback}.\n"
                      f"Facts: teams {c.match['teams']}, final {c.summary}, moments {json.dumps(c.moments)}.\n"
                      f"Style: {recap_mod.PERSONAS[c.persona]}\n\nDraft:\n{c.draft}")
            c.draft = llm.chat([{"role": "user", "content": prompt}]).choices[0].message.content
            c.log("Narrator", "ok", f"draft #{c.attempts} rewritten from feedback", t)
        else:
            c.draft = recap_mod.recap(c.match, c.moments, c.summary, c.persona, c.fmt)
            c.log("Narrator", "ok", f"draft #{c.attempts} ({c.persona}/{c.fmt})", t)
        await ctx.send_message(c)


def check_claims(text: str, c: MatchContext) -> list[str]:
    """Deterministic grounding checks: scorelines, minutes and scorers must exist in the data."""
    issues = []
    valid_scores = {(0, 0)} | {(m["score"]["home"], m["score"]["away"]) for m in c.moments}
    for a, b in re.findall(r"(?<![\d.])(\d)\s*[-–]\s*(\d)(?![\d.%])", text):
        if (int(a), int(b)) not in valid_scores and (int(b), int(a)) not in valid_scores:
            issues.append(f"scoreline {a}-{b} never happened")
    moment_minutes = {m["minute"] for m in c.moments}
    for mstr in re.findall(r"\b(\d{1,2})(?:'|’|st|nd|rd|th)\s*(?:minute)?", text):
        mi = int(mstr)
        if not any(abs(mi - x) <= 1 for x in moment_minutes):
            issues.append(f"no key moment near minute {mi}")
    scorers = {m["player"] for m in c.moments if m["kind"] == "goal"}
    goals_by = {p: sum(m.get("player") == p and m["kind"] == "goal" for m in c.moments) for p in scorers}
    for p, n in goals_by.items():
        if re.search(rf"hat-?trick[^.]*\b{re.escape(p)}\b|\b{re.escape(p)}\b[^.]*hat-?trick", text, re.I) and n < 3:
            issues.append(f"{p} scored {n}, not a hat-trick")
    return issues


class FactChecker(Executor):
    """Rejects any draft containing claims the event data does not support."""

    @handler
    async def run(self, c: MatchContext, ctx: WorkflowContext[MatchContext]) -> None:
        t = time.perf_counter()
        issues = check_claims(c.draft, c)
        if not issues and not llm.is_mock():
            prompt = ("You are a sports fact-checker. Compare the TEXT with the DATA and list problems as JSON "
                      "{\"errors\": [{\"claim\": str, \"severity\": \"critical\"|\"minor\"}]}. "
                      "critical = a concrete fact that CONTRADICTS the data: wrong score, scorer, minute, team, a number "
                      "that disagrees with the stats, or an event that never happened. "
                      "minor = interpretation, emphasis, opinion or style. Return an empty list if nothing is wrong.\n"
                      f"DATA: teams {c.match['teams']}, summary+stats {json.dumps(c.summary)}, "
                      f"moments {json.dumps(c.moments)}\nTEXT: {c.draft}")
            r = llm.chat([{"role": "user", "content": prompt}], response_format={"type": "json_object"})
            errors = json.loads(r.choices[0].message.content).get("errors", [])
            issues = [e["claim"] for e in errors if e.get("severity") == "critical"][:5]
        c.verified, c.feedback = not issues, issues
        c.log("FactChecker", "pass" if c.verified else "reject",
              "all claims grounded" if c.verified else "; ".join(issues), t)
        # route explicitly so the decision can't be affected by later mutations of the shared context
        target = "localizer" if c.verified else "narrator" if c.attempts <= MAX_RETRIES else "fallback"
        await ctx.send_message(c, target_id=target)


class Fallback(Executor):
    """Last resort after repeated rejections: a template recap built only from verified data."""

    @handler
    async def run(self, c: MatchContext, ctx: WorkflowContext[MatchContext]) -> None:
        t = time.perf_counter()
        s, teams = c.summary["score"], c.match["teams"]
        goals = "; ".join(f"{m['minute']}' {m['player']} ({teams[m['team']]})" for m in c.moments if m["kind"] == "goal")
        c.draft = (f"{teams['home']} {s['home']}-{s['away']} {teams['away']}. Goals: {goals or 'none'}. "
                   f"xG {c.summary['xg']['home']} vs {c.summary['xg']['away']}.")
        c.verified = True
        c.log("Fallback", "ok", f"template recap after {c.attempts} rejected drafts", t)
        await ctx.send_message(c)


class Localizer(Executor):
    """Translates the verified recap for the target audience."""

    @handler
    async def run(self, c: MatchContext, ctx: WorkflowContext[MatchContext, MatchContext]) -> None:
        t = time.perf_counter()
        try:
            c.final = recap_mod.translate(c.draft, c.lang)
            c.log("Localizer", "ok", f"→ {recap_mod.LANGS.get(c.lang, c.lang)}", t)
        except Exception as ex:
            c.final = c.draft
            c.log("Localizer", "warn", f"translation failed, serving English: {ex}", t)
        await ctx.yield_output(c)


def build_workflow():
    det, ana, nar = Detector(id="detector"), Analyst(id="analyst"), Narrator(id="narrator")
    fc, fb, loc = FactChecker(id="factchecker"), Fallback(id="fallback"), Localizer(id="localizer")
    return (WorkflowBuilder(name="matchmind-producer", start_executor=det, max_iterations=30)
            .add_chain([det, ana, nar, fc])
            .add_edge(fc, loc)
            .add_edge(fc, nar)
            .add_edge(fc, fb)
            .add_edge(fb, loc)
            .build())


async def produce(match: dict, **opts) -> MatchContext:
    result = await build_workflow().run(MatchContext(match=match, **opts))
    return result.get_outputs()[-1]
