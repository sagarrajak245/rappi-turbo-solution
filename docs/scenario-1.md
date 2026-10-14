# Scenario 1 — formula rulings and case expectations

The deterministic core (`backend/app/modules/planning`, `backend/app/modules/validation`) decides every Scenario 1 case without an LLM. This page records how ambiguous parts of the spec were resolved. Every expected number in the case table (`backend/app/scenarios/scenario1.py`) was derived by hand from these rules, cross-checked with an independent script, and never taken from the code's output.

## Verdict vs outcome

- **Verdict** describes the recommendation and is one of `ACCEPT`, `MODIFY`, `REJECT`, `INVESTIGATE`.
- **Outcome** says what happens next: `PROPOSE` to the buyer, or `ESCALATE` when no valid action exists.
- **Data-quality flags** have one of three severities: `warning`, `blocking`, `escalate`.

Rules apply in this order. The first that matches decides:

1. A blocking flag → `INVESTIGATE`, with no quantity.
2. An escalate flag (inactive supplier), or no valid PO under the caps → `ESCALATE`, with resolution options.
3. Need = 0 → `REJECT 0`. This takes priority over the accept rule.
4. The accept rule holds → `ACCEPT` the rec.
5. Otherwise → `MODIFY`.

When a cap limits the order below the need but the cap still meets the MOQ, the result is a partial order: `MODIFY` to the cap, flagged `partial_coverage`. It is `ACCEPT` if the cap equals the rec.

## Formulas

| Step | Ruling |
|---|---|
| Protection period | P = lead time L + order cycle R. R defaults to 7. |
| Demand | Forecast for days 1..P, where day 1 is tomorrow. With no forecast, use the 28-day sales average (`no_forecast` warning). With neither, `no_demand_data` is blocking. |
| Safety stock | `ceil(z · σ · √P)`, with z = 1.65 at 95% and σ the **population** stdev of 28 days of sales. Values are rounded with `round(x, 9)` before any ceil/floor. |
| Inventory position | on_hand − reserved + open POs with ETA in [today, today+P]. Overdue POs are excluded and flagged `overdue_po`. Cancelled and received POs never count. |
| Need | N = max(0, D_P + SS − IP). Q = N rounded up to the MOQ, then up to the case pack. |
| Accept rule | The rec must be feasible: a case multiple, at least the MOQ, and within every cap. Then accept if \|rec − Q\| ≤ max(1 case, 10 % of rec). |
| Budget cap | `floor(max(0, amount − committed) / unit cost)`, floored to a case. A zero-cost item has no budget cap. |
| Storage cap | Zone capacity − other SKUs' projected stock at our arrival − our physical stock at arrival, then floored to a case. "Projected stock at arrival" means on_hand (including reserved) + inbound by arrival − forecast × L. Space is measured in `unit_volume` units (default 1). |
| Shelf-life cap | Forecast over the `shelf_life − 1` sellable days after arrival, minus max(0, stock at arrival), floored to a case. |
| Stock-out before arrival | Stock at arrival = on_hand − reserved + inbound by arrival − forecast × L. A value below 0 raises the `stockout_before_arrival` warning. |

## Data-quality checks

| Check | Severity |
|---|---|
| Snapshot older than 24 h. Exactly 24 h is still fresh. | blocking |
| Negative on-hand | blocking |
| No forecast, sales available | warning (sales fallback) |
| No forecast and no sales | blocking |
| Overdue open PO | warning (excluded from IP) |
| Supplier inactive | escalate |
| Forecast vs sales gap `\|f̄ − s̄\| / s̄`: over 50 % is blocking (strictly greater; s̄ = 0 with f̄ > 0 is also blocking), over 25 % is a warning | blocking / warning |
| Supplier/product notes that look like instructions | warning. The text is never forwarded. |

## Validator

- **Hard constraints are never bypassed by a reason.** These are budget, storage, shelf life, MOQ and case pack. Trying to override one is reported as an issue.
- **Soft policies** are max 21 days of cover and max 50 % deviation from the rec. A decision may break one only with an override that carries a reason, and the override is recorded.
- **Consistency:**
  - `REJECT` must order 0.
  - `ACCEPT` must order the rec.
  - `MODIFY` must order a positive quantity that differs from the rec.
  - `INVESTIGATE` proposes no quantity.
- Any quantity different from the calculated baseline needs a deviation reason.
- If the case pack is broken, the validator suggests the nearest valid quantities. For example, 805 with a case of 48 → 768 / 816.

## Cases

Every case is derived step by step in a comment next to it in `scenario1.py`.

**Decision cases**

| Case | Expected | Flags |
|---|---|---|
| C1 | ACCEPT 800 | |
| C2 | REJECT 0 | |
| C3 | MODIFY 300 | |
| C4 | MODIFY 1128 | |
| C5 | MODIFY 150 | |
| C6 | MODIFY 816 | |
| C7 | MODIFY 500 | partial_coverage (budget) |
| C8 | MODIFY 400 | partial_coverage (storage) |
| C9 | ESCALATE, with options | |
| C10 | MODIFY 210 | overdue_po |
| C11 | MODIFY 204 | partial_coverage (shelf life) |

**Data-quality cases**

| Case | Expected | Flags |
|---|---|---|
| Q1 | INVESTIGATE | stale_snapshot |
| Q2 | INVESTIGATE | negative_on_hand |
| Q3a | MODIFY 216 | no_forecast |
| Q3b | INVESTIGATE | no_demand_data |
| Q4 | MODIFY 400 | overdue_po |
| Q5 | ESCALATE | supplier_inactive |
| Q6 | INVESTIGATE | forecast_sales_gap |
| Q7 | MODIFY 180 | suspicious_text |

**Feedback-loop cases**

F1–F6 have clean `ACCEPT` baselines. The surprise comes from the mock ERP afterwards:

| Case | ERP behaviour | Expected follow-up |
|---|---|---|
| F1 | price +8 % | re-plan to 210 |
| F2 | case pack 12 | re-plan to 144 |
| F3 | timeout after create | retry returns the same PO |
| F4 | rejected on submit | |
| F5 | ETA +3 days | stock-out before arrival |
| F6 | ERP quantity mismatch after submit | |

`tests/unit/test_scenario1_end_to_end.py` runs every case through data quality → calculator → validator and asserts the verdict, quantity, outcome and exact flag set.
