"""Building blocks of a scenario case table.

Everything is expressed relative to "today" (day offsets, hours of age) so the same table can be
seeded on any date and still produce the same decisions.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.shared.enums import FlagCode, Outcome, PoStatus, Verdict

SALES_WINDOW_DAYS = 28
FORECAST_HORIZON_DAYS = 28


@dataclass(frozen=True)
class SupplierSpec:
    code: str
    name: str
    active: bool = True
    notes: str | None = None


@dataclass(frozen=True)
class ProductSpec:
    """A product and the commercial terms of its (single) supplier."""

    sku: str
    name: str
    category: str
    zone: str
    supplier: str
    unit_cost_inr: Decimal
    moq: int
    case_pack: int
    lead_time_days: int
    order_cycle_days: int | None = None  # None -> config default (7)
    perishable: bool = False
    shelf_life_days: int | None = None
    unit_volume: Decimal = Decimal("1")
    notes: str | None = None


@dataclass(frozen=True)
class OpenPo:
    qty: int
    eta_offset: int  # days from today; negative = overdue
    status: PoStatus = PoStatus.PLACED


@dataclass(frozen=True)
class Neighbour:
    """Another SKU stored in the same zone at the same node. Only its load matters."""

    sku: str
    on_hand: int
    forecast_daily: int


@dataclass(frozen=True)
class ErpSurprise:
    behaviour: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Expected:
    """Baseline decision of the deterministic pipeline (data quality -> calculator -> validator).

    qty is None when no order quantity is proposed (INVESTIGATE or ESCALATE).
    flags is the exact set of flags the pipeline must raise.
    """

    verdict: Verdict | None
    qty: int | None
    outcome: Outcome = Outcome.PROPOSE
    flags: frozenset[FlagCode] = frozenset()


@dataclass(frozen=True)
class CaseSpec:
    id: str
    title: str
    sku: str
    node: str
    rec: int
    on_hand: int
    reserved: int
    expected: Expected
    forecast_daily: int | None = None  # None -> no forecast rows
    sales_mean: int | None = None  # None -> no sales rows
    sales_sigma: int = 0
    snapshot_age_hours: int = 2
    open_pos: tuple[OpenPo, ...] = ()
    zone_neighbours: tuple[Neighbour, ...] = ()
    erp: ErpSurprise | None = None


def sales_series(mean: int, sigma: int, days: int = SALES_WINDOW_DAYS) -> tuple[int, ...]:
    """Alternating mean-sigma / mean+sigma: the mean is exact and the population stdev is sigma."""
    if sigma > mean:
        raise ValueError("sigma larger than mean would need negative sales")
    if days % 2:
        raise ValueError("days must be even so the series stays balanced")
    return tuple(mean - sigma if i % 2 == 0 else mean + sigma for i in range(days))
