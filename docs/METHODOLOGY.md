# Calculations, safety and evaluation

## Financial definitions and data limitations

- **Exposure default:** `100 Ã— SUM(current_weight)` for stock holdings in each sector.
  Do not replace weights with price-derived weights. Bonds are excluded without rescaling.
- **Equity-only basis:** divide the stock-sector weight by all stock weights. This is an explicit
  option, not the default. A portfolio with no equities returns no sector rows and an explanation.
- **Mixed portfolio example:** Balanced Portfolio has 36% stocks and 64% bonds. Technology is
  22% of the supplied whole-portfolio weights, or 61.111111% of the equity allocation.
- **Incomplete weights:** Total Stock Market Index Fund sums to 98%. The remaining 2% is
  unaccounted for in supplied weights; it is not assumed to be cash.
- **AUM versus holding value:** `portfolios.total_aum` is recorded AUM. Market-value queries use
  `quantity Ã— current_price`, as in supplied reference question 7. These values do not reconcile
  in this dataset. Bond prices are treated exactly as that reference specifies; no face-value
  conversion is invented.
- **Different measures can differ:** International Equity Fund's Technology exposure is 36%
  by weights and 47.2% by the supplied market-value formula.
- **Source classifications:** sector and country come from the CSVs, even if a fund name suggests
  something else. Fund names are not a substitute for country data.
- **Named-sector market-value results:** by default, return portfolios that hold the requested
  sector, following the supplied reference. Zero-exposure portfolios are included only when
  explicitly requested. The phrase "for each portfolio" is ambiguous in the supplied question;
  this convention is documented rather than changing the expected data.
- **Historical sample:** dated observations span 25 Sepâ€“09 Oct 2023. This is not live market data.
- **Diversification ratio:** distinct stock sectors / total holdings, rounded to 3 decimals,
  follows the supplied evaluation convention. It is not a general-purpose financial risk score.

## Reliability boundaries

- In-memory database rebuilt from unchanged CSVs; foreign keys and weight validity checked.
- SQLite `query_only` and an authorizer deny writes, schema changes, file attachment,
  introspection and non-approved functions. A SELECT prefix alone is not the safety boundary.
- Single-statement execution; named value parameters; no arbitrary Python execution.
- Approximately 2 seconds / 2 million SQLite VM steps per query, 500 output rows,
  SQL/expression/string limits. Truncated answers are labelled partial and cannot pass evaluation.
- One SQL repair for syntax/schema errors. Safety failures are not repaired automatically.
- Exact or unique token-based portfolio resolution. Ambiguous names ask for specificity instead
  of guessing. Fuzzy typo correction is intentionally not included.
- Final numbers and evidence come from tools. No second model call paraphrases or changes numbers.
- Short answer summaries are generated directly from returned fields, values and dates. Tables
  retain the full result. Summaries add no API calls and do not infer risk ratings or missing units.
- Provider errors are converted into actionable messages without logging API keys.

These are application safeguards for this local assessment, not a hardened multi-tenant sandbox.
Public hosting would require authentication, per-user quotas and deployment-specific controls.

## Evaluation methodology

The supplied file contains 8 reference SQL queries and 2 exposure tool specifications.
The evaluator executes reference SQL on the same source dataset. Exposure expectations are
computed through a separate CSV implementation, independent of the production calculator.

Results compare values rather than SQL strings or aliases. Numeric tolerance is `abs=1e-4`,
`rel=1e-8`; duplicates are preserved. The explicit top-5 request (question 5) and extra
cases explicitly marked ordered preserve row order. Reference SQL's incidental ordering
does not constrain questions that did not ask for an order.
Other cases use unordered row comparison. If all reference column names appear unambiguously,
the evaluator selects those columns by name, allowing reordered or additional descriptive fields.
Otherwise it requires the same column count and compares positions while ignoring aliases.
It records both the strict shape match and the comparison method. Missing rows, duplicate rows,
wrong values, and incomplete projections still fail. Exposure cases also check tool, resolved
portfolio and basis. This is a pragmatic evaluator, not a complete SQL-equivalence prover.

All interfaces and the evaluator are stateless: no earlier questions or answers are sent to Gemini.
The agent never imports the ground-truth file. The prompt contains documented domain definitions,
including the supplied diversification convention, but no stored answers. The 10 supplied cases
are development examples, not a blind test set. The additional 8 questions are also authored
development checks; neither score proves performance on unseen finance questions.
