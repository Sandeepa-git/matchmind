"""Run the full pipeline in the terminal: replay -> moments -> Why? card -> recap -> ask."""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from matchmind import analyst, ask, recap
from matchmind.data import load_match
from matchmind.llm import is_mock
from matchmind.metrics import MatchState

speed = float(sys.argv[1]) if len(sys.argv) > 1 else 0  # e.g. 0.02 for a "live" feel
m = load_match()
print(f"{m['teams']['home']} vs {m['teams']['away']}  (mock={is_mock()})\n")
st = MatchState()
for ev in m["events"]:
    mo = st.update(ev)
    if mo:
        print(f"{mo['minute']:>3}'  {mo['kind']:<14} {m['teams'][mo['team']]:<18} score {mo['score']}  momentum {mo['momentum']}")
    time.sleep(speed)
print("\nSummary:", st.summary())
first_goal = next((x for x in st.moments if x["kind"] == "goal"), st.moments[0])
card = analyst.explain(m, first_goal)
print("\nWHY?", card["headline"], "\n ", card["explanation"], "\n  evidence:", card["evidence"])
print("\nRECAP:", recap.recap(m, st.moments, st.summary(), "casual", "article"))
print("\nASK:", ask.ask(m, "What happened around minute 60?")["answer"])
