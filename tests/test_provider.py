"""Exercise the actual SDK serialization with a local HTTP transport; no API calls."""
import json
import httpx
from google import genai
from google.genai import types
from portfolio_agent.database import Database
from portfolio_agent.models import AnalyticsError
from portfolio_agent.planner import GeminiPlanner
import pytest


def test_sdk_wire_contract(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "local-test-placeholder")
    db = Database()
    planner = GeminiPlanner(db)
    planner.client.close()
    def handler(request):
        payload = json.loads(request.content)
        assert payload["generationConfig"]["responseJsonSchema"]["properties"]["tool"]
        assert "ground_truth" not in request.content.decode()
        assert [turn["role"] for turn in payload["contents"]] == ["user"]
        assert "conversation_history" not in request.content.decode()
        return httpx.Response(200, json={"candidates": [{"content": {"role": "model", "parts": [{"text": json.dumps({"tool": "sql_query", "sql": "SELECT COUNT(*) FROM portfolios"})}]}, "finishReason": "STOP"}]})
    planner.client = genai.Client(api_key="local-test-placeholder", http_options=types.HttpOptions(client_args={"transport": httpx.MockTransport(handler)}))
    try:
        plan = planner.plan("How many portfolios?")
        assert plan.tool == "sql_query"
    finally:
        planner.close()
        db.close()


def test_missing_key_is_actionable(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    db = Database()
    try:
        with pytest.raises(AnalyticsError, match="local .env"):
            GeminiPlanner(db)
    finally:
        db.close()


@pytest.mark.parametrize("outcome", ["corrected", "invalid", "authentication"])
def test_invalid_plan_correction_is_bounded(monkeypatch, outcome):
    from types import SimpleNamespace
    from portfolio_agent.models import ProviderError
    monkeypatch.setenv("GEMINI_API_KEY", "local-test-placeholder")
    db = Database()
    planner = GeminiPlanner(db)
    planner.client.close()
    calls = []

    def generate(**kwargs):
        calls.append(json.loads(kwargs["contents"]))
        if outcome == "authentication":
            error = RuntimeError("sensitive-provider-details")
            error.code = 403
            raise error
        if len(calls) == 2 and outcome == "corrected":
            return SimpleNamespace(text=json.dumps({"tool": "hybrid", "sql": "SELECT portfolio_name FROM portfolios"}))
        return SimpleNamespace(text=json.dumps({"tool": "hybrid", "sector": "Technology", "top_n": 1}))

    planner.client = SimpleNamespace(models=SimpleNamespace(generate_content=generate), close=lambda: None)
    try:
        if outcome == "corrected":
            assert planner.plan("Compare exposure").sql
            assert len(calls) == 2
            assert calls[1]["plan_validation_errors"]
            assert "input" not in calls[1]["plan_validation_errors"][0]
        else:
            with pytest.raises(ProviderError) as raised:
                planner.plan("Compare exposure")
            assert raised.value.code == ("authentication" if outcome == "authentication" else "invalid_plan")
            assert len(calls) == (1 if outcome == "authentication" else 2)
            assert "sensitive-provider-details" not in str(raised.value)
    finally:
        planner.close()
        db.close()
