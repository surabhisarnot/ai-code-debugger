"""The shape of everything that goes in and out. Pydantic enforces it."""
from typing import Literal

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    code: str = Field(min_length=1)
    language: str = "python"


class Finding(BaseModel):
    title: str = Field(description="Short name of the issue")
    severity: Literal["critical", "high", "medium", "low"]
    category: Literal["bug", "security", "performance", "style", "design"]
    line_start: int = Field(description="First line of the issue (1-indexed)")
    line_end: int = Field(description="Last line of the issue (1-indexed)")
    evidence: str = Field(
        description="Exact code copied from those lines. No line-number prefixes."
    )
    explanation: str = Field(description="Why this is a problem, in plain words")
    suggested_fix: str = Field(description="Corrected code or a concrete fix")
    confirmed_by: str | None = Field(
        default=None,
        description="Tool and rule that flagged this, e.g. 'ruff F841' or "
        "'bandit B608'. Null if it comes from your own reading only.",
    )


class Report(BaseModel):
    summary: str = Field(description="2-3 sentences: what the code does")
    walkthrough: str = Field(
        description="Code comprehension: entry points, how the functions call "
        "each other, and the main execution flow, in plain words"
    )
    architecture_notes: str = Field(
        description="Structure, responsibilities, and any design gaps"
    )
    findings: list[Finding]
    improvements: list[str] = Field(
        description="General improvements that are not specific bugs"
    )
