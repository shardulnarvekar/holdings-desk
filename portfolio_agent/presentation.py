"""Short factual summaries of tool output; no model call or inferred advice."""
from datetime import date


def format_value(value):
    if value is None:
        return "No data"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:,.6f}".rstrip("0").rstrip(".")
    return str(value)


def summarize_rows(columns, rows, truncated=False):
    if not rows:
        return "No matching records were found in the supplied dataset."
    labels = [name.replace("_", " ") for name in columns]
    if len(rows) == 1:
        fields = [f"{label}: {format_value(value)}" for label, value in zip(labels, rows[0])]
        return "; ".join(fields[:5]) + ("; more fields in the table." if len(fields) > 5 else "")

    # Only summarize a time series when the actual result identifies a single fund.
    if "portfolio_name" in columns and "performance_date" in columns:
        fund_index = columns.index("portfolio_name")
        date_index = columns.index("performance_date")
        funds = {row[fund_index] for row in rows}
        try:
            dates = [date.fromisoformat(row[date_index]) for row in rows]
        except (ValueError, TypeError):
            dates = []
        if len(funds) == 1 and dates:
            fields = [label for name, label in zip(columns, labels)
                      if name not in {"portfolio_name", "performance_date"}]
            metrics = ", ".join(fields[:3]) or "recorded data"
            prefix = "Showing the first" if truncated else "Showing"
            return (f"{next(iter(funds))}: {metrics}. "
                    f"{prefix} {len(rows)} returned records from {min(dates)} to {max(dates)}. "
                    "Values are as recorded in the dataset.")

    if len(columns) == 1:
        preview = ", ".join(format_value(row[0]) for row in rows[:3])
        remaining = f", and {len(rows) - 3} more" if len(rows) > 3 else ""
        prefix = "Showing the first" if truncated else "Found"
        return f"{prefix} {len(rows)} results for {labels[0]}: {preview}{remaining}."

    fields = ", ".join(labels[:4])
    if len(labels) > 4:
        fields += ", and additional fields"
    prefix = "Showing the first" if truncated else "Showing"
    return f"{prefix} {len(rows)} records with {fields}."
