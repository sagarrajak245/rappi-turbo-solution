"""INR money helpers. Money is always Decimal, quantized to paise."""

from decimal import ROUND_HALF_UP, Decimal

PAISE = Decimal("0.01")


def to_inr(value: Decimal | int | float | str) -> Decimal:
    # str() first so a float like 0.125 is taken at face value, not its binary approximation.
    return Decimal(str(value)).quantize(PAISE, rounding=ROUND_HALF_UP)


def format_inr(amount: Decimal) -> str:
    """Indian digit grouping: ₹1,25,000 / ₹12,34,567.50. Paise shown only when non-zero."""
    amount = to_inr(amount)
    sign = "-" if amount < 0 else ""
    rupees, paise = f"{abs(amount):.2f}".split(".")
    head, tail = rupees[:-3], rupees[-3:]
    groups: list[str] = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    grouped = ",".join([*groups, tail])
    return f"{sign}₹{grouped}" + (f".{paise}" if paise != "00" else "")
