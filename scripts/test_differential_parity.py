#!/usr/bin/env python3
"""Unit tests for the generated operation-level differential inventory."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.differential_parity import load_openapi, operation_cases, operation_signature


ROOT = Path(__file__).resolve().parents[1]


class DifferentialParityTests(unittest.TestCase):
    def test_operation_inventory_covers_the_pinned_surface_once(self) -> None:
        _raw, document = load_openapi(
            ROOT / "parity/openapi/python-openapi.json.gz.b64"
        )
        cases = operation_cases(document)
        expected = json.loads((ROOT / "parity/reference.json").read_text())["surface"][
            "openapi_operations"
        ]
        self.assertEqual(len(cases), expected)
        self.assertEqual(len({case["name"] for case in cases}), expected)
        self.assertEqual(
            cases[-1]["name"], "operation:POST:/platform/authorization/invalidate"
        )
        for case in cases:
            self.assertNotIn("{", case["path"])
            self.assertNotIn("Authorization", case["headers"])

    def test_operation_signature_uses_exact_status_and_media_type(self) -> None:
        self.assertEqual(
            operation_signature(
                {
                    "status": 404,
                    "headers": {
                        "content-type": "Application/JSON; charset=utf-8",
                        "allow": "post, GET",
                    },
                }
            ),
            {"status": 404, "content_type": "application/json", "allow": ["GET", "POST"]},
        )


if __name__ == "__main__":
    unittest.main()
