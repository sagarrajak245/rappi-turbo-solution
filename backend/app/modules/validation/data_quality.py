"""Data-quality checks: can the numbers behind a decision be trusted? Pure, no I/O.

Severity decides what happens next: blocking -> INVESTIGATE, escalate -> ESCALATE, warning ->
decide anyway and mention it. Free-text notes are scanned for instruction-like text (Q7) but
never quoted back, so they cannot reach a prompt as an instruction.
"""

import re
from datetime import datetime, timedelta
from statistics import fmean

from app.core.config import DataQualitySettings
from app.modules.planning.schemas import Flag, PlanningInput
from app.shared.enums import FlagCode, FlagSeverity

_PRECISION = 9


def _gap_flag(inp: PlanningInput, dq: DataQualitySettings) -> Flag | None:
    f_mean, s_mean = fmean(inp.forecast), fmean(inp.sales)
    if s_mean == 0:
        if f_mean == 0:
            return None
        return Flag(
            code=FlagCode.FORECAST_SALES_GAP,
            severity=FlagSeverity.BLOCKING,
            message=f"Forecast {f_mean:g}/day but no sales in the window",
        )
    gap = round(abs(f_mean - s_mean) / s_mean, _PRECISION)
    if gap > dq.forecast_sales_gap_block_pct:
        severity = FlagSeverity.BLOCKING
    elif gap > dq.forecast_sales_gap_warn_pct:
        severity = FlagSeverity.WARNING
    else:
        return None
    return Flag(
        code=FlagCode.FORECAST_SALES_GAP,
        severity=severity,
        message=f"Forecast {f_mean:g}/day vs sales {s_mean:g}/day ({gap:.0%} apart)",
    )


def _suspicious(inp: PlanningInput, dq: DataQualitySettings) -> list[str]:
    patterns = [re.compile(p, re.IGNORECASE) for p in dq.injection_patterns]
    fields = {"supplier notes": inp.supplier_notes, "product notes": inp.product_notes}
    return [name for name, text in fields.items() if text and any(p.search(text) for p in patterns)]


def check_data_quality(
    inp: PlanningInput, now: datetime, dq: DataQualitySettings
) -> tuple[Flag, ...]:
    flags: list[Flag] = []

    def add(code: FlagCode, severity: FlagSeverity, message: str) -> None:
        flags.append(Flag(code=code, severity=severity, message=message))

    age = now - inp.snapshot_as_of
    if age > timedelta(hours=dq.snapshot_max_age_hours):
        hours = age.total_seconds() / 3600
        add(FlagCode.STALE_SNAPSHOT, FlagSeverity.BLOCKING, f"Stock snapshot is {hours:.1f}h old")
    if inp.on_hand < 0:
        add(FlagCode.NEGATIVE_ON_HAND, FlagSeverity.BLOCKING, f"On hand is {inp.on_hand}")
    if not inp.forecast:
        if inp.sales:
            add(FlagCode.NO_FORECAST, FlagSeverity.WARNING, "No forecast; using sales average")
        else:
            add(FlagCode.NO_DEMAND_DATA, FlagSeverity.BLOCKING, "No forecast and no sales")
    overdue = [po.po_number for po in inp.inbound if po.eta_offset < 0]
    if overdue:
        add(
            FlagCode.OVERDUE_PO,
            FlagSeverity.WARNING,
            f"Overdue PO not counted as inbound: {', '.join(overdue)}",
        )
    if not inp.supplier_active:
        add(
            FlagCode.SUPPLIER_INACTIVE,
            FlagSeverity.ESCALATE,
            f"Supplier {inp.supplier_code} is inactive",
        )
    if inp.forecast and inp.sales and (gap := _gap_flag(inp, dq)) is not None:
        flags.append(gap)
    for field in _suspicious(inp, dq):
        add(
            FlagCode.SUSPICIOUS_TEXT,
            FlagSeverity.WARNING,
            f"Instruction-like text in {field}; treated as data and ignored",
        )
    return tuple(flags)
