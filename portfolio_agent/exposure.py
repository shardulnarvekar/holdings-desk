"""Exposure is calculated from supplied weights, never model arithmetic."""
import re
from decimal import Decimal
from .database import Database
from .models import AnalyticsError


def normalized_name(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def resolve_portfolio(name: str, names: list[str]) -> str:
    query = normalized_name(name)
    if not query:
        raise AnalyticsError("Please specify a portfolio name.")
    exact = [n for n in names if normalized_name(n) == query]
    if exact:
        return exact[0]
    # Token matching handles 'international equity' without guessing typos.
    candidates = [n for n in names if set(query.split()).issubset(normalized_name(n).split())]
    if len(candidates) == 1:
        return candidates[0]
    if candidates:
        raise AnalyticsError("Portfolio name is ambiguous. Choose: " + "; ".join(candidates))
    raise AnalyticsError(f"No portfolio matches '{name}'. Check the portfolio directory.")


def calculate_exposure(db: Database, name: str, basis: str = "portfolio") -> dict:
    if basis not in {"portfolio", "equity"}:
        raise AnalyticsError("Exposure basis must be portfolio or equity.")
    name = resolve_portfolio(name, db.portfolios)
    result = db.query(
        """SELECT s.asset_type, sec.sector_name, h.current_weight
        FROM holdings h JOIN portfolios p USING(portfolio_id)
        JOIN securities s USING(security_id)
        LEFT JOIN sectors sec USING(sector_id)
        WHERE p.portfolio_name = :name""", {"name": name}
    )
    sectors = {}
    total = equity = bonds = Decimal(0)
    warnings = []
    for asset, sector, raw_weight in result.rows:
        weight = Decimal(str(raw_weight))
        total += weight
        if asset == "Bond":
            bonds += weight
            continue
        equity += weight
        sector = sector or "Unclassified"
        sectors[sector] = sectors.get(sector, Decimal(0)) + weight
    if abs(total - 1) > Decimal("0.000001"):
        warnings.append(f"Supplied holding weights total {total * 100:.2f}%. The difference is not assumed to be cash.")
    if "Unclassified" in sectors:
        warnings.append("Some stock holdings lack a sector; retained as Unclassified.")
    if not result.rows:
        warnings.append("This portfolio has no holding records.")
    elif equity == 0:
        warnings.append("No equity holdings. Sector exposure is not applicable; bonds are excluded.")
    divisor = equity if basis == "equity" else Decimal(1)
    rows = sorted(
        [[sector, round(float(weight / divisor * 100), 6)] for sector, weight in sectors.items()],
        key=lambda r: (-r[1], r[0]),
    ) if divisor else []
    return {
        "portfolio_name": name, "basis": basis,
        "columns": ["sector", "exposure_pct"], "rows": rows,
        "equity_weight_pct": float(equity * 100),
        "excluded_bond_weight_pct": float(bonds * 100),
        "total_weight_pct": float(total * 100), "warnings": warnings,
        "formula": "100 × sum(stock current_weight in sector)" + (
            " / sum(all stock current_weight)" if basis == "equity" else ""
        ),
    }
