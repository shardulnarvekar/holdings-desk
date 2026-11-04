"""Evaluate real agent results. Reference checking is explicitly NOT AI accuracy."""
import argparse
import csv
import hashlib
import json
import math
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from portfolio_agent.agent import PortfolioAgent
from portfolio_agent.database import Database, ROOT
from portfolio_agent.models import AnalyticsError, Answer
from portfolio_agent.planner import GeminiPlanner


def equivalent(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(a, b, rel_tol=1e-8, abs_tol=1e-4)
    return a == b


def rows_match(actual, expected, ordered=False):
    """Compare values, preserve duplicates; SQL text/aliases need not match."""
    if len(actual) != len(expected):
        return False
    def same(a, b):
        return len(a) == len(b) and all(equivalent(x, y) for x, y in zip(a, b))
    if ordered:
        return all(same(a, b) for a, b in zip(actual, expected))
    remaining = list(expected)
    for row in actual:
        index = next((i for i, ref in enumerate(remaining) if same(row, ref)), None)
        if index is None:
            return False
        remaining.pop(index)
    return True


def project_columns(actual_columns, actual_rows, expected_columns):
    """Allow additional fields only when every expected field is unambiguously named."""
    actual = [c.casefold() for c in actual_columns]
    expected = [c.casefold() for c in expected_columns]
    if all(actual.count(c) == 1 for c in expected):
        indexes = [actual.index(c) for c in expected]
        return [[row[i] for i in indexes] for row in actual_rows], "named_projection"
    if len(actual) == len(expected):
        return actual_rows, "positional_alias_tolerant"
    return None, "incompatible_columns"


def independent_exposure(root: Path, portfolio_name: str):
    """Separate CSV oracle; does not invoke the production exposure calculator."""
    def records(table):
        with (root / "data" / f"{table}.csv").open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    pid = next(p["portfolio_id"] for p in records("portfolios") if p["portfolio_name"] == portfolio_name)
    securities = {s["security_id"]: s for s in records("securities")}
    sectors = {s["sector_id"]: s["sector_name"] for s in records("sectors")}
    totals = {}
    for holding in records("holdings"):
        if holding["portfolio_id"] != pid:
            continue
        security = securities[holding["security_id"]]
        if security["asset_type"] != "Stock":
            continue
        sector = sectors.get(security["sector_id"], "Unclassified")
        totals[sector] = totals.get(sector, 0) + float(holding["current_weight"]) * 100
    return [[k, v] for k, v in totals.items()]


def expected_result(case, db):
    truth = case["ground_truth"]
    if "sql_query" in truth:
        result = db.query(truth["sql_query"])
        if result.truncated:
            raise AnalyticsError("Reference result was truncated; evaluation cannot proceed.")
        return result.columns, result.rows
    name = truth["parameters"]["portfolio_name"]
    return ["sector", "exposure_pct"], independent_exposure(db.root, name)


def dataset_hash():
    digest = hashlib.sha256()
    for path in sorted((ROOT / "data").glob("*.csv")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    digest.update((ROOT / "database_schema.sql").read_bytes())
    return digest.hexdigest()


def run_evaluation(agent, db, cases, delay=0, checkpoint=None):
    results = []
    blocked = None
    for case in cases:
        if results and delay and not blocked:
            time.sleep(delay)
        columns, expected = expected_result(case, db)
        if blocked:
            answer = Answer(case["question"], "skipped", f"Not attempted after {blocked}.",
                backend=agent.planner.name, error_code="skipped_after_provider_failure")
        else:
            answer = agent.answer_question(case["question"])
            if answer.error_code in {"daily_quota", "authentication", "model_unavailable"}:
                blocked = answer.error_code
        expected_tool = "sql_query" if case["type"] == "text2sql" else "exposure_calculator"
        tool_ok = answer.tool == expected_tool
        ordered = case.get("ordered", case["id"] == 5)
        projected, comparison = project_columns(answer.columns, answer.rows, columns)
        strict_match = len(answer.columns) == len(columns) and rows_match(answer.rows, expected, ordered)
        value_ok = answer.status == "ok" and projected is not None and rows_match(projected, expected, ordered)
        if expected_tool == "exposure_calculator":
            value_ok = value_ok and answer.evidence.get("portfolio_name") == case["ground_truth"]["parameters"]["portfolio_name"]
            value_ok = value_ok and answer.evidence.get("basis") == "portfolio"
        results.append({
            "id": case["id"], "question": case["question"], "difficulty": case.get("difficulty", "extra"),
            "passed": tool_ok and value_ok, "tool_correct": tool_ok,
            "values_correct": value_ok, "expected_columns": columns, "expected_rows": expected,
            "strict_shape_match": strict_match, "comparison": comparison,
            "failure_category": "" if tool_ok and value_ok else (answer.error_code or ("tool_selection" if not tool_ok else "result_mismatch")),
            "ordered_comparison": ordered, "actual": answer.to_dict(),
        })
        if checkpoint:
            checkpoint(results)
        label = "SKIP" if answer.status == "skipped" else "PASS" if tool_ok and value_ok else "FAIL"
        print(f"{label} {case['id']}: {case['question']}", flush=True)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-check", action="store_true", help="Check reference data only; not an AI benchmark")
    parser.add_argument("--extra", action="store_true", help="Include extra paraphrase/edge questions")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--model", help="Evaluate a Gemini model without changing .env or the app default")
    parser.add_argument("--delay", type=float, default=15, help="Seconds between model questions (default 15 for modest free-tier pacing)")
    parser.add_argument("--ids", nargs="+", type=int, help="Run only selected IDs, e.g. --ids 6 7 8")
    args = parser.parse_args()
    if not 0 <= args.delay <= 60:
        parser.error("--delay must be between 0 and 60 seconds")
    cases = json.loads((ROOT / "ground_truth_dataset.json").read_text())["questions"]
    if args.extra:
        cases += json.loads((ROOT / "tests" / "extra_questions.json").read_text())["questions"]
    if args.ids:
        unknown = set(args.ids) - {c["id"] for c in cases}
        if unknown:
            parser.error(f"Unknown IDs: {sorted(unknown)}. Use --extra for additional cases.")
        cases = [c for c in cases if c["id"] in args.ids]
    output = args.output or ROOT / "reports" / ("reference-check.json" if args.reference_check else "live-evaluation.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    db = Database()
    planner = None
    try:
        report = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "dataset_sha256": dataset_hash()}
        if args.reference_check:
            report.update({"mode": "reference_check", "notice": "Reference execution only. No language model tested; this is not agent accuracy."})
            report["results"] = [{"id": c["id"], "question": c["question"], "columns": expected_result(c, db)[0], "rows": expected_result(c, db)[1]} for c in cases]
            print(f"Validated {len(cases)} reference cases. AI accuracy has NOT been measured.")
            success = True
        else:
            planner = GeminiPlanner(db)
            if args.model:
                planner.model = args.model
            def checkpoint(results):
                partial = {**report, "mode": "live_gemini", "status": "in_progress", "model": planner.model, "results": results}
                output.write_text(json.dumps(partial, indent=2), encoding="utf-8")
            results = run_evaluation(PortfolioAgent(db, planner), db, cases, args.delay, checkpoint)
            report.update({"mode": "live_gemini", "model": planner.model, "results": results})
            report["passed"] = sum(r["passed"] for r in results)
            report["total"] = len(results)
            report["accuracy"] = report["passed"] / len(results)
            report["tool_accuracy"] = sum(r["tool_correct"] for r in results) / len(results)
            report["provider_failures"] = sum(r["failure_category"] in {"authentication", "rate_limit", "daily_quota", "model_unavailable", "provider_unavailable", "provider_or_plan_error"} for r in results)
            report["skipped"] = sum(r["actual"]["status"] == "skipped" for r in results)
            report["status"] = "blocked_by_provider" if report["skipped"] else "completed"
            report["request_delay_seconds"] = args.delay
            attempted = [r for r in results if r["actual"]["status"] != "skipped"]
            report["attempted"] = len(attempted)
            report["median_latency_ms"] = statistics.median(r["actual"]["elapsed_ms"] for r in attempted)
            report["by_difficulty"] = {d: {
                "passed": sum(r["passed"] for r in results if r["difficulty"] == d),
                "total": sum(r["difficulty"] == d for r in results),
            } for d in sorted({r["difficulty"] for r in results})}
            success = report["passed"] == len(results)
            print(f"Live result: {report['passed']}/{len(results)}. Median latency: {report['median_latency_ms']:.0f} ms.")
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Report: {output}")
        return 0 if success else 1
    except AnalyticsError as exc:
        print(str(exc))
        return 2
    finally:
        if planner:
            planner.close()
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
