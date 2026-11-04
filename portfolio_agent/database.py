"""Reproducible CSV loading and bounded, read-only query execution."""
import csv
import math
import re
import sqlite3
import time
from pathlib import Path
from .models import AnalyticsError, QueryResult

ROOT = Path(__file__).resolve().parents[1]
TABLES = (
    "sectors", "securities", "benchmarks", "portfolios", "holdings",
    "transactions", "historical_prices", "portfolio_performance", "risk_metrics",
)
SAFE_FUNCTIONS = {
    "count", "sum", "avg", "min", "max", "total", "round", "abs", "coalesce",
    "ifnull", "nullif", "lower", "upper", "trim", "ltrim", "rtrim", "length",
    "substr", "substring", "replace", "like", "glob", "date", "datetime",
    "strftime", "julianday", "unixepoch", "typeof", "printf", "format",
    "row_number", "rank", "dense_rank", "lag", "lead", "first_value",
    "last_value", "nth_value", "ntile", "percent_rank", "cume_dist",
}


class Database:
    def __init__(self, root: Path = ROOT):
        self.root = root
        self.connection = sqlite3.connect(":memory:")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.executescript((root / "database_schema.sql").read_text())
        self.counts = {}
        for table in TABLES:
            with (root / "data" / f"{table}.csv").open(newline="", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                columns = next(reader)
                expected = [r[1] for r in self.connection.execute(f"PRAGMA table_info({table})")]
                if columns != expected:
                    raise AnalyticsError(f"Unexpected columns in {table}.csv.")
                rows = [[None if cell == "" else cell for cell in row] for row in reader]
            self.connection.executemany(
                f"INSERT INTO {table} VALUES ({','.join('?' for _ in columns)})", rows
            )
            self.counts[table] = len(rows)
        self.connection.commit()
        if self.connection.execute("PRAGMA foreign_key_check").fetchall():
            raise AnalyticsError("The dataset has broken foreign-key relationships.")
        for (weight,) in self.connection.execute("SELECT current_weight FROM holdings"):
            if not isinstance(weight, (float, int)) or not math.isfinite(weight) or weight < 0:
                raise AnalyticsError("Holding weights must be finite, nonnegative numbers.")
        self.portfolios = [r[0] for r in self.connection.execute("SELECT portfolio_name FROM portfolios")]
        self.sectors = [r[0] for r in self.connection.execute("SELECT sector_name FROM sectors")]
        self.schema = "\n".join(
            r[0] for r in self.connection.execute("SELECT sql FROM sqlite_master WHERE type='table'")
        )
        self.connection.execute("PRAGMA query_only=ON")
        self.connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 1_000_000)
        self.connection.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 20_000)
        self.connection.setlimit(sqlite3.SQLITE_LIMIT_COLUMN, 100)
        self.connection.setlimit(sqlite3.SQLITE_LIMIT_EXPR_DEPTH, 100)
        self.connection.set_authorizer(self._authorize)

    @staticmethod
    def _authorize(action, arg1, arg2, database, source):
        if action in {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_RECURSIVE}:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_READ and arg1 in TABLES:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_FUNCTION and (arg2 or "").lower() in SAFE_FUNCTIONS:
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    def query(self, sql: str, parameters: dict | None = None, max_rows=500) -> QueryResult:
        if len(sql) > 20000 or not re.match(r"^\s*(SELECT|WITH)\b", sql, re.IGNORECASE):
            raise AnalyticsError("Only a single read-only SELECT query is allowed.")
        deadline = time.monotonic() + 2
        ticks = 0

        def budget():
            nonlocal ticks
            ticks += 1
            return int(ticks > 2000 or time.monotonic() > deadline)

        self.connection.set_progress_handler(budget, 1000)
        try:
            cursor = self.connection.execute(sql, parameters or {})
            rows = cursor.fetchmany(max_rows + 1)
            return QueryResult(
                [d[0] for d in cursor.description],
                [list(r) for r in rows[:max_rows]], len(rows) > max_rows,
            )
        except sqlite3.Error as exc:
            # Database errors contain no credentials; useful for one bounded SQL repair.
            raise AnalyticsError(f"Query could not run: {exc}") from exc
        finally:
            self.connection.set_progress_handler(None, 0)

    def close(self):
        self.connection.close()
