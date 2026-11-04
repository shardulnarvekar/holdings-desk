import json
import pytest
from portfolio_agent.database import Database, ROOT
from portfolio_agent.exposure import calculate_exposure, resolve_portfolio
from portfolio_agent.agent import PortfolioAgent
from portfolio_agent.models import AnalyticsError, Plan, ProviderError
from portfolio_agent.planner import DemoPlanner
from evaluate import rows_match, independent_exposure, expected_result, run_evaluation, project_columns


@pytest.fixture
def db():
    database = Database()
    yield database
    database.close()


def test_supplied_data_loads_and_references_execute(db):
    assert db.counts == dict(sectors=10, securities=30, benchmarks=13, portfolios=13,
        holdings=95, transactions=24, historical_prices=330, portfolio_performance=44, risk_metrics=44)
    cases = json.loads((ROOT / "ground_truth_dataset.json").read_text())["questions"]
    expected_counts = [1, 10, 8, 1, 5, 7, 8, 1, 1, 4]
    for case, count in zip(cases, expected_counts):
        assert len(expected_result(case, db)[1]) == count
    assert expected_result(cases[3], db)[1] == [[85000000.0]]


@pytest.mark.parametrize("sql", [
    "DELETE FROM portfolios", "DROP TABLE holdings", "PRAGMA query_only=OFF",
    "ATTACH DATABASE 'x.db' AS external", "SELECT 1; DELETE FROM portfolios",
    "WITH t AS (SELECT 1) DELETE FROM holdings", "SELECT * FROM sqlite_master",
    "SELECT load_extension('anything')", "SELECT writefile('x.txt','payload')",
    "SELECT randomblob(1000000000)", "SELECT * FROM pragma_table_info('portfolios')",
])
def test_read_only_boundary(db, sql):
    with pytest.raises(AnalyticsError):
        db.query(sql)
    assert db.query("SELECT COUNT(*) FROM portfolios").rows == [[13]]


def test_query_budget_and_recovery(db):
    with pytest.raises(AnalyticsError, match="interrupted"):
        db.query("WITH RECURSIVE numbers(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM numbers) SELECT SUM(n) FROM numbers")
    assert db.query("SELECT 1").rows == [[1]]


def test_truncation_is_explicit(db):
    result = db.query("SELECT * FROM holdings", max_rows=5)
    assert len(result.rows) == 5 and result.truncated


def test_parameter_injection_is_data(db):
    assert db.query("SELECT portfolio_name FROM portfolios WHERE portfolio_name=:name", {"name": "' OR 1=1 --"}).rows == []


def test_exposure_expected_breakdown(db):
    result = calculate_exposure(db, "international equity")
    assert dict(result["rows"]) == {"Energy": 38, "Technology": 36, "Automotive": 15, "Consumer Staples": 11}
    assert calculate_exposure(db, "Tech Innovation Fund")["rows"] == [["Technology", 100]]


def test_mixed_portfolio_denominators(db):
    whole = calculate_exposure(db, "balanced")
    equity = calculate_exposure(db, "balanced", "equity")
    assert dict(whole["rows"])["Technology"] == 22
    assert sum(row[1] for row in whole["rows"]) == 36
    assert whole["excluded_bond_weight_pct"] == 64
    assert dict(equity["rows"])["Technology"] == pytest.approx(61.111111)
    assert sum(row[1] for row in equity["rows"]) == pytest.approx(100)


@pytest.mark.parametrize("basis", ["portfolio", "equity"])
def test_bond_only_has_no_division_by_zero(db, basis):
    result = calculate_exposure(db, "Fixed Income Plus", basis)
    assert result["rows"] == [] and result["excluded_bond_weight_pct"] == 100
    assert "No equity" in result["warnings"][0]


def test_incomplete_weights_are_not_silently_normalized(db):
    result = calculate_exposure(db, "Total Stock Market Index Fund")
    assert sum(row[1] for row in result["rows"]) == 98
    assert result["total_weight_pct"] == 98 and result["warnings"]


def test_names_are_resolved_without_guessing(db):
    assert resolve_portfolio("INTERNATIONAL EQUITY", db.portfolios) == "International Equity Fund"
    with pytest.raises(AnalyticsError, match="ambiguous"):
        resolve_portfolio("international", db.portfolios)
    with pytest.raises(AnalyticsError, match="No portfolio"):
        resolve_portfolio("Imaginary Fund", db.portfolios)


def test_independent_oracle_agrees_for_every_portfolio(db):
    for name in db.portfolios:
        assert rows_match(calculate_exposure(db, name)["rows"], independent_exposure(ROOT, name))


