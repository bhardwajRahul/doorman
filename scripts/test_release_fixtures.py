#!/usr/bin/env python3
"""Unit tests for the owned release fixture contract; Docker is not required."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.release_fixtures import PROTO, ReleaseFixtures, performance_scenarios


IMAGE = "sha256:" + "a" * 64


class ReleaseFixtureTests(unittest.TestCase):
    def test_protocol_scenarios_are_complete_and_target_each_runtime(self) -> None:
        scenarios = performance_scenarios("http://python", "http://rust")
        self.assertEqual(
            [scenario["name"] for scenario in scenarios],
            ["rest", "graphql", "soap", "grpc"],
        )
        for scenario in scenarios:
            self.assertTrue(scenario["python_url"].startswith("http://python/"))
            self.assertTrue(scenario["rust_url"].startswith("http://rust/"))
        grpc_body = json.loads(scenarios[-1]["request"]["body"])
        self.assertEqual(grpc_body["method"], "Resource.Create")
        self.assertIn("service Resource", PROTO)
        self.assertIn("rpc Create", PROTO)

    def test_fixture_requires_an_immutable_image_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "immutable Rust image ID"):
                ReleaseFixtures(Path(directory), "doorman:latest", {})

    def test_cutover_ownership_command_is_scoped_to_the_owned_volume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch("scripts.release_fixtures.free_port", side_effect=[3101, 3102]):
                fixture = ReleaseFixtures(Path(directory), IMAGE, {})
            with patch.object(fixture, "command") as command:
                fixture.prepare_data_volume_for_rust("owned-data")
            args = command.call_args.args[0]
            self.assertEqual(args[:3], ["docker", "run", "--rm"])
            self.assertIn("owned-data:/app/data", args)
            self.assertEqual(args[-3:], ["-R", "10001:10001", "/app/data"])
            self.assertIn(IMAGE, args)

    def test_comparison_pair_exports_separate_tokens_without_writing_them_to_scenarios(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("scripts.release_fixtures.free_port", side_effect=[3101, 3102]):
                fixture = ReleaseFixtures(root, IMAGE, {})
            with (
                patch.object(fixture, "create_volume", side_effect=["python-data", "rust-data"]),
                patch.object(
                    fixture,
                    "start_gateway",
                    side_effect=[
                        ("python-container", "http://python"),
                        ("rust-container", "http://rust"),
                    ],
                ),
                patch.object(fixture, "seed"),
                patch.object(fixture, "login", side_effect=["python-secret", "rust-secret"]),
                patch.object(fixture, "container_pid", side_effect=["101", "202"]),
            ):
                values = fixture.start_comparison_pair()
            self.assertEqual(values["PYTHON_PARITY_TOKEN"], "python-secret")
            self.assertEqual(values["RUST_PARITY_TOKEN"], "rust-secret")
            scenarios = Path(values["PARITY_PERF_SCENARIOS"]).read_text()
            self.assertNotIn("python-secret", scenarios)
            self.assertNotIn("rust-secret", scenarios)


if __name__ == "__main__":
    unittest.main()
