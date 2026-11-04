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
