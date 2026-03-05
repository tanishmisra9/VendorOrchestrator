from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MatchResult(BaseModel):
    record_id_a: int
    record_id_b: int
    vendor_name_a: str
    vendor_name_b: str
    fuzzy_score: float
    tax_id_match: bool = False
    llm_judgment: Optional[str] = None
    confidence: float
    cluster_id: Optional[int] = None
    timestamp: datetime = Field(default_factory=_utcnow)


class AnalystOverride(BaseModel):
    vendor_id: int
    original_action: str
    override_action: str
    reason: str
    analyst_name: str
    timestamp: datetime = Field(default_factory=_utcnow)


class QualitySuggestion(BaseModel):
    record_index: int
    field: str
    original_value: Optional[str] = None
    suggested_value: Optional[str] = None
    issue: str
    severity: str = "warning"


class ConfidenceEntry(BaseModel):
    record_index: int
    vendor_name: str
    confidence: float
    reason: str


class LLMRationale(BaseModel):
    record_id_a: int
    record_id_b: int
    judgment: str
    rationale: str
    model: str = "gpt-4"
    timestamp: datetime = Field(default_factory=_utcnow)


class RunContext(BaseModel):
    """Full context state for a single pipeline run."""

    run_id: str
    matching_history: list[MatchResult] = Field(default_factory=list)
    analyst_overrides: list[AnalystOverride] = Field(default_factory=list)
    quality_suggestions: list[QualitySuggestion] = Field(default_factory=list)
    confidence_levels: list[ConfidenceEntry] = Field(default_factory=list)
    llm_rationales: list[LLMRationale] = Field(default_factory=list)
