"""Independent re-check of a proposed quantity against the hard limits.

This deliberately does not reuse the validator: it takes the calculator's caps, the MOQ and the
case pack directly, so a bug or a missing check in the agent's own validation shows up here.
"""

from collections.abc import Mapping
from typing import Any


def hard_violations(
    *, qty: int | None, caps: Mapping[Any, int], moq: int, case_pack: int
) -> list[str]:
    if not qty:  # no order proposed (None) or an explicit zero: nothing can be violated
        return []
    found: list[str] = []
    for code, cap in caps.items():
        if qty > cap:
            found.append(f"qty {qty} exceeds cap {getattr(code, 'value', code)}={cap}")
    if qty < moq:
        found.append(f"qty {qty} is below the MOQ {moq}")
    if case_pack > 0 and qty % case_pack:
        found.append(f"qty {qty} is not a multiple of the case pack {case_pack}")
    return found
