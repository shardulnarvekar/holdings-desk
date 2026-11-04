from streamlit.testing.v1 import AppTest
from portfolio_agent.database import ROOT
from portfolio_agent.models import Plan, ProviderError
from portfolio_agent.planner import GeminiPlanner
import pytest


@pytest.fixture(autouse=True)
def isolated_ui_configuration(monkeypatch):
    # UI tests mock the planner and must not depend on a developer's .env.
    monkeypatch.setenv("GEMINI_API_KEY", "local-test-placeholder")
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: None)


def test_independent_questions_clear_and_explorer(monkeypatch):
    calls = []
    def plan(self, question, feedback="", history=None):
        calls.append(list(history or []))
        if len(calls) == 1:
            return Plan(tool="clarify", clarification="Which portfolio?")
        return Plan(tool="exposure_calculator", portfolio_name="International Equity Fund")
    monkeypatch.setattr(GeminiPlanner, "plan", plan)
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
    assert not app.exception and not calls and not app.radio
    app.text_input[0].set_value("Show sector exposure")
    app.button[0].click().run()
    app.text_input[0].set_value("International Equity Fund")
    app.button[0].click().run()
    assert calls == [[], []]
    assert "Energy" in app.session_state["live_answer"]["message"]
    next(b for b in app.button if b.label == "Clear result").click().run()
    assert "live_answer" not in app.session_state
    app.selectbox[0].select("Fixed Income Plus").run()
    assert any("No equity" in warning.value for warning in app.warning)
    assert not app.exception


def test_no_automatic_api_call(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Loading must not call Gemini")
    monkeypatch.setattr(GeminiPlanner, "plan", forbidden)
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
    assert not app.exception and len(app.text_input) == 1 and not app.sidebar.button


def test_error_is_visible_without_entering_context(monkeypatch):
    def fail(*args, **kwargs):
        raise ProviderError("Quota reached. Try later.", "daily_quota")
    monkeypatch.setattr(GeminiPlanner, "plan", fail)
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
    app.text_input[0].set_value("Count portfolios")
    app.button[0].click().run()
    assert "conversation" not in app.session_state
    assert any("Quota reached" in e.value for e in app.error)
    assert not app.exception
