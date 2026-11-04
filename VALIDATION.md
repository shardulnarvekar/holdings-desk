# Verification

Verified on Windows / Python 3.13, 4 November 2026.

## Requirements coverage

| Supplied requirement | Implementation |
|---|---|
| Natural-language SQL tool | Structured Gemini plan and bounded read-only SQLite executor |
| Stock-sector exposure calculator | Adds supplied stock weights by sector; excludes bonds |
| Command-line agent | `python -m portfolio_agent` |
| Ground-truth evaluator | `python evaluate.py` |
| Run documentation and error handling | README, setup script, actionable errors and bounded retries |

All 13 supplied files (schema, ground truth, original instructions, suggested libraries and
nine CSV files) were compared byte-for-byte with the original package and match.
No further feature is required by the assignment. The optional Streamlit UI, evidence,
SQL safeguards, equity-only basis and hybrid tool comparisons are documented extras.

## Current checks

- 43 automated tests passed; report: `reports/unit-tests.xml`.
- All 18 reference cases execute successfully; report: `reports/reference-check.json`.
  Reference checking validates data/oracles, not model accuracy.
- Pinned dependency environment passes `pip check`.
- CLI, error paths, independent questions, SDK serialization, calculations, query safety,
  result comparison and Streamlit interactions are covered by tests.
- Reviewer setup was previously tested in a separate environment without the developer's
  `.env`; install and a live CLI question worked. Windows is verified; other OSes are not.
- UI has no chat history, follow-up memory or demo selector. Each question is independent.
  The CLI's optional preset demo is explicitly labelled and never counted as AI accuracy.
- Desktop/mobile layout checks found no horizontal overflow at 390/768/1440 px.

## Live evaluation

`reports/submission-evaluation.json` records the latest pre-publication run on
`gemini-3.5-flash-lite`, including every attempted case, provider error and latency.
The completed run passed 9/10 supplied cases, with median latency 19.23 seconds.
Question 7 failed with an invalid column reference after one SQL repair. A targeted
recheck is recorded separately in `reports/submission-q7-recheck.json`; it does not
rewrite the full-run score. That recheck passed (1/1) in 20.19 seconds. Failed SQL is now retained in evidence for diagnosis,
with automated coverage. Both the project and clean reviewer environments pass 43 tests.

Earlier full evaluation (`reports/final-evaluation.json`) passed all 10 required cases
and 6/8 extras; the two failed extra requests passed on a separate targeted retry
(`reports/extra-recheck.json`). The original 16/18 score is preserved. Prior experiments,
including quota-blocked model comparisons, are historical and do not establish current
accuracy. The current application remains on Flash-Lite.

## Interpretation and limits

These are development examples, not a blind test set. Passing them does not guarantee
accuracy on unseen questions. Provider latency, quotas and availability remain external
constraints. Errors are displayed rather than replaced with invented financial answers.
The documented sector-market-value cohort and diversification conventions follow the
supplied reference. Numerical answers and summaries come from tools, not model arithmetic.

This is an independent portfolio analytics project built with supplied historical sample
data. It is not an official PL Capital service, live market feed or investment adviser.
Private GitHub publication is separate from deploying a public application.
