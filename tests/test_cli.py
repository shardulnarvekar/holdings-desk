import subprocess
import sys
from portfolio_agent.database import ROOT


def test_cli_demo_is_concise_and_explain_is_optional():
    command = [sys.executable, "-m", "portfolio_agent", "--demo", "Count the portfolios"]
    plain = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    assert plain.returncode == 0 and "13" in plain.stdout
    assert "Evidence:" not in plain.stdout
    detailed = subprocess.run(command + ["--explain"], cwd=ROOT, text=True, capture_output=True)
    assert detailed.returncode == 0 and "SELECT COUNT(*)" in detailed.stdout


def test_interactive_cli_accepts_questions_and_exits():
    result = subprocess.run([sys.executable, "-m", "portfolio_agent", "--demo"],
        cwd=ROOT, input="Count the portfolios\nexit\n", text=True, capture_output=True)
    assert result.returncode == 0
    assert "Ask >" in result.stdout and "portfolio count: 13" in result.stdout
