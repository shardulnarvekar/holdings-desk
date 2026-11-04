"""A thin review interface over the same agent used by the CLI."""
import base64
import html
import os
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from portfolio_agent.agent import PortfolioAgent
from portfolio_agent.database import Database, ROOT
from portfolio_agent.exposure import calculate_exposure
from portfolio_agent.models import AnalyticsError
from portfolio_agent.planner import GeminiPlanner

st.set_page_config(page_title="Portfolio Lens | Portfolio Analytics", page_icon=":material/account_balance:", layout="wide")
load_dotenv(ROOT / ".env", override=True)
font_css = ""
for weight, filename in [(400, "SourceSans3-Regular.ttf.woff2"), (600, "SourceSans3-Semibold.ttf.woff2")]:
    encoded = base64.b64encode((ROOT / "assets" / "fonts" / filename).read_bytes()).decode("ascii")
    font_css += f"@font-face{{font-family:PortfolioSans;src:url(data:font/woff2;base64,{encoded}) format('woff2');font-weight:{weight};font-display:swap;}}"
st.markdown("<style>" + font_css + (ROOT / "assets" / "style.css").read_text(encoding="utf-8") + "</style>", unsafe_allow_html=True)


def run_question(question):
    db = Database()
    planner = None
    try:
        planner = GeminiPlanner(db)
        agent = PortfolioAgent(db, planner)
        answer = agent.answer_question(question).to_dict()
        return answer
    except AnalyticsError as exc:
        return {"status": "error", "message": str(exc), "question": question, "rows": [], "columns": [], "warnings": [], "evidence": {}, "backend": "gemini", "tool": "", "elapsed_ms": 0}
    finally:
        if planner and hasattr(planner, "close"):
            planner.close()
        db.close()


def render_sector_chart(rows):
    """Accessible proportional bars, labelled with exact values; no model calls."""
    parts = []
    for sector, percent in sorted(rows, key=lambda row: (-row[1], row[0])):
        width = max(0, min(100, float(percent)))
        label = html.escape(str(sector))
        parts.append(f'<div class="sector-row"><div class="sector-label"><span>{label}</span><span class="sector-value">{percent:,.2f}%</span></div><div class="sector-track" aria-hidden="true"><div class="sector-fill" style="width:{width}%"></div></div></div>')
    st.markdown('<div class="sector-chart" role="group" aria-label="Sector exposure percentages">' + ''.join(parts) + '<div class="chart-scale" aria-hidden="true"><span>0%</span><span>50%</span><span>100%</span></div></div>', unsafe_allow_html=True)


def render_answer(answer, message_key):
    if answer["status"] == "error":
        st.error(answer["message"])
        return
    if answer["status"] == "clarification":
        st.info(answer["message"] + " Restate your full question with these details.")
        return
    st.write(answer["message"])
    for warning in answer["warnings"]:
        st.warning(warning)
    data = pd.DataFrame(answer["rows"], columns=answer["columns"])
    if answer["tool"] == "exposure_calculator":
        display_data = data.rename(columns={"sector": "Sector", "exposure_pct": "Exposure (%)"})
        basis = answer["evidence"]["basis"]
        st.caption("Percentage of " + ("the equity allocation" if basis == "equity" else "the whole portfolio using supplied weights") + ". Bonds excluded.")
        st.dataframe(display_data, hide_index=True, use_container_width=True,
            column_config={"Exposure (%)": st.column_config.NumberColumn("Exposure (%)", format="%.2f")})
        with st.expander("View sector chart"):
            render_sector_chart(answer["rows"])
    elif not data.empty:
        display_data = data.rename(columns=lambda name: name.replace("_", " ").capitalize())
        st.dataframe(display_data, hide_index=True, use_container_width=True)
    with st.expander("Details & export"):
        st.caption(f"{answer['tool'].replace('_', ' ')} · {answer['elapsed_ms'] / 1000:.2f}s · {answer['backend']}")
        evidence = answer["evidence"]
        if "sql" in evidence:
            st.code(evidence["sql"], language="sql")
            if evidence.get("parameters"):
                st.json(evidence["parameters"])
        if "formula" in evidence:
            st.code(evidence["formula"], language="text")
        st.caption("Source: supplied CSV assessment dataset. No live market feed.")
        st.json(evidence, expanded=False)
        if not data.empty:
            st.download_button("Download CSV", data.to_csv(index=False), "portfolio-result.csv", "text/csv", key=f"csv_{message_key}")


