"""Domain vocabulary shared across modules (planning, validation, ERP, agent)."""

from enum import StrEnum


class Verdict(StrEnum):
    """What the agent says about the recommendation (KB D24)."""

    ACCEPT = "ACCEPT"
    MODIFY = "MODIFY"
    REJECT = "REJECT"
    INVESTIGATE = "INVESTIGATE"


class Outcome(StrEnum):
    """What happens next: a proposal for the human, or an escalation (no valid action)."""

    PROPOSE = "PROPOSE"
    ESCALATE = "ESCALATE"


class FlagSeverity(StrEnum):
    WARNING = "warning"  # decide anyway, mention it
    BLOCKING = "blocking"  # data untrustworthy -> INVESTIGATE
    ESCALATE = "escalate"  # no safe action possible -> ESCALATE


class ConstraintCode(StrEnum):
    """Hard constraints (KB D18): never bypassable by a reason."""

    BUDGET = "budget"
    STORAGE = "storage"
    SHELF_LIFE = "shelf_life"
    MOQ = "moq"
    CASE_PACK = "case_pack"


class PoStatus(StrEnum):
    """Status of a purchase order in our own records (open POs feed the calculator)."""

    PLACED = "placed"
    CONFIRMED = "confirmed"
    RECEIVED = "received"
    CANCELLED = "cancelled"


class ErpPoStatus(StrEnum):
    """Status of a purchase order inside the (mock) ERP."""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
