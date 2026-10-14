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


class FlagCode(StrEnum):
    """Facts worth telling the buyer about. Severity is decided by the validation policy."""

    STALE_SNAPSHOT = "stale_snapshot"
    NEGATIVE_ON_HAND = "negative_on_hand"
    NO_FORECAST = "no_forecast"  # fell back to the sales average
    NO_DEMAND_DATA = "no_demand_data"  # no forecast and no sales either
    OVERDUE_PO = "overdue_po"
    SUPPLIER_INACTIVE = "supplier_inactive"
    FORECAST_SALES_GAP = "forecast_sales_gap"
    SUSPICIOUS_TEXT = "suspicious_text"  # free text that looks like an instruction (Q7)
    STOCKOUT_BEFORE_ARRIVAL = "stockout_before_arrival"
    PARTIAL_COVERAGE = "partial_coverage"  # a cap forced less than the need


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


class UserRole(StrEnum):
    BUYER = "buyer"
    ADMIN = "admin"


class RunStatus(StrEnum):
    """Lifecycle of one agent run (KB §3.2): decide, wait for the buyer, execute in the ERP."""

    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING = "executing"
    COMPLETED = "completed"
    REJECTED = "rejected"
    ACKNOWLEDGED = "acknowledged"
    ESCALATED = "escalated"
    NEEDS_HUMAN = "needs_human"
    FAILED = "failed"
