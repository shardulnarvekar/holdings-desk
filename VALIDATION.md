# Release verification

Final audit: **7 November 2026**. Model: `gemini-3.5-flash-lite`.

## Required scope

The SQL tool, stock-sector exposure calculator, CLI agent, ground-truth evaluator,
run documentation and error handling are implemented. Streamlit, hybrid comparisons,
evidence/export and equity-only normalization are documented extras. No chat memory,
REST service, agent framework or extra deployment is needed.

All 13 original supplied files match byte-for-byte: nine CSVs, schema, ground truth,
README and suggested requirements. Original instructions are retained under `assessment/`.

## Automated and setup checks

- **48 automated tests pass** in fresh Python 3.11 and Python 3.13 environments on Windows.
- All **18 reference cases** execute correctly. This checks the expected data, not AI accuracy.
- `pip check` reports no broken dependencies.
- A new source copy with no `.env` or `.venv` completed `python setup_project.py` using
  Python 3.11 and Python 3.13 on Windows, in paths containing spaces. Both generated
  `.env` files contain no key; both passed all 48 tests and dependency validation.
  Python 3.11 also passed the direct CLI calculation and all 18 reference checks.
- UI reviewed at 390/768/1440 px with no page overflow; logo remains visible.
- Source and existing Git history scanned for the local key and common secret patterns.
- Each question is independent. No model request runs merely from loading the UI.

Tests cover read-only SQL boundaries, execution budgets, parameter injection, deterministic
calculations, mixed/bond-only funds, incomplete weights, ambiguity, evaluator mismatches,
bounded SQL repair, preserved failure evidence, SDK serialization, CLI and UI behavior.

## Setup compatibility correction

A reviewer-style Python 3.11 installation exposed a NumPy pin that required Python
3.12 or newer. The original Python 3.13 setup check did not cover this case.
The lock file now selects NumPy 2.4.6 on Python 3.11 and retains NumPy 2.5.4 on
Python 3.12+. All other pinned versions are unchanged. Real clean installations
and the complete test suite passed on both locally available Python versions.
Repeating setup preserved `.env` unchanged. The originally failed Python 3.11
test copy also completed setup successfully without replacing its virtual environment,
and passed a direct CLI calculation and dependency check.
This change does not alter the agent prompt or financial calculations.

## Live results

The initial full audit, `reports/final-audit-2026-11-07.json`, passed **17/18**:
9/10 required and 8/8 extra questions. Median latency was **1.49 seconds**. The miss
was unnecessary clarification of a uniquely matching shortened portfolio name.

The next required-question run, `reports/release-required-2026-11-07.json`, passed
9/10. A repaired SQL query incorrectly excluded bonds from a market-value denominator.
The planner now explicitly describes the schema's nullable sector relationship and
requires preserving all holdings in total-value calculations. The name-resolution
instructions also clarify unique whole-word matches. Neither correction changes data,
expected results or comparison tolerances.

The final full run, `reports/release-final-2026-11-07.json`, passed **18/18**: all
**10 supplied questions** and **8 additional cases**, with no provider failures. Median
latency was **2.64 seconds** per answer on this run. This is a
recorded development result, not a guarantee for every future question.

Earlier development reports are under `reports/archive/`. Failed runs remain available;
they are not relabelled as passes.

## Limits

These are development cases, not unseen holdout questions. Results can vary between
requests. Provider quotas, latency and outages remain external constraints. Errors are
shown rather than substituted with fabricated answers. The reference-specific sector
cohort and diversification conventions are documented in `docs/METHODOLOGY.md`.

Windows/Python 3.11 and 3.13 are verified locally. macOS/Linux commands are documented, not locally
tested. Original code/documentation is MIT licensed; supplied materials and third-party
assets are explicitly excluded. The PL Capital mark identifies assessment context, not
official endorsement. GitHub publication does not deploy a public service.


## Incomplete-plan fix — 8 November 2026

A repeated live comparison question returned a hybrid plan without SQL. Authentication
was working; the old generic message incorrectly suggested connectivity. The planner
now emphasizes the required hybrid selection SQL and makes at most one correction
attempt for invalid plan structure. Authentication failures are not retried by this
correction path. If correction fails, the message identifies an invalid plan and no
calculation executes. All 51 automated tests passed on the development Python 3.13
environment. The originally failing question passed live in the Python 3.11 test copy:
Tech Innovation Fund, 100% Technology exposure, 1.50 seconds. This targeted recheck
is separate from the earlier full 18-case evaluation.
