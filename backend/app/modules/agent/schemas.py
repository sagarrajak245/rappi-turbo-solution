"""Structured LLM outputs (KB §3.2 nodes 5 and 7) and the agent API DTOs."""

from pydantic import BaseModel, ConfigDict, Field

from app.modules.validation.schemas import ProposedDecision, SoftOverride
from app.shared.enums import Outcome, Verdict


class DecisionOut(BaseModel):
    """What the decide node asks the LLM for. Converted to a ProposedDecision for validation."""

    model_config = ConfigDict(frozen=True)

    verdict: Verdict
    qty: int | None = Field(default=None, ge=0)
    reasons: list[str] = []
    facts_cited: list[str] = []
    deviation_reason: str | None = None
    overrides: list[SoftOverride] = []
    investigate_items: list[str] = []
    recommended_option: str | None = None

    def to_proposed(self) -> ProposedDecision:
        return ProposedDecision(
            verdict=self.verdict,
            qty=self.qty,
            outcome=Outcome.PROPOSE,
            reasons=tuple(self.reasons),
            deviation_reason=self.deviation_reason,
            overrides=tuple(self.overrides),
        )


class ReviewOut(BaseModel):
    """The reviewer LLM's groundedness check."""

    model_config = ConfigDict(frozen=True)

    ok: bool
    issues: list[str] = []
