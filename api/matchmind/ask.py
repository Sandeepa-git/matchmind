"""'Ask the analyst' - grounded Q&A over 5-minute match chunks.

Local retrieval is keyword-based. To upgrade, push `chunks()` into an Azure AI Search
index and replace `retrieve()` with a search query (see README).
"""
import json
import re
from collections import Counter

from . import llm


def chunks(match: dict, size: int = 5) -> list[dict]:
    out = []
    for start in range(0, 95, size):
        evs = [e for e in match["events"] if start <= e["minute"] < start + size]
        if not evs:
            continue
        lines = []
        for team in ("home", "away"):
            te = [e for e in evs if e["team"] == team]
            c = Counter(e["type"] for e in te)
            top = Counter(e["player"] for e in te).most_common(3)
            lines.append(f"{match['teams'][team]}: {len(te)} actions, {dict(c)}, most involved {top}")
        notable = [f"{e['minute']}' {e['player']} {e['type']}" + (f" xG {e['xg']}" if "xg" in e else "")
                   for e in evs if e["type"] in ("goal", "shot", "foul")]
        out.append({"id": f"min-{start}-{start + size}", "range": f"{start}-{start + size}",
                    "content": " | ".join(lines) + " | notable: " + "; ".join(notable)})
    return out


def retrieve(match: dict, question: str, k: int = 5) -> list[dict]:
    words = set(re.findall(r"\w+", question.lower()))
    mins = [int(n) for n in re.findall(r"\b(\d{1,2})\b", question)]
    scored = []
    for ch in chunks(match):
        lo, hi = map(int, ch["range"].split("-"))
        s = sum(w in ch["content"].lower() for w in words) + (5 if any(lo <= m < hi for m in mins) else 0)
        scored.append((s, ch))
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:k]]


def ask(match: dict, question: str) -> dict:
    ctx = retrieve(match, question)
    if llm.is_mock():
        return {"answer": f"[mock] Most relevant window: minutes {ctx[0]['range']}. {ctx[0]['content'][:300]}",
                "citations": [c["range"] for c in ctx]}
    prompt = ("Answer the fan's question using ONLY the match data below. Cite windows like [min 60-65]. "
              "If the data doesn't answer it, say so.\n\n"
              + "\n".join(f"[min {c['range']}] {c['content']}" for c in ctx)
              + f"\n\nTeams: {json.dumps(match['teams'])}\nQuestion: {question}")
    r = llm.chat([{"role": "user", "content": prompt}])
    return {"answer": r.choices[0].message.content, "citations": [c["range"] for c in ctx]}