st.title("Portfolio Lens")
st.caption("Portfolio analytics · Holdings, allocations and exposure")
ask, explore, notes = st.tabs(["Ask the agent", "Portfolio explorer", "About the data"])

with ask:
    if not os.getenv("GEMINI_API_KEY"):
        st.info("Add GEMINI_API_KEY to .env to ask questions. Portfolio explorer works without a key.")
    st.caption("Each question stands alone. Include the portfolio and metric you want to explore.")
    with st.form("ask_form", border=False, clear_on_submit=False):
        question = st.text_input("Your question", placeholder="What are the sector exposures for International Equity Fund?", max_chars=2000)
        submitted = st.form_submit_button("Ask the agent", type="primary", disabled=not bool(os.getenv("GEMINI_API_KEY")))
    if submitted:
        with st.spinner("Checking the portfolio data…"):
            st.session_state["live_answer"] = run_question(question)
    if "live_answer" in st.session_state:
        st.divider()
        st.subheader("Answer")
        st.caption(st.session_state["live_answer"]["question"])
        render_answer(st.session_state["live_answer"], "current")
        if st.button("Clear result"):
            st.session_state.pop("live_answer", None)
            st.rerun()
    else:
        with st.expander("Example questions"):
            st.markdown("- What are the names of all active portfolios?\n- What are the sector exposures for International Equity Fund?\n- Show the top 5 holdings by cost basis in Growth Equity Fund.")

with explore:
    st.caption("Calculate sector weights directly. No AI request needed.")
    db = Database()
    try:
        a, b = st.columns([2, 1])
        with a:
            name = st.selectbox("Portfolio", db.portfolios, index=6)
        with b:
            basis_label = st.selectbox("Percentage basis", ["Whole portfolio", "Equities only"])
        exposure = calculate_exposure(db, name, "equity" if basis_label == "Equities only" else "portfolio")
        st.subheader(name)
        for warning in exposure["warnings"]:
            st.warning(warning)
        if exposure["rows"]:
            data = pd.DataFrame(exposure["rows"], columns=["Sector", "Exposure (%)"])
            st.dataframe(data, hide_index=True, use_container_width=True)
            with st.expander("View sector chart"):
                render_sector_chart(exposure["rows"])
        else:
            st.info("There are no equity sectors to display.")
        st.caption(f"Supplied weights: {exposure['total_weight_pct']:g}% · Equities: {exposure['equity_weight_pct']:g}% · Bonds excluded: {exposure['excluded_bond_weight_pct']:g}%")
        with st.expander("Portfolio directory"):
            directory = db.query("SELECT portfolio_name, target_risk_level, total_aum, status FROM portfolios")
            st.dataframe(pd.DataFrame(directory.rows, columns=directory.columns), hide_index=True, use_container_width=True)
    finally:
        db.close()

with notes:
    st.subheader("Data and assumptions")
    st.markdown("""
**Sector exposure** adds the supplied stock holding weights by sector. Bonds are excluded.
The default percentage basis is the whole portfolio. Equity-only normalization is an explicit choice.

**Recorded AUM and listed holding value are different fields.** AUM is taken directly from
the portfolio record. Market-value questions use quantity × supplied current price.
The sample's values do not reconcile; we preserve the source instead of inventing adjustments.

**One fund has incomplete weight coverage.** Total Stock Market Index Fund's weights sum
to 98%. We report the gap, without assuming it is cash or automatically normalizing it away.

**Classifications come from the supplied dataset.** A fund's name is not evidence of geographic
exposure. These historical sample records are not live prices or investment recommendations.

**The agent is read-only.** It has a bounded SQL executor and a deterministic exposure calculator.
Each question is independent. Earlier questions and answers are not sent to Gemini.\nThe evaluator treats each assessment question independently.
""")
    st.subheader("Evaluation you can reproduce")
    st.code("python evaluate.py --reference-check\npython evaluate.py --extra\npython -m pytest -q", language="bash")
    st.caption("Reference checking validates the dataset only. Live evaluation measures Gemini answers against reference results. See reports/ for generated reports.")

st.caption("Sample data · September–October 2023 · Not live market data")
