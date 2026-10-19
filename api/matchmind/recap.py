"""Persona- and format-aware recaps, plus translation via Azure AI Translator."""
import json
import os
import uuid

import requests

from . import llm

PERSONAS = {
    "casual": "Fun and simple, no jargon, energetic, about 120 words.",
    "tactics": "Detailed tactical breakdown: shape, pressing, half-spaces, transitions. About 250 words.",
    "fantasy": "Focus on player performances, FPL-relevant actions (goals, chances, defensive work) and captaincy tips.",
    "kids": "Explain like to a 10-year-old new fan, friendly and short.",
}
FORMATS = {
    "tv_script": "a 60-second broadcast voiceover script with [cue] markers",
    "social": "a 5-post social media thread with emojis, numbered 1/5..5/5",
    "article": "a match report with a headline and 3 short paragraphs",
}
LANGS = {"en": "English", "es": "Spanish", "fr": "French", "hi": "Hindi", "ar": "Arabic", "si": "Sinhala", "pt": "Portuguese", "ja": "Japanese"}


def recap(match: dict, moments: list, summary: dict, persona: str, fmt: str) -> str:
    def run():
        if llm.is_mock():
            goals = [m for m in moments if m["kind"] == "goal"]
            lines = [f"{m['minute']}' {m['player']} scores for {match['teams'][m['team']]}" for m in goals]
            s = summary["score"]
            return (f"[mock {persona}/{fmt}] {match['teams']['home']} {s['home']}-{s['away']} {match['teams']['away']}. "
                    + "; ".join(lines) + f". xG {summary['xg']['home']} vs {summary['xg']['away']}.")
        prompt = (f"Teams: {json.dumps(match['teams'])}\nFinal: {json.dumps(summary)}\n"
                  f"Key moments: {json.dumps(moments)}\n\nWrite {FORMATS[fmt]}. Audience style: {PERSONAS[persona]} "
                  "Use only the facts given; tactical points must be supported by the per-half stats. "
                  "Use plain language that translates well: avoid idioms like 'late winner' or 'parked the bus'.")
        r = llm.chat([{"role": "user", "content": prompt}])
        return r.choices[0].message.content

    return llm.cached(["recap", match["match_id"], persona, fmt, len(moments)], run)


def translate(text: str, lang: str) -> str:
    if lang == "en":
        return text
    key = os.getenv("TRANSLATOR_KEY")
    if not key:
        return f"[{LANGS.get(lang, lang)} translation needs TRANSLATOR_KEY] {text}"

    def run():
        r = requests.post("https://api.cognitive.microsofttranslator.com/translate",
                          params={"api-version": "3.0", "to": lang},
                          headers={"Ocp-Apim-Subscription-Key": key,
                                   "Ocp-Apim-Subscription-Region": os.getenv("TRANSLATOR_REGION", "eastus2"),
                                   "X-ClientTraceId": str(uuid.uuid4())},
                          json=[{"text": text}], timeout=20)
        r.raise_for_status()
        return r.json()[0]["translations"][0]["text"]

    return llm.cached(["tr", text, lang], run)
