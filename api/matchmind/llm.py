"""Azure OpenAI (Microsoft Foundry) client with a mock fallback so the app runs without keys."""
import hashlib
import json
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", encoding="utf-8-sig")
except ImportError:
    pass

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache"
MODEL_SMART = os.getenv("MODEL_SMART", "gpt-5-mini")
MODEL_FAST = os.getenv("MODEL_FAST", "gpt-5-mini")

_client = None


def client():
    global _client
    if os.getenv("MATCHMIND_MOCK") == "1":
        return None
    if _client is None and os.getenv("AZURE_OPENAI_KEY"):
        from openai import AzureOpenAI
        _client = AzureOpenAI(azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
                              api_key=os.environ["AZURE_OPENAI_KEY"], api_version="2025-04-01-preview")
    return _client


def is_mock() -> bool:
    return client() is None


def cached(key_parts: list, fn):
    """Cache LLM outputs on disk: saves Azure credit and makes demos instant."""
    if is_mock():
        return fn()
    CACHE_DIR.mkdir(exist_ok=True)
    key = hashlib.sha1(json.dumps(key_parts, sort_keys=True, default=str).encode()).hexdigest()
    path = CACHE_DIR / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    result = fn()
    path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return result


def chat(messages: list, model: str = MODEL_FAST, **kw):
    if model.startswith(("gpt-5", "o")):
        kw.setdefault("reasoning_effort", os.getenv("REASONING_EFFORT", "low"))
    return client().chat.completions.create(model=model, messages=messages, **kw)
