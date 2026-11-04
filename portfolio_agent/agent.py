"""Bounded orchestration shared by CLI, evaluator and UI."""
import time
from .database import Database
from .exposure import calculate_exposure
from .models import AnalyticsError, Answer, Plan
from .planner import Planner
from .presentation import summarize_rows


class PortfolioAgent:
    def __init__(self, db: Database, planner: Planner):
        self.db, self.planner = db, planner

    def answer_question(self, question: str) -> Answer:
        start = time.perf_counter()
        answer = Answer(question, "error", "", backend=self.planner.name)
        try:
            if not question.strip() or len(question) > 2000:
                raise AnalyticsError("Enter a question between 1 and 2,000 characters.")
            plan = self.planner.plan(question)
            answer.tool = plan.tool
            attempts = []
            try:
                self._execute(plan, answer)
            except AnalyticsError as exc:
                # One repair only for ordinary SQL syntax/schema errors, never safety blocks.
                repairable = any(t in str(exc).lower() for t in ("no such column", "no such table", "syntax error", "ambiguous column"))
                if plan.tool not in {"sql_query", "hybrid"} or not repairable:
                    raise
                attempts.append({"sql": plan.sql, "error": str(exc)})
                answer.evidence["repair_attempts"] = attempts
                plan = self.planner.plan(question, f"SQL: {plan.sql}\nError: {exc}")
                answer.tool = plan.tool
                self._execute(plan, answer)
            if attempts:
                answer.evidence["repair_attempts"] = attempts
        except AnalyticsError as exc:
            answer.status = "error"
            answer.message = str(exc)
            answer.error_code = getattr(exc, "code", "tool_or_input_error")
        answer.elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        return answer

    def _execute(self, plan: Plan, answer: Answer):
        if plan.tool == "clarify":
            answer.status, answer.message = "clarification", plan.clarification
            return
        if plan.tool == "exposure_calculator":
            exposure = calculate_exposure(self.db, plan.portfolio_name, plan.basis)
            answer.columns, answer.rows = exposure["columns"], exposure["rows"]
            answer.warnings = exposure["warnings"]
            answer.evidence = exposure
            basis = "the equity allocation" if plan.basis == "equity" else "the supplied portfolio weights"
            if exposure["rows"]:
                sector, percent = exposure["rows"][0]
                answer.message = f"{exposure['portfolio_name']}: {sector} is the largest sector at {percent:g}% of {basis}."
            else:
                answer.message = f"{exposure['portfolio_name']} has no equity sector exposure to report."
            answer.status = "ok"
            return
        parameters = {p.name: p.value for p in plan.parameters}
        # Preserve failed SQL too, so evaluator errors are reproducible and inspectable.
        answer.evidence.update({"sql": plan.sql, "parameters": parameters})
        result = self.db.query(plan.sql, parameters)
        answer.evidence = {"sql": plan.sql, "parameters": parameters, "truncated": result.truncated}
        if result.truncated:
            answer.warnings.append("Result exceeds 500 rows. This is a partial result; narrow the question.")
        if plan.tool == "sql_query":
            answer.columns, answer.rows = result.columns, result.rows
            answer.message = summarize_rows(result.columns, result.rows, result.truncated)
            answer.status = "partial" if result.truncated else "ok"
            return
        # Hybrid query selects a cohort; deterministic exposure tool operates on each fund.
        if result.truncated or len(result.columns) != 1 or result.columns[0] != "portfolio_name":
            raise AnalyticsError("A hybrid query must return a complete, single portfolio_name column.")
        if plan.top_n and not plan.sector:
            raise AnalyticsError("Specify a sector before ranking portfolio exposures.")
        sector = None
        if plan.sector:
            sector = next((s for s in self.db.sectors if s.casefold() == plan.sector.casefold()), None)
            if sector is None:
                raise AnalyticsError(f"Unknown sector '{plan.sector}'.")
        answer.columns = ["portfolio_name", "sector", "exposure_pct"]
        breakdowns = []
        for name in dict.fromkeys(r[0] for r in result.rows):
            exposure = calculate_exposure(self.db, name, plan.basis)
            breakdowns.append(exposure)
            answer.warnings.extend(f"{name}: {w}" for w in exposure["warnings"])
            if sector:
                if plan.basis == "equity" and exposure["equity_weight_pct"] == 0:
                    answer.warnings.append(f"{name}: excluded from equity-normalized comparison (no equities).")
                    continue
                value = dict(exposure["rows"]).get(sector, 0)
                answer.rows.append([name, sector, value])
            else:
                answer.rows.extend([name, s, v] for s, v in exposure["rows"])
        if sector:
            answer.rows.sort(key=lambda r: (-r[2], r[0]))
        if plan.top_n:
            answer.rows = answer.rows[:plan.top_n]
        answer.evidence.update({"basis": plan.basis, "exposures": breakdowns, "tools_used": ["sql_query", "exposure_calculator"]})
        answer.message = f"Compared sector exposure for {len(breakdowns)} portfolio(s)."
        if sector and answer.rows:
            answer.message = f"{answer.rows[0][0]} has the highest {sector} exposure in this group: {answer.rows[0][2]:g}%."
        answer.status = "ok"
