import argparse
import json
import sys
from .agent import PortfolioAgent
from .database import Database
from .exposure import calculate_exposure
from .models import AnalyticsError
from .planner import GeminiPlanner, DemoPlanner, DEMO_QUESTIONS


def display(answer, as_json=False, explain=False):
    if as_json:
        print(json.dumps(answer.to_dict(), indent=2, ensure_ascii=False))
        return
    print(f"\n[{answer.status.upper()} | {answer.backend}] {answer.message}")
    if answer.columns:
        print(" | ".join(answer.columns))
        for row in answer.rows:
            print(" | ".join("NULL" if x is None else str(x) for x in row))
    for warning in answer.warnings:
        print("Note:", warning)
    if explain:
        print("Evidence:", json.dumps(answer.evidence, indent=2, ensure_ascii=False))
    print(f"Time: {answer.elapsed_ms:.0f} ms")


def main():
    parser = argparse.ArgumentParser(description="Portfolio Analytics Agent — supplied assessment snapshot")
    parser.add_argument("question", nargs="?")
    parser.add_argument("--demo", action="store_true", help="Preset walkthrough only; no Gemini calls")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--explain", action="store_true", help="Show SQL, parameters and calculation evidence")
    parser.add_argument("--exposure", metavar="PORTFOLIO", help="Run the calculator directly without AI")
    parser.add_argument("--basis", choices=["portfolio", "equity"], default="portfolio")
    args = parser.parse_args()
    db = Database()
    planner = None
    try:
        if args.exposure:
            print(json.dumps(calculate_exposure(db, args.exposure, args.basis), indent=2))
            return 0
        planner = DemoPlanner() if args.demo else GeminiPlanner(db)
        agent = PortfolioAgent(db, planner)
        if args.question:
            answer = agent.answer_question(args.question)
            display(answer, args.json, args.explain)
            return 0 if answer.status in {"ok", "clarification"} else 1
        print("Portfolio Analytics | Snapshot: 25 Sep-09 Oct 2023 | Type exit to quit.")
        print("Each question is independent. Include the portfolio, metric and period you need.")
        print("Example: What is the latest recorded volatility for Growth Equity Fund?")
        if args.demo:
            print("DEMO: preset plans, not AI. Available questions:")
            print("\n".join(DEMO_QUESTIONS))
        while True:
            try:
                question = input("\nAsk > ").strip()
            except EOFError:
                break
            if question.lower() in {"exit", "quit"}:
                break
            if not args.demo and question and sys.stderr.isatty():
                print("Waiting for Gemini to choose a tool...", file=sys.stderr, flush=True)
            display(agent.answer_question(question), args.json, args.explain)
        return 0
    except AnalyticsError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    finally:
        if planner and hasattr(planner, "close"):
            planner.close()
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
