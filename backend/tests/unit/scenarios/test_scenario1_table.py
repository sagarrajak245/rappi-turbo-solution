import statistics

import pytest

from app.scenarios.scenario1 import CASES, NODES, PRODUCTS, SUPPLIERS, ZONE_CAPACITY
from app.scenarios.types import sales_series
from app.shared.enums import Outcome, Verdict


def test_sales_series_has_exact_mean_and_population_stdev() -> None:
    series = sales_series(40, 10)
    assert len(series) == 28
    assert statistics.fmean(series) == 40
    assert statistics.pstdev(series) == 10


def test_sales_series_refuses_negative_days() -> None:
    with pytest.raises(ValueError):
        sales_series(5, 6)


def test_every_case_is_its_own_sku_node_pair() -> None:
    pairs = [(c.sku, c.node) for c in CASES]
    neighbours = [(n.sku, c.node) for c in CASES for n in c.zone_neighbours]
    assert len(set(pairs + neighbours)) == len(pairs) + len(neighbours)


def test_case_table_references_known_entities() -> None:
    for case in CASES:
        assert case.node in NODES, case.id
        assert case.sku in PRODUCTS, case.id
        assert PRODUCTS[case.sku].supplier in SUPPLIERS, case.id
        assert all(n.sku in PRODUCTS for n in case.zone_neighbours), case.id
    assert all(node in NODES for node, _ in ZONE_CAPACITY)


def test_expected_values_are_coherent() -> None:
    for case in CASES:
        exp = case.expected
        if exp.outcome is Outcome.ESCALATE or exp.verdict is Verdict.INVESTIGATE:
            assert exp.qty is None, case.id
        elif exp.verdict is Verdict.REJECT:
            assert exp.qty == 0, case.id
        else:
            assert exp.qty is not None and exp.qty > 0, case.id
            terms = PRODUCTS[case.sku]
            assert exp.qty % terms.case_pack == 0 and exp.qty >= terms.moq, case.id
        if exp.verdict is Verdict.ACCEPT:
            assert exp.qty == case.rec, case.id


def test_all_spec_cases_are_present() -> None:
    ids = {c.id for c in CASES}
    expected = {f"C{i}" for i in range(1, 12)} | {f"F{i}" for i in range(1, 7)}
    expected |= {"Q1", "Q2", "Q3a", "Q3b", "Q4", "Q5", "Q6", "Q7"}
    assert ids == expected
