"""Small, explicit contract between the language model and deterministic tools."""
from dataclasses import dataclass, field, asdict
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Parameter(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    value: str | int | float | None


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: Literal["sql_query", "exposure_calculator", "hybrid", "clarify"]
    sql: str = ""
    parameters: list[Parameter] = Field(default_factory=list)
    portfolio_name: str = ""
    basis: Literal["portfolio", "equity"] = "portfolio"
    sector: str = ""
    top_n: int | None = Field(default=None, ge=1, le=50)
    clarification: str = ""

    @model_validator(mode="after")
    def validate_action(self):
        if self.tool in {"sql_query", "hybrid"} and not self.sql.strip():
            raise ValueError("A database action requires SQL.")
        if self.tool == "exposure_calculator" and not self.portfolio_name.strip():
            raise ValueError("An exposure action requires a portfolio name.")
        if self.tool == "clarify" and not self.clarification.strip():
            raise ValueError("Clarification requires a question for the user.")
        names = [p.name for p in self.parameters]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate SQL parameter names.")
        return self


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[list]
    truncated: bool = False


@dataclass
class Answer:
    question: str
    status: str
    message: str
    tool: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)
    evidence: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    elapsed_ms: float = 0
    backend: str = ""
    error_code: str = ""

    def to_dict(self):
        return asdict(self)


class AnalyticsError(Exception):
    """Safe, actionable message that can be shown to a user."""


class ProviderError(AnalyticsError):
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code
