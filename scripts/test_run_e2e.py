#!/usr/bin/env python3
"""Runner control-flow tests; no Docker daemon, network, or Rust build required."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import run_e2e


IMAGE = "sha256:" + "a" * 64


class E2ERunnerTests(unittest.TestCase):
    def release_environment(self, directory: Path) -> dict[str, str]:
        command = directory / "rehearse.sh"
        command.write_text("#!/bin/sh\nexit 1\n")
        command.chmod(0o700)
        scenarios = directory / "scenarios.json"
        scenarios.write_text(json.dumps([
            {"name": name, "python_url": "http://localhost:3102/" + name,
             "rust_url": "http://localhost:3101/" + name}
            for name in ("rest", "graphql", "soap", "grpc")
        ]))
        return {
            **{key: sorted(values)[0] for key, values in run_e2e.release_check.REQUIRED_ENVIRONMENT.items()},
            **{key: "long-non-placeholder-value-1234567890" for key in run_e2e.release_check.REQUIRED_VALUES},
            "PYTHON_PARITY_URL": "http://localhost:3102", "RUST_PARITY_URL": "http://localhost:3101",
            "PYTHON_PARITY_PID": "123", "RUST_PARITY_PID": "456",
            "PARITY_PERF_SCENARIOS": str(scenarios), "RELEASE_OPERATIONS_COMMAND": str(command),
        }

    def test_release_preflight_rejects_missing_hook_and_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.object(run_e2e.benchmark_parity, "rss_bytes", return_value=10):
            env = self.release_environment(Path(directory))
            run_e2e.validate_release_inputs(env)
            with self.assertRaisesRegex(ValueError, "RELEASE_OPERATIONS_COMMAND"):
                run_e2e.validate_release_inputs({**env, "RELEASE_OPERATIONS_COMMAND": ""})
            with self.assertRaisesRegex(ValueError, "must differ"):
                run_e2e.validate_release_inputs({**env, "RUST_PARITY_PID": "123"})
            with self.assertRaisesRegex(ValueError, "must differ"):
                run_e2e.validate_release_inputs({**env, "RUST_PARITY_URL": "http://localhost:3102/"})
            with self.assertRaisesRegex(ValueError, "JWT_SECRET_KEY"):
                run_e2e.validate_release_inputs({**env, "JWT_SECRET_KEY": "too-short"})
            path = Path(env["PARITY_PERF_SCENARIOS"])
            scenarios = json.loads(path.read_text())
            path.write_text(json.dumps(scenarios[:1]))
            with self.assertRaisesRegex(ValueError, "rest, graphql, soap, and grpc"):
                run_e2e.validate_release_inputs(env)

    def test_release_preflight_rejects_dead_pids(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.object(run_e2e.benchmark_parity, "rss_bytes", return_value=0):
            with self.assertRaisesRegex(ValueError, "PYTHON_PARITY_PID"):
                run_e2e.validate_release_inputs(self.release_environment(Path(directory)))

    def test_command_failure_keeps_log_and_status_without_dumping_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner = run_e2e.Runner(Path(directory), {**os.environ, "JWT_SECRET_KEY": "do-not-log-me"}, False)
            with self.assertRaisesRegex(RuntimeError, "exit 7"):
                runner.run("fails", [sys.executable, "-c", "print('diagnostic'); raise SystemExit(7)"])
            summary = json.loads((Path(directory) / "summary.json").read_text())
            self.assertEqual(summary["stages"][0]["status"], "failed")
            self.assertEqual(summary["stages"][0]["exit_code"], 7)
            self.assertEqual((Path(directory) / "01-fails.log").read_text(), "diagnostic\n")
            self.assertNotIn("do-not-log-me", json.dumps(summary))

    def test_cancellation_terminates_the_owned_subprocess_group(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner = run_e2e.Runner(Path(directory), {}, False)
            with patch.object(run_e2e.subprocess, "Popen") as popen, \
                 patch.object(run_e2e.os, "killpg") as killpg:
                child = popen.return_value.__enter__.return_value
                child.pid = 12345
                child.stdout.__iter__.side_effect = KeyboardInterrupt
                with self.assertRaises(KeyboardInterrupt):
                    runner.run("interrupted", ["test-command"])
                killpg.assert_called_once_with(12345, run_e2e.signal.SIGTERM)
                self.assertTrue(popen.call_args.kwargs["start_new_session"])
                self.assertEqual(runner.summary["stages"][0]["status"], "failed")

    def test_candidate_uses_loopback_and_fresh_credentials_not_user_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner = run_e2e.Runner(Path(directory), {"DOORMAN_ADMIN_PASSWORD": "user-secret"}, False)
            runner.image_id = IMAGE
            with patch.object(runner, "run") as run, \
                 patch.object(runner, "docker_output", side_effect=["127.0.0.1:43210", "127.0.0.1:43211"]), \
                 patch.object(runner, "wait_http"):
                runner.candidate_smoke()
            start = run.call_args_list[0]
            self.assertEqual(start.args[1][-1], IMAGE)
            self.assertNotIn("--volume", start.args[1])
            self.assertNotIn("--mount", start.args[1])
            self.assertIn("127.0.0.1::3001", start.args[1])
            self.assertNotEqual(start.args[2]["DOORMAN_ADMIN_PASSWORD"], "user-secret")
            self.assertEqual(start.args[2]["MEM_OR_EXTERNAL"], "MEM")
            self.assertNotIn(start.args[2]["DOORMAN_ADMIN_PASSWORD"], start.args[1])
            live = run.call_args_list[1]
            self.assertIn("--ignored", live.args[1])
            self.assertEqual(live.args[2]["LIVE_SERVER_URL"], "http://127.0.0.1:43210")

    def fake_run(self, runner: run_e2e.Runner, calls: list[str], *, wrong_image: bool = False, errors: float = 0):
        def run(name, command, env=None):
            calls.append(name)
            if name == "image-build":
                (runner.evidence / "image-id.txt").write_text(IMAGE)
            elif name == "operations-rehearsals":
                (runner.evidence / "operations.json").write_text(json.dumps({
                    "image_id": "wrong" if wrong_image else IMAGE,
                }))
            elif name == "performance":
                (runner.evidence / "performance.json").write_text(json.dumps({"profiles": {
                    "rest": {"measurements": {"python": [{"error_rate": errors}],
                                               "rust": [{"error_rate": errors}]}}
                }}))
        return run

    def test_local_plan_runs_storage_and_image_but_does_not_claim_release(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner = run_e2e.Runner(Path(directory), {}, False)
            calls = []
            with patch.object(runner, "run", side_effect=self.fake_run(runner, calls)), \
                 patch.object(runner, "candidate_smoke") as smoke, patch.object(runner, "cleanup"):
                runner.execute()
            self.assertEqual(calls, ["source-state", "source-commit", "runner-tests", "parity-inventory",
                                     "rust-checks", "frontend-build", "external-storage", "image-build"])
            smoke.assert_called_once()
            self.assertEqual(runner.summary["mode"], "tests")
            self.assertEqual(runner.env["RELEASE_IMAGE_ID"], IMAGE)

    def test_full_release_runs_every_gate_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner = run_e2e.Runner(Path(directory), {"RELEASE_OPERATIONS_COMMAND": "/test/hook"}, True)
            calls = []
            with patch.object(runner, "run", side_effect=self.fake_run(runner, calls)), \
                 patch.object(runner, "candidate_smoke"), patch.object(runner, "cleanup"):
                runner.execute()
            self.assertEqual(calls[-4:], ["operations-rehearsals", "differential", "performance", "release-check"])

    def test_release_rejects_another_image_or_equally_broken_benchmarks(self) -> None:
        for wrong_image, errors, message in [(True, 0, "RELEASE_IMAGE_ID"), (False, 1, "successful requests")]:
            with self.subTest(message=message), tempfile.TemporaryDirectory() as directory:
                runner = run_e2e.Runner(Path(directory), {"RELEASE_OPERATIONS_COMMAND": "/test/hook"}, True)
                calls = []
                with patch.object(runner, "run", side_effect=self.fake_run(runner, calls, wrong_image=wrong_image, errors=errors)), \
                     patch.object(runner, "candidate_smoke"), patch.object(runner, "cleanup"):
                    with self.assertRaisesRegex(RuntimeError, message):
                        runner.execute()
                self.assertNotIn("release-check", calls)

    def test_fail_fast_before_later_builds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner = run_e2e.Runner(Path(directory), {}, False)
            calls = []

            def run(name, command, env=None):
                calls.append(name)
                if name == "rust-checks":
                    raise RuntimeError("test failed")

            with patch.object(runner, "run", side_effect=run), self.assertRaisesRegex(RuntimeError, "test failed"):
                runner.execute()
            self.assertNotIn("frontend-build", calls)

    def test_cleanup_only_removes_owned_container(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner = run_e2e.Runner(Path(directory), {}, False)
            runner.container = "doorman-e2e-test-owned"
            with patch.object(run_e2e.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as execute:
                runner.cleanup()
            self.assertEqual(execute.call_args_list[0].args[0], ["docker", "logs", "doorman-e2e-test-owned"])
            self.assertEqual(execute.call_args_list[1].args[0], ["docker", "rm", "--force", "doorman-e2e-test-owned"])
            self.assertIsNone(runner.container)

    def test_main_cleans_up_and_marks_failure_on_interrupt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env = {"E2E_EVIDENCE_ROOT": directory}
            with patch.object(sys, "argv", ["run_e2e.py"]), \
                 patch.object(run_e2e, "child_environment", return_value=env), \
                 patch.object(run_e2e, "preflight"), patch.object(run_e2e.signal, "signal"), \
                 patch.object(run_e2e.Runner, "execute", side_effect=KeyboardInterrupt), \
                 patch.object(run_e2e.Runner, "cleanup") as cleanup:
                self.assertEqual(run_e2e.main(), 130)
            cleanup.assert_called_once()
            report = next(Path(directory).glob("*/summary.json"))
            self.assertEqual(json.loads(report.read_text())["status"], "failed")

    def test_plan_is_non_mutating(self) -> None:
        with patch.object(sys, "argv", ["run_e2e.py", "--release", "--plan"]), \
             patch.object(run_e2e, "preflight") as preflight, \
             patch.object(run_e2e.tempfile, "mkdtemp") as mkdir:
            self.assertEqual(run_e2e.main(), 0)
        preflight.assert_not_called()
        mkdir.assert_not_called()


if __name__ == "__main__":
    unittest.main()
