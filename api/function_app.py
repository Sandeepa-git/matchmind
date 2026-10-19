"""MatchMind HTTP API (Azure Functions, Python v2 model).

Live replay is stateless: the frontend advances a match clock and calls /api/state?minute=N,
which returns everything known up to that minute.
"""
import json
from functools import lru_cache

import azure.functions as func

from matchmind import agents, analyst, ask as ask_mod, recap as recap_mod
from matchmind.data import load_match
from matchmind.llm import is_mock
from matchmind.metrics import analyse

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


@lru_cache(maxsize=1)
def match():
    return load_match()


def upto(minute: int) -> dict:
    m = match()
    return {**m, "events": [e for e in m["events"] if e["minute"] <= minute]}


def ok(body, status=200):
    return func.HttpResponse(json.dumps(body, ensure_ascii=False), status_code=status, mimetype="application/json")


def minute_param(req) -> int:
    try:
        return max(0, min(95, int(req.params.get("minute", 95))))
    except ValueError:
        return 95


@app.route(route="state", methods=["GET"])
def state(req: func.HttpRequest) -> func.HttpResponse:
    minute = minute_param(req)
    st = analyse(upto(minute)["events"])
    m = match()
    return ok({"match_id": m["match_id"], "teams": m["teams"], "minute": minute, "mock": is_mock(),
               "summary": st.summary(), "series": st.series, "moments": st.moments})


@app.route(route="why/{moment_id:int}", methods=["GET"])
def why(req: func.HttpRequest) -> func.HttpResponse:
    st = analyse(match()["events"])
    mid = int(req.route_params["moment_id"])
    if mid >= len(st.moments):
        return ok({"error": "unknown moment"}, 404)
    return ok(analyst.explain(match(), st.moments[mid]))


@app.route(route="produce", methods=["POST"])
async def produce(req: func.HttpRequest) -> func.HttpResponse:
    """Runs the multi-agent workflow: Detector → Analyst → Narrator ⇄ FactChecker → Localizer."""
    body = req.get_json()
    persona = body.get("persona", "casual")
    fmt = body.get("format", "article")
    lang = body.get("lang", "en")
    if persona not in recap_mod.PERSONAS or fmt not in recap_mod.FORMATS or lang not in recap_mod.LANGS:
        return ok({"error": "bad persona/format/lang"}, 400)
    c = await agents.produce(match(), minute=max(0, min(95, int(body.get("minute", 95)))), persona=persona,
                             fmt=fmt, lang=lang, inject_error=bool(body.get("inject_error")))
    return ok({"text": c.final, "lang": lang, "verified": c.verified, "attempts": c.attempts,
               "trace": c.trace, "cards": c.cards})


@app.route(route="ask", methods=["POST"])
def ask(req: func.HttpRequest) -> func.HttpResponse:
    q = (req.get_json().get("question") or "").strip()[:500]
    if not q:
        return ok({"error": "question required"}, 400)
    return ok(ask_mod.ask(match(), q))


@app.route(route="options", methods=["GET"])
def options(req: func.HttpRequest) -> func.HttpResponse:
    return ok({"personas": list(recap_mod.PERSONAS), "formats": list(recap_mod.FORMATS), "langs": recap_mod.LANGS})
