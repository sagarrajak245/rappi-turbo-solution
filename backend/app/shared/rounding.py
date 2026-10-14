"""Rounding helpers shared by the calculator, options and validator.

Float arithmetic produces values like 3.0000000000000004; rounding to 9 decimals first
keeps an exact multiple from being bumped up (or down) by one.
"""

import math

_PRECISION = 9


def safe_ceil(value: float) -> int:
    return math.ceil(round(value, _PRECISION))


def safe_floor(value: float) -> int:
    return math.floor(round(value, _PRECISION))


def _check_case(case_pack: int) -> None:
    if case_pack <= 0:
        raise ValueError(f"case pack must be positive, got {case_pack}")


def ceil_to_case(qty: int, case_pack: int) -> int:
    """Smallest multiple of case_pack that is >= qty."""
    _check_case(case_pack)
    return -(-qty // case_pack) * case_pack


def floor_to_case(qty: int, case_pack: int) -> int:
    """Largest multiple of case_pack that is <= qty."""
    _check_case(case_pack)
    return (qty // case_pack) * case_pack
