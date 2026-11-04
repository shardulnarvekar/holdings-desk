from portfolio_agent.agent import PortfolioAgent
from portfolio_agent.database import Database
from portfolio_agent.models import Plan


def test_repeated_questions_are_independent():
    class Planner:
        name = "test"
        def __init__(self): self.calls = []
        def plan(self, question, feedback=""):
            self.calls.append((question, feedback))
            return Plan(tool="clarify", clarification="Please provide a complete question.")
    db = Database()
    try:
        planner = Planner(); agent = PortfolioAgent(db, planner)
        agent.answer_question("Volatility for Growth Equity Fund")
        agent.answer_question("How many portfolios?")
        assert planner.calls == [("Volatility for Growth Equity Fund", ""), ("How many portfolios?", "")]
        assert not hasattr(agent, "history")
    finally: db.close()
