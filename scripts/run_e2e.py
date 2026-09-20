#!/usr/bin/env python3
"""Sequential local E2E checks, optionally followed by the full release gates.

No production services are started or stopped. Release fixtures/rehearsals are
explicit inputs, not silently skipped checks. See user-docs/TESTS.md.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Support both `python scripts/run_e2e.py` and unittest imports.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import benchmark_parity, release_check


ROOT = Path(__file__).resolve().parents[1]
LOCAL_STAGES = (
    "Runner/checker regression tests",
    "Pinned Python reference and 600-entry coverage ledger",
    "Rust formatting, Clippy, and complete Cargo suite",
    "Frontend dependency install and production build",
    "Isolated MongoDB/Redis integration tests (explicitly enabled)",
    "Candidate Docker image build",
    "Disposable image: backend readiness, frontend HTTP, and live TCP/auth test",
)
RELEASE_STAGES = (
    "Operator-supplied isolated image/restore/cutover/rollback rehearsal command",
    "Python/Rust differential comparison",
    "REST/GraphQL/SOAP/gRPC performance comparison",
    "Production configuration and fresh release evidence validation",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def child_environment() -> dict[str, str]:
    env = dict(os.environ)
    cargo_bin = str(Path.home() / ".cargo" / "bin")
    env["PATH"] = cargo_bin + os.pathsep + env.get("PATH", "")
    # Never inherit recursive make parallelism or a user-selected Rust test filter.
    for key in ("MAKEFLAGS", "MFLAGS", "CARGO", "DOORMAN_EXTERNAL_STORAGE_TEST"):
        env.pop(key, None)
    env["CARGO"] = shutil.which("cargo", path=env["PATH"]) or "cargo"
    env["NEXT_TELEMETRY_DISABLED"] = "1"
    return env


def validate_release_inputs(env: dict[str, str]) -> None:
    """Validate inputs before paying the cost of builds; never print secrets."""
    reports = {name for name in release_check.REQUIRED_VALUES if name.endswith("REPORT")}
    reports.add("EXTERNAL_STORAGE_LOG")
    for name, allowed in release_check.REQUIRED_ENVIRONMENT.items():
        if env.get(name, "").strip().lower() not in allowed:
            raise ValueError(f"{name} must be one of {', '.join(sorted(allowed))}")
    for name in set(release_check.REQUIRED_VALUES) - reports:
        if env.get(name, "").strip().lower() in release_check.PLACEHOLDERS:
            raise ValueError(f"{name} is required; see user-docs/TESTS.md")
    for name, minimum in (("JWT_SECRET_KEY", 32), ("DOORMAN_ADMIN_PASSWORD", 16),
                          ("MONGO_DB_PASSWORD", 16), ("REDIS_PASSWORD", 16)):
        if len(env[name].strip()) < minimum:
            raise ValueError(f"{name} must be at least {minimum} characters")
    for name in ("PYTHON_PARITY_URL", "RUST_PARITY_URL"):
        if not env.get(name, "").startswith(("http://", "https://")):
            raise ValueError(f"{name} must identify an isolated running fixture server")
    if env["PYTHON_PARITY_URL"].rstrip("/") == env["RUST_PARITY_URL"].rstrip("/"):
        raise ValueError("Python and Rust fixture URLs must differ")
    for name in ("PYTHON_PARITY_PID", "RUST_PARITY_PID"):
        if not env.get(name, "").isdigit() or benchmark_parity.rss_bytes(int(env[name])) <= 0:
            raise ValueError(f"{name} must identify a running process visible in local /proc")
    if env["PYTHON_PARITY_PID"] == env["RUST_PARITY_PID"]:
        raise ValueError("Python and Rust fixture PIDs must differ")
    path = Path(env.get("PARITY_PERF_SCENARIOS", ""))
    if not path.is_file():
        raise ValueError("PARITY_PERF_SCENARIOS must point to a seeded protocol scenario file")
    values = json.loads(path.read_text())
    if not isinstance(values, list):
        raise ValueError("PARITY_PERF_SCENARIOS must contain a JSON array")
    scenarios = [benchmark_parity.normalize_scenario(value) for value in values]
    benchmark_parity.validate_scenarios(scenarios)
    if {case["name"] for case in scenarios} != set(release_check.REQUIRED_PERFORMANCE_PROFILES):
        raise ValueError("Performance scenarios must contain rest, graphql, soap, and grpc")
    command = Path(env.get("RELEASE_OPERATIONS_COMMAND", ""))
    if not command.is_file() or not os.access(command, os.X_OK):
        raise ValueError("RELEASE_OPERATIONS_COMMAND must be an executable rehearsal script; "
                         "see user-docs/OPERATIONS.md (there is no built-in deployment rehearsal)")


def preflight(env: dict[str, str], release: bool) -> None:
    if release:
        validate_release_inputs(env)
    missing = [name for name in ("git", "make", "cargo", "npm", "docker", "bash")
               if not shutil.which(name, path=env["PATH"])]
    if missing:
        raise ValueError("Missing required tools: " + ", ".join(missing))
    for command in (["docker", "info"], ["docker", "compose", "version"],
                    ["cargo", "fmt", "--version"], ["cargo", "clippy", "--version"]):
        result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, timeout=30)
        if result.returncode:
            raise ValueError(f"Prerequisite failed: {' '.join(command)}; "
                             "check Docker access and Rust components (do not run make with sudo)")


class Runner:
    def __init__(self, evidence: Path, env: dict[str, str], release: bool):
        self.evidence = evidence
        self.env = {**env, "E2E_EVIDENCE_DIR": str(evidence),
                    "EXTERNAL_STORAGE_LOG": str(evidence / "external-storage.log"),
                    "DOORMAN_EXTERNAL_STORAGE_LOG_DIR": str(evidence / "external-storage"),
                    "PARITY_REPORT": str(evidence / "differential.json"),
                    "PARITY_PERF_REPORT": str(evidence / "performance.json"),
                    "RELEASE_OPERATIONS_REPORT": str(evidence / "operations.json")}
        self.release = release
        self.container: str | None = None
        self.image_id: str | None = None
        self.summary: dict = {"schema_version": 1, "mode": "release" if release else "tests",
                              "started_at": utc_now(), "status": "running", "stages": []}
        self.save()

    def save(self) -> None:
        (self.evidence / "summary.json").write_text(json.dumps(self.summary, indent=2) + "\n")

    def run(self, name: str, command: list[str], env: dict[str, str] | None = None) -> None:
        logfile = self.evidence / f"{len(self.summary['stages']) + 1:02d}-{name}.log"
        stage = {"name": name, "status": "running", "log": logfile.name, "started_at": utc_now()}
        self.summary["stages"].append(stage)
        self.save()
        print(f"\n==> {name} (log: {logfile})", flush=True)
        try:
            # Own the subprocess group so cancellation also reaches grandchildren.
            # Stream to the console AND persist output; a quiet long-running command
            # still leaves summary.json identifying the active stage.
            with logfile.open("w") as log:
                with subprocess.Popen(command, cwd=ROOT, env=env or self.env, stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT, text=True, errors="replace",
                                      start_new_session=True) as child:
                    try:
                        assert child.stdout is not None
                        for line in child.stdout:
                            log.write(line)
                            log.flush()
                            print(line, end="", flush=True)
                        code = child.wait()
                    except BaseException:
                        try:
                            os.killpg(child.pid, signal.SIGTERM)
                        except ProcessLookupError:
                            pass
                        try:
                            child.wait(timeout=30)
                        except subprocess.TimeoutExpired:
                            os.killpg(child.pid, signal.SIGKILL)
                            child.wait()
                        raise
            stage["exit_code"] = code
            if code:
                raise RuntimeError(f"{name} failed (exit {code}); see {logfile}")
            stage["status"] = "passed"
        except BaseException:
            stage["status"] = "failed"
            raise
        finally:
            stage["finished_at"] = utc_now()
            self.save()

    def docker_output(self, *args: str) -> str:
        result = subprocess.run(["docker", *args], cwd=ROOT, env=self.env, text=True,
                                capture_output=True, timeout=60)
        if result.returncode:
            # Avoid echoing inspect output, which may contain container secrets.
            raise RuntimeError(f"docker {args[0]} failed; inspect the saved Docker logs")
        return result.stdout.strip()

    def wait_http(self, url: str, expected_status: str | None = None) -> None:
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=3) as response:
                    if response.status == 200 and (
                        expected_status is None or json.load(response).get("status") == expected_status
                    ):
                        return
            except (OSError, ValueError, urllib.error.URLError):
                pass
            time.sleep(1)
        raise RuntimeError("Candidate HTTP readiness timed out; see candidate.log")

    def candidate_smoke(self) -> None:
        assert self.image_id
        self.container = "doorman-e2e-" + secrets.token_hex(8)
        local = {"ENV": "development", "HOST": "0.0.0.0", "PORT": "3001", "WEB_PORT": "3000",
                 "MEM_OR_EXTERNAL": "MEM", "THREADS": "1", "HTTPS_ONLY": "false",
                 "LOCAL_HOST_IP_BYPASS": "false", "CORS_STRICT": "true", "DEMO_SEED": "false",
                 "ALLOWED_ORIGINS": "http://localhost:3000", "JWT_SECRET_KEY": secrets.token_hex(32),
                 "JWT_ISSUER": "e2e-isolated", "JWT_AUDIENCE": "e2e-isolated-clients",
                 "MEM_ENCRYPTION_KEY": secrets.token_hex(32), "MEM_DUMP_PATH": "/app/data/e2e.bin",
                 "DOORMAN_ADMIN_EMAIL": "e2e@example.test",
                 "DOORMAN_ADMIN_PASSWORD": "E2e!" + secrets.token_hex(24)}
        # Pass values through the subprocess environment, never CLI arguments/logs.
        command = ["docker", "run", "--detach", "--name", self.container,
                   "--publish", "127.0.0.1::3001", "--publish", "127.0.0.1::3000"]
        for key in local:
            command.extend(["--env", key])
        self.run("candidate-start", [*command, self.image_id], {**self.env, **local})
        api_binding = self.docker_output("port", self.container, "3001/tcp")
        web_binding = self.docker_output("port", self.container, "3000/tcp")
        for binding in (api_binding, web_binding):
            if not re.fullmatch(r"127\.0\.0\.1:\d+", binding):
                raise RuntimeError("Candidate must bind exclusively to a loopback port")
        base = "http://" + api_binding
        print("Waiting for disposable backend and frontend...", flush=True)
        self.wait_http(base + "/platform/monitor/liveness", "alive")
        self.wait_http(base + "/platform/monitor/readiness", "ready")
        self.wait_http("http://" + web_binding)
        self.run("live-tcp", ["cargo", "test", "--manifest-path", "gateway-rs/Cargo.toml",
                              "--locked", "--test", "live_tcp_port_3001", "--", "--ignored", "--nocapture"],
                 {**self.env, **local, "LIVE_SERVER_URL": base})
        self.summary["local_image_smoke"] = {"passed": True, "image_id": self.image_id,
                                              "finished_at": utc_now()}
        self.save()

    def cleanup(self) -> None:
        if not self.container:
            return
        # Only remove the randomly named container created by this run. Never prune.
        with (self.evidence / "candidate.log").open("w") as log:
            subprocess.run(["docker", "logs", self.container], env=self.env,
                           stdout=log, stderr=subprocess.STDOUT, timeout=30)
        result = subprocess.run(["docker", "rm", "--force", self.container], env=self.env,
                                capture_output=True, timeout=30)
        if result.returncode:
            raise RuntimeError(f"Could not clean up {self.container}; remove that container manually")
        self.container = None

    def execute(self) -> None:
        self.run("source-state", ["git", "status", "--short"])
        self.run("source-commit", ["git", "rev-parse", "HEAD"])
        self.run("runner-tests", [sys.executable, "-m", "unittest", "discover", "-s", "scripts", "-p", "test_*.py"])
        self.run("parity-inventory", ["make", "parity-reference", "parity-ledger"])
        self.run("rust-checks", ["make", "check"])
        self.run("frontend-build", ["make", "web-build"])
        self.run("external-storage", ["bash", "scripts/run_external_storage_tests.sh"])
        self.run("image-build", ["docker", "build", "--iidfile", str(self.evidence / "image-id.txt"), "."])
        self.image_id = (self.evidence / "image-id.txt").read_text().strip()
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", self.image_id):
            raise RuntimeError("Docker did not produce a valid immutable image ID")
        self.env["RELEASE_IMAGE_ID"] = self.image_id
        self.summary["image_id"] = self.image_id
        self.save()
        self.candidate_smoke()
        # Don't leave the local smoke server competing with benchmark processes.
        self.cleanup()
        if self.release:
            self.run("operations-rehearsals", [str(Path(self.env["RELEASE_OPERATIONS_COMMAND"]).resolve())])
            operations = json.loads(Path(self.env["RELEASE_OPERATIONS_REPORT"]).read_text())
            if not isinstance(operations, dict) or operations.get("image_id") != self.image_id:
                raise RuntimeError("Operational evidence must identify this run's RELEASE_IMAGE_ID")
            self.run("differential", ["make", "parity-differential"])
            self.run("performance", ["make", "parity-performance"])
            # Relative error comparison alone can pass two equally broken servers.
            report = json.loads(Path(self.env["PARITY_PERF_REPORT"]).read_text())
            for profile in report["profiles"].values():
                for trials in profile["measurements"].values():
                    if not trials or any(trial["error_rate"] != 0 for trial in trials):
                        raise RuntimeError("Release benchmark requires successful requests in every trial")
            self.run("release-check", ["make", "release-check"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", action="store_true", help="include every release evidence gate")
    parser.add_argument("--plan", action="store_true", help="print stages without running commands")
    parser.add_argument("--preflight", action="store_true", help="validate prerequisites without building")
    args = parser.parse_args()
    if args.plan:
        for index, stage in enumerate(LOCAL_STAGES + (RELEASE_STAGES if args.release else ()), 1):
            print(f"{index}. {stage}")
        print("\nPrerequisites and release fixture contract: user-docs/TESTS.md")
        return 0
    env = child_environment()
    runner = None
    code = 1
    # SIGTERM should follow the same evidence/cleanup path as Ctrl-C.
    def interrupted(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupted)
    try:
        preflight(env, args.release)
        if args.preflight:
            print("Prerequisites passed; no tests or builds were run.")
            return 0
        parent = Path(env.get("E2E_EVIDENCE_ROOT", str(ROOT / "release-evidence"))).resolve()
        parent.mkdir(parents=True, exist_ok=True)
        evidence = Path(tempfile.mkdtemp(prefix=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-"), dir=parent))
        evidence.chmod(0o700)
        print(f"Evidence: {evidence}", flush=True)
        runner = Runner(evidence, env, args.release)
        runner.execute()
        code = 0
    except KeyboardInterrupt:
        print("\nInterrupted; cleaning up owned resources.", file=sys.stderr)
        code = 130
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
    finally:
        if runner:
            try:
                runner.cleanup()
            except (OSError, RuntimeError, subprocess.SubprocessError) as error:
                print(f"Cleanup failed: {error}", file=sys.stderr)
                code = code or 1
            runner.summary.update(status="passed" if code == 0 else "failed", finished_at=utc_now())
            runner.save()
            print(f"Evidence saved: {runner.evidence}", flush=True)
    if code == 0:
        print("PASS: release gates completed." if args.release else
              "PASS: automated E2E checks completed. Release rehearsals/comparisons are NOT certified; "
              "use make release-e2e for those gates.")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
