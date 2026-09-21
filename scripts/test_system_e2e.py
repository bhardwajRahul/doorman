#!/usr/bin/env python3
"""Offline regression tests for the generated system E2E contract."""

from __future__ import annotations

import unittest

from scripts import system_e2e


class SystemE2EContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ledger = system_e2e.validate_contract()

    def test_union_inventory_and_every_cell_has_a_disposition(self) -> None:
        contract = system_e2e.load_json(system_e2e.SYSTEM / "contract.json")
        self.assertEqual(len(self.ledger["operations"]), 178)
        self.assertEqual(len(self.ledger["dashboard_routes"]), 50)
        self.assertEqual(
            len(self.ledger["operation_cells"]),
            178 * len(contract["operation_classes"]),
        )
        self.assertTrue(
            all(
                cell["disposition"] in {"executable", "not_applicable"}
                for cell in self.ledger["operation_cells"]
            )
        )

    def test_generated_rows_cover_every_valid_pair(self) -> None:
        pairwise = system_e2e.load_json(system_e2e.SYSTEM / "pairwise.json")
        covered = set().union(
            *(system_e2e.covered_pairs(row) for row in self.ledger["pairwise_rows"])
        )
        self.assertEqual(system_e2e.valid_pairs(pairwise) - covered, set())
        self.assertGreaterEqual(len(self.ledger["pairwise_rows"]), 40)

    def test_every_scenario_maps_features_and_expected_evidence(self) -> None:
        feature_ids = set(self.ledger["features"])
        scenario_ids: set[str] = set()
        mapped: set[str] = set()
        for scenario in self.ledger["scenarios"]:
            self.assertNotIn(scenario["id"], scenario_ids)
            scenario_ids.add(scenario["id"])
            self.assertTrue(scenario["features"])
            self.assertTrue(scenario["expected"])
            mapped.update(scenario["features"])
        self.assertEqual(feature_ids - mapped, set())

    def test_plan_is_deterministic_and_does_not_start_services(self) -> None:
        first = system_e2e.plan("comprehensive")
        second = system_e2e.plan("comprehensive")
        self.assertEqual(first, second)
        self.assertEqual(first["topologies"], ["memory", "external", "two-node"])
        self.assertEqual(first["independent_upstreams"], 10)


if __name__ == "__main__":
    unittest.main()
