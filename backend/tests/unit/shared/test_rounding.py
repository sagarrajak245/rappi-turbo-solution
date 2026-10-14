import pytest

from app.shared.rounding import ceil_to_case, floor_to_case, safe_ceil, safe_floor


def test_safe_ceil_ignores_float_noise_on_exact_values() -> None:
    assert safe_ceil(0.1 * 3 * 10) == 3  # 3.0000000000000004 must not become 4
    assert safe_ceil(54.72) == 55


def test_safe_floor_ignores_float_noise() -> None:
    assert safe_floor(2.9999999999999996) == 3
    assert safe_floor(625.0) == 625


@pytest.mark.parametrize(
    ("qty", "case", "expected"),
    [(205, 10, 210), (210, 10, 210), (0, 10, 0), (761, 48, 768), (769, 48, 816)],
)
def test_ceil_to_case(qty: int, case: int, expected: int) -> None:
    assert ceil_to_case(qty, case) == expected


@pytest.mark.parametrize(("qty", "case", "expected"), [(625, 10, 620), (9, 10, 0), (816, 48, 816)])
def test_floor_to_case(qty: int, case: int, expected: int) -> None:
    assert floor_to_case(qty, case) == expected


def test_case_pack_must_be_positive() -> None:
    with pytest.raises(ValueError, match="case pack"):
        ceil_to_case(10, 0)
