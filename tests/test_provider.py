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


@pytest.mark.parametrize("payload", [
    "", "not json", "{}", '{"tool":"unrecognized"}',
    '{"tool":"sql_query"}', '{"tool":"exposure_calculator"}',
    '{"tool":"clarify"}', '{"tool":"hybrid","sql":"SELECT portfolio_name FROM portfolios","top_n":0}',
    '{"tool":"sql_query","sql":"SELECT :x","parameters":[{"name":"x","value":1},{"name":"x","value":2}]}',
])
def test_bad_responses_never_execute_and_recover_next_question(monkeypatch, payload):
    from types import SimpleNamespace
    from portfolio_agent.agent import PortfolioAgent
    monkeypatch.setenv("GEMINI_API_KEY", "local-test-placeholder")
    db = Database()
    planner = GeminiPlanner(db)
    planner.close()
    calls = []
    def generate(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(text=payload if len(calls) <= 2 else '{"tool":"sql_query","sql":"SELECT COUNT(*) FROM portfolios"}')
    planner.client = SimpleNamespace(models=SimpleNamespace(generate_content=generate), close=lambda: None)
    try:
        agent = PortfolioAgent(db, planner)
        answer = agent.answer_question("Count portfolios")
        assert answer.status == "error" and answer.error_code == "invalid_plan"
        assert not answer.rows and len(calls) == 2
        answer = agent.answer_question("Count portfolios")
        assert answer.status == "ok" and answer.rows == [[13]] and len(calls) == 3
    finally:
        planner.close(); db.close()


@pytest.mark.parametrize("code,detail,category", [
    (401, "private request details", "authentication"),
    (403, "private request details", "authentication"),
    (404, "private request details", "model_unavailable"),
    (429, "requestsPerDay private request details", "daily_quota"),
    (429, "private request details", "rate_limit"),
    (500, "private request details", "provider_unavailable"),
    (503, "private request details", "provider_unavailable"),
    (None, "private request details", "provider_or_plan_error"),
])
def test_provider_failure_is_safe_and_next_question_can_succeed(monkeypatch, code, detail, category):
    from types import SimpleNamespace
    from portfolio_agent.agent import PortfolioAgent
    monkeypatch.setenv("GEMINI_API_KEY", "local-test-placeholder")
    db = Database(); planner = GeminiPlanner(db); planner.close()
    calls = []
    def generate(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            error = RuntimeError(detail); error.code = code; raise error
        return SimpleNamespace(text='{"tool":"sql_query","sql":"SELECT COUNT(*) FROM portfolios"}')
    planner.client = SimpleNamespace(models=SimpleNamespace(generate_content=generate), close=lambda: None)
    try:
        agent = PortfolioAgent(db, planner)
        answer = agent.answer_question("Count portfolios")
        assert answer.error_code == category and answer.status == "error" and not answer.rows
        assert "private request details" not in answer.message
        assert len(calls) == 1
        assert agent.answer_question("Count portfolios").rows == [[13]]
    finally:
        planner.close(); db.close()


def test_env_key_edits_take_effect_after_process_restart(tmp_path):
    import os
    import subprocess
    import sys
    env = dict(os.environ)
    env.pop("GEMINI_API_KEY", None)
    env.pop("GOOGLE_API_KEY", None)
    script = """
import sys
from pathlib import Path
import portfolio_agent.planner as module
from portfolio_agent.database import Database
from portfolio_agent.models import AnalyticsError
module.ROOT=Path(sys.argv[1])
db=Database()
try:
    planner=module.GeminiPlanner(db)
    planner.close()
    print('configured')
except AnalyticsError:
    print('missing')
finally:
    db.close()
"""
    for content, expected in [("# GEMINI_API_KEY=local-placeholder", "missing"),
                              ("GEMINI_API_KEY=local-placeholder", "configured"),
                              ("# GEMINI_API_KEY=local-placeholder", "missing")]:
        (tmp_path / '.env').write_text(content, encoding='utf-8')
        result = subprocess.run([sys.executable, '-c', script, str(tmp_path)], env=env, capture_output=True, text=True)
        assert result.returncode == 0 and result.stdout.strip() == expected


@pytest.mark.parametrize("status,expected_calls,expected_code", [
    (503, 2, None), (429, 1, "rate_limit"), (403, 1, "authentication"), (404, 1, "model_unavailable")
])
def test_actual_sdk_retry_policy(monkeypatch, status, expected_calls, expected_code):
    from portfolio_agent.models import ProviderError
    monkeypatch.setenv("GEMINI_API_KEY", "local-test-placeholder")
    db = Database(); planner = GeminiPlanner(db); planner.close()
    calls = []
    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(status, json={"error":{"code":status,"message":"private-provider-detail","status":"UNAVAILABLE"}})
        return httpx.Response(200, json={"candidates":[{"content":{"role":"model","parts":[{"text":'{"tool":"sql_query","sql":"SELECT COUNT(*) FROM portfolios"}'}]},"finishReason":"STOP"}]})
    planner.client = genai.Client(api_key="local-test-placeholder", http_options=types.HttpOptions(
        client_args={"transport":httpx.MockTransport(handler)},
        retry_options=types.HttpRetryOptions(attempts=2, initial_delay=0.01, max_delay=0.01, http_status_codes=[500,502,503,504])))
    try:
        if expected_code:
            with pytest.raises(ProviderError) as raised:
                planner.plan("Count portfolios")
            assert raised.value.code == expected_code
            assert "private-provider-detail" not in str(raised.value)
        else:
            assert planner.plan("Count portfolios").tool == "sql_query"
        assert len(calls) == expected_calls
    finally:
        planner.close(); db.close()
