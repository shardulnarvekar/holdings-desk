from portfolio_agent.presentation import summarize_rows


def test_single_record_keeps_date_and_value_without_inventing_units():
    message = summarize_rows(["portfolio_name", "volatility", "performance_date"],
                             [["Growth Equity Fund", 18.0, "2023-10-09"]])
    assert "Growth Equity Fund" in message and "volatility: 18" in message
    assert "2023-10-09" in message and "%" not in message


def test_time_series_reports_returned_range_not_latest_or_risk_advice():
    rows = [["Fund A", "2023-10-09", 18], ["Fund A", "2023-09-25", 20]]
    original = [row[:] for row in rows]
    message = summarize_rows(["portfolio_name", "performance_date", "volatility"], rows)
    assert "2023-09-25 to 2023-10-09" in message
    assert "latest" not in message and rows == original
    partial = summarize_rows(["portfolio_name", "performance_date", "volatility"], rows, True)
    assert "first 2 returned records" in partial


def test_missing_values_and_multiple_funds_do_not_become_single_fund_claim():
    assert "No data" in summarize_rows(["volatility"], [[None]])
    message = summarize_rows(["portfolio_name", "performance_date", "volatility"],
        [["Fund A", "2023-10-09", 18], ["Fund B", "2023-10-09", 20]])
    assert "across" not in message
    assert "Showing 2 records" in message