def test_comparison_preserves_duplicates_and_order():
    assert rows_match([[2], [1.00000001]], [[1], [2]])
    assert not rows_match([[2], [1]], [[1], [2]], ordered=True)
    assert not rows_match([[1], [1]], [[1], [2]])
    assert not rows_match([[None]], [[0]])
    assert not rows_match([[1000001]], [[1000000]])


class StubPlanner:
    name = "test stub, not AI"
    def __init__(self, *plans):
        self.plans = iter(plans)
        self.calls = 0
    def plan(self, question, feedback=""):
        self.calls += 1
        return next(self.plans)


def test_agent_bounded_sql_repair(db):
    planner = StubPlanner(Plan(tool="sql_query", sql="SELECT missing FROM portfolios"),
        Plan(tool="sql_query", sql="SELECT COUNT(*) FROM portfolios"))
    answer = PortfolioAgent(db, planner).answer_question("How many portfolios?")
    assert answer.status == "ok" and answer.rows == [[13]]
    assert planner.calls == 2 and answer.evidence["repair_attempts"]


def test_agent_never_repairs_write_attempt(db):
    planner = StubPlanner(Plan(tool="sql_query", sql="DELETE FROM portfolios"))
    assert PortfolioAgent(db, planner).answer_question("Delete portfolios").status == "error"
    assert planner.calls == 1


def test_failed_repair_retains_sql_for_diagnosis(db):
    planner = StubPlanner(Plan(tool="sql_query", sql="SELECT missing FROM portfolios"),
        Plan(tool="sql_query", sql="SELECT still_missing FROM portfolios"))
    answer = PortfolioAgent(db, planner).answer_question("Count portfolios")
    assert answer.status == "error" and planner.calls == 2
    assert answer.evidence["sql"] == "SELECT still_missing FROM portfolios"
    assert answer.evidence["repair_attempts"][0]["sql"] == "SELECT missing FROM portfolios"


def test_hybrid_uses_both_tools(db):
    answer = PortfolioAgent(db, DemoPlanner()).answer_question("Compare Technology exposure across active high-risk funds")
    assert answer.status == "ok"
    assert answer.rows == [["Tech Innovation Fund", "Technology", 100.0], ["Growth Equity Fund", "Technology", 93.0], ["Emerging Markets Fund", "Technology", 35.0], ["Small Cap Value Fund", "Technology", 0]]
    assert answer.evidence["tools_used"] == ["sql_query", "exposure_calculator"]


def test_demo_refuses_freeform(db):
    answer = PortfolioAgent(db, DemoPlanner()).answer_question("What are tomorrow's returns?")
    assert answer.status == "error" and "Demo mode" in answer.message


def test_evaluator_detects_wrong_tool_even_with_correct_number(db):
    cases = [{"id": 999, "type": "exposure_calculator", "question": "technology exposure", "ground_truth": {"parameters": {"portfolio_name": "Tech Innovation Fund"}}}]
    planner = StubPlanner(Plan(tool="sql_query", sql="SELECT 'Technology', 100"))
    results = run_evaluation(PortfolioAgent(db, planner), db, cases)
    assert not results[0]["passed"] and not results[0]["tool_correct"]


def test_blank_input_never_calls_model(db):
    planner = StubPlanner()
    assert PortfolioAgent(db, planner).answer_question(" ").status == "error"
    assert planner.calls == 0


def test_named_projection_accepts_extra_fields_but_not_missing_values():
    rows, method = project_columns(["security_id", "symbol", "company_name"], [[1,"AAPL","Apple"]], ["symbol", "company_name"])
    assert rows == [["AAPL", "Apple"]] and method == "named_projection"
    assert not rows_match(rows, [["AAPL", "Apple"], ["MSFT", "Microsoft"]])
    assert project_columns(["symbol", "symbol", "other"], [], ["symbol"])[0] is None
    assert project_columns(["company_name"], [], ["symbol", "company_name"])[0] is None
    reordered, _ = project_columns(["company_name", "symbol"], [["Apple", "AAPL"]], ["symbol", "company_name"])
    assert reordered == [["AAPL", "Apple"]]


def test_daily_quota_stops_requests_and_checkpoints(db):
    class QuotaPlanner:
        name = "quota test"
        calls = 0
        def plan(self, question, feedback=""):
            self.calls += 1
            raise ProviderError("Daily quota exhausted", "daily_quota")
    planner = QuotaPlanner()
    cases = json.loads((ROOT / "ground_truth_dataset.json").read_text())["questions"][:3]
    checkpoints = []
    results = run_evaluation(PortfolioAgent(db, planner), db, cases, checkpoint=lambda rows: checkpoints.append(len(rows)))
    assert planner.calls == 1
    assert [r["actual"]["status"] for r in results] == ["error", "skipped", "skipped"]
    assert checkpoints == [1, 2, 3]
