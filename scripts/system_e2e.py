#!/usr/bin/env python3
"""Local, owned, fail-closed Doorman system-test orchestrator.

The plan and contract checks use only the Python standard library and do not
start Docker. Runtime profiles build the working tree once, retain evidence,
and never reuse or prune resources outside their run label.
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import html
import itertools
import json
import os
import random
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as xml_escape

ROOT = Path(__file__).resolve().parents[1]
SYSTEM = ROOT / "system-tests"
OPENAPI = ROOT / "parity/openapi/python-openapi.json.gz.b64"
EVIDENCE_ROOT = ROOT / "system-e2e-evidence"
REPORT_NAME = "system-e2e-report.json"
LABEL = "com.doorman.system-e2e.run"
PROFILE_BUDGETS = {"smoke": 300, "comprehensive": 1800, "soak": 3600}
PROFILE_TOPOLOGIES = {
    "smoke": ["memory"],
    "comprehensive": ["memory", "external", "two-node"],
    "soak": ["two-node"],
}


class ContractError(ValueError):
    pass


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"cannot read {path.relative_to(ROOT)}: {error}") from error


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def operation_inventory() -> list[dict[str, str]]:
    # Keep this import local so --help and cleanup do not depend on parity helpers.
    sys.path.insert(0, str(ROOT))
    from scripts.differential_parity import load_openapi, operation_cases

    _, document = load_openapi(OPENAPI)
    return [
        {
            "feature_id": f"openapi:{case['method']}:{case['path_template']}",
            "method": case["method"],
            "path": case["path_template"],
            "operation_id": case["operation_id"],
        }
        for case in operation_cases(document)
    ]


def dashboard_routes() -> list[str]:
    routes = []
    for page in sorted((ROOT / "web-client/src/app").rglob("page.tsx")):
        route = "/" + str(page.parent.relative_to(ROOT / "web-client/src/app"))
        routes.append("/" if route == "/." else route)
    return routes


def is_na(operation: dict[str, str], case: str, rules: list[dict[str, Any]]) -> str | None:
    for rule in rules:
        if case not in rule["classes"]:
            continue
        methods = rule.get("methods")
        prefixes = rule.get("path_prefixes")
        if methods and operation["method"] not in methods:
            continue
        if prefixes and not any(operation["path"].startswith(prefix) for prefix in prefixes):
            continue
        return str(rule["rationale"])
    return None


def operation_cells(contract: dict[str, Any]) -> list[dict[str, str]]:
    cells: list[dict[str, str]] = []
    for operation in operation_inventory():
        for case in contract["operation_classes"]:
            rationale = is_na(operation, case, contract["not_applicable_rules"])
            cell = {**operation, "class": case}
            if rationale:
                cell.update(disposition="not_applicable", rationale=rationale)
            else:
                cell.update(
                    disposition="executable",
                    scenario_id=f"operation::{operation['method']}::{operation['path']}::{case}",
                )
            cells.append(cell)
    return cells


def violates(values: dict[str, str], forbidden: list[dict[str, str]]) -> bool:
    return any(all(values.get(key) == value for key, value in rule.items()) for rule in forbidden)


def valid_pairs(pairwise: dict[str, Any]) -> set[tuple[str, str, str, str]]:
    axes = list(pairwise["axes"])
    invalid = pairwise["forbidden_pairs"]
    result: set[tuple[str, str, str, str]] = set()
    for left_index, left in enumerate(axes):
        for right in axes[left_index + 1 :]:
            for left_value in pairwise["axes"][left]:
                for right_value in pairwise["axes"][right]:
                    partial = {left: left_value, right: right_value}
                    if not violates(partial, invalid):
                        result.add((left, left_value, right, right_value))
    return result


def covered_pairs(row: dict[str, str]) -> set[tuple[str, str, str, str]]:
    axes = list(row)
    return {
        (left, row[left], right, row[right])
        for index, left in enumerate(axes)
        for right in axes[index + 1 :]
    }


def _candidate_for_pair(
    target: tuple[str, str, str, str], pairwise: dict[str, Any], rng: random.Random
) -> dict[str, str] | None:
    left, left_value, right, right_value = target
    axes: dict[str, list[str]] = pairwise["axes"]
    fixed = {left: left_value, right: right_value}
    for _ in range(100):
        row = dict(fixed)
        names = [name for name in axes if name not in fixed]
        rng.shuffle(names)
        for name in names:
            choices = list(axes[name])
            rng.shuffle(choices)
            chosen = next(
                (value for value in choices if not violates({**row, name: value}, pairwise["forbidden_pairs"])),
                None,
            )
            if chosen is None:
                break
            row[name] = chosen
        if len(row) == len(axes) and not violates(row, pairwise["forbidden_pairs"]):
            return {name: row[name] for name in axes}
    return None


def pairwise_rows(pairwise: dict[str, Any]) -> list[dict[str, str]]:
    rng = random.Random(pairwise["seed"])
    targets = valid_pairs(pairwise)
    candidates: dict[bytes, dict[str, str]] = {}
    for target in sorted(targets):
        row = _candidate_for_pair(target, pairwise, rng)
        if row is None:
            raise ContractError(f"pair has no valid complete assignment: {target}")
        candidates[canonical(row)] = row
    # Extra deterministic candidates make the greedy cover substantially smaller.
    axes: dict[str, list[str]] = pairwise["axes"]
    for _ in range(4000):
        row = {name: rng.choice(values) for name, values in axes.items()}
        if not violates(row, pairwise["forbidden_pairs"]):
            candidates[canonical(row)] = row
    uncovered = set(targets)
    rows: list[dict[str, str]] = []
    pool = list(candidates.values())
    while uncovered:
        best = max(pool, key=lambda row: len(covered_pairs(row) & uncovered))
        gain = covered_pairs(best) & uncovered
        if not gain:
            raise ContractError(f"pairwise generation stalled with {len(uncovered)} uncovered pairs")
        rows.append(best)
        uncovered -= gain
        pool.remove(best)
    return rows


@functools.lru_cache(maxsize=1)
def generated_ledger() -> dict[str, Any]:
    contract = load_json(SYSTEM / "contract.json")
    pairwise = load_json(SYSTEM / "pairwise.json")
    operations = operation_inventory()
    routes = dashboard_routes()
    cells = operation_cells(contract)
    rows = pairwise_rows(pairwise)
    scenarios: list[dict[str, Any]] = []
    for cell in cells:
        if cell["disposition"] == "executable":
            scenarios.append(
                {
                    "id": cell["scenario_id"],
                    "domain": "operation",
                    "features": [cell["feature_id"]],
                    "executor": "openapi-operation",
                    "expected": ["status", "content_type", "headers", "body_class", "state", "audit", "redaction"],
                }
            )
    for setting in contract["runtime_settings"]:
        for kind in ("positive", "invalid"):
            scenarios.append(
                {
                    "id": f"setting::{setting}::{kind}",
                    "domain": "configuration",
                    "features": [f"setting:{setting}"],
                    "executor": "runtime-setting",
                    "expected": ["startup_or_reload_result", "effective_value", "atomicity", "redaction"],
                }
            )
    for route in routes:
        scenarios.append(
            {
                "id": f"ui::{route}",
                "domain": "browser",
                "features": [f"ui:{route}"],
                "executor": "playwright-workflow",
                "expected": ["route", "backend_effect", "console", "network", "accessibility"],
            }
        )
    for pack in contract["feature_packs"]:
        scenarios.append(
            {
                "id": f"pack::{pack}",
                "domain": "higher-order",
                "features": [f"pack:{pack}"],
                "executor": "higher-order-pack",
                "expected": ["status", "state", "side_effects", "audit", "redaction"],
            }
        )
    for index, row in enumerate(rows, 1):
        scenarios.append(
            {
                "id": f"pairwise::{index:04d}",
                "domain": "pairwise",
                "features": ["matrix:pairwise"],
                "executor": "generated-policy-case",
                "inputs": row,
                "expected": ["status", "body_class", "headers", "state", "side_effects"],
            }
        )
    features = [item["feature_id"] for item in operations]
    features += [f"setting:{setting}" for setting in contract["runtime_settings"]]
    features += [f"ui:{route}" for route in routes]
    features += [f"pack:{pack}" for pack in contract["feature_packs"]]
    features.append("matrix:pairwise")
    return {
        "schema_version": 1,
        "manifest_hashes": {
            path.name: sha256(path)
            for path in (SYSTEM / "contract.json", SYSTEM / "pairwise.json", SYSTEM / "upstreams.json")
        },
        "features": features,
        "operations": operations,
        "operation_cells": cells,
        "dashboard_routes": routes,
        "pairwise_rows": rows,
        "valid_pairs": len(valid_pairs(pairwise)),
        "scenarios": scenarios,
    }


def validate_contract() -> dict[str, Any]:
    contract = load_json(SYSTEM / "contract.json")
    upstreams = load_json(SYSTEM / "upstreams.json")
    approvals = load_json(SYSTEM / "approvals.json")
    ledger = generated_ledger()
    errors: list[str] = []
    operations = ledger["operations"]
    if len(operations) != contract["frozen_openapi_operations"]:
        errors.append(
            f"frozen OpenAPI drift: expected {contract['frozen_openapi_operations']}, found {len(operations)}"
        )
    ids = [item["feature_id"] for item in operations]
    if len(ids) != len(set(ids)):
        errors.append("duplicate OpenAPI method/path feature IDs")
    routes = ledger["dashboard_routes"]
    route_hash = hashlib.sha256(canonical(routes)).hexdigest()
    if len(routes) != contract["expected_dashboard_routes"]:
        errors.append(
            f"dashboard route drift: expected {contract['expected_dashboard_routes']}, found {len(routes)}"
        )
    if route_hash != contract["dashboard_routes_sha256"]:
        errors.append("dashboard route inventory changed; review and update its contract hash")
    profiles = upstreams.get("profiles", [])
    profile_ids = [profile.get("id") for profile in profiles]
    expected_profiles = list(load_json(SYSTEM / "pairwise.json")["axes"]["protocol_profile"])
    if profile_ids != expected_profiles or len(profile_ids) != 10:
        errors.append("fixture profiles must be the ten ordered pairwise protocol profiles")
    if any(set(profile) != {"id", "protocol", "standard"} for profile in profiles):
        errors.append("each fixture profile must declare exactly id, protocol, and standard")
    cells = ledger["operation_cells"]
    expected_cells = len(operations) * len(contract["operation_classes"])
    if len(cells) != expected_cells or any(
        cell.get("disposition") not in {"executable", "not_applicable"} for cell in cells
    ):
        errors.append("every operation/class cell must be executable or explicitly not applicable")
    if any(
        cell["disposition"] == "not_applicable" and not cell.get("rationale") for cell in cells
    ):
        errors.append("not_applicable cells require a rationale")
    scenario_ids = [scenario["id"] for scenario in ledger["scenarios"]]
    if len(scenario_ids) != len(set(scenario_ids)):
        errors.append("duplicate scenario IDs")
    feature_ids = ledger["features"]
    mapped = set(itertools.chain.from_iterable(s["features"] for s in ledger["scenarios"]))
    missing_features = sorted(set(feature_ids) - mapped)
    if missing_features:
        errors.append(f"features without executable scenarios: {', '.join(missing_features[:5])}")
    if any(not scenario.get("features") for scenario in ledger["scenarios"]):
        errors.append("scenario without a feature mapping")
    if any(not scenario.get("expected") for scenario in ledger["scenarios"]):
        errors.append("scenario without explicit expected evidence")
    rows = ledger["pairwise_rows"]
    actual_pairs = set().union(*(covered_pairs(row) for row in rows))
    missing_pairs = valid_pairs(load_json(SYSTEM / "pairwise.json")) - actual_pairs
    if missing_pairs:
        errors.append(f"pairwise matrix misses {len(missing_pairs)} valid pairs")
    today = date.today()
    for approval in approvals.get("approvals", []):
        required = {"scenario_id", "signature", "rationale", "issue", "owner", "expires"}
        if set(approval) != required:
            errors.append("each approval must contain exactly the reviewed approval fields")
            continue
        try:
            if date.fromisoformat(approval["expires"]) < today:
                errors.append(f"stale approval: {approval['scenario_id']}")
        except (TypeError, ValueError):
            errors.append(f"invalid approval expiry: {approval.get('scenario_id', '<unknown>')}")
    if contract.get("approved_differences"):
        errors.append("approvals belong in system-tests/approvals.json, not the feature contract")
    report_schema = load_json(SYSTEM / "report.schema.json")
    required_report_fields = {
        "schema_version", "status", "profile", "run_id", "source_commit",
        "dirty_state_digest", "candidate_image_id", "fixture_image_ids",
        "manifest_hashes", "random_seed", "topologies", "timings",
        "scenario_counts", "operation_coverage", "pair_coverage", "ui_coverage",
        "failures", "infrastructure_errors", "approved_differences", "artifacts",
    }
    if set(report_schema.get("required", [])) != required_report_fields:
        errors.append("report schema required fields drifted from the evidence contract")
    if not required_report_fields <= set(report_schema.get("properties", {})):
        errors.append("report schema does not define every required evidence field")
    if errors:
        raise ContractError("\n".join(errors))
    return ledger


def plan(profile: str) -> dict[str, Any]:
    ledger = validate_contract()
    applicable = sum(cell["disposition"] == "executable" for cell in ledger["operation_cells"])
    na = len(ledger["operation_cells"]) - applicable
    return {
        "profile": profile,
        "budget_seconds": PROFILE_BUDGETS[profile],
        "topologies": PROFILE_TOPOLOGIES[profile],
        "candidate_images": 1,
        "independent_upstreams": 10,
        "features": len(ledger["features"]),
        "operations": len(ledger["operations"]),
        "operation_cells": {"executable": applicable, "not_applicable": na},
        "dashboard_routes": len(ledger["dashboard_routes"]),
        "runtime_settings": len(load_json(SYSTEM / "contract.json")["runtime_settings"]),
        "pairwise_scenarios": len(ledger["pairwise_rows"]),
        "valid_pairs": ledger["valid_pairs"],
        "higher_order_packs": len(load_json(SYSTEM / "contract.json")["feature_packs"]),
        "total_scenarios": len(ledger["scenarios"]),
    }


def print_plan(profile: str) -> None:
    value = plan(profile)
    print(json.dumps(value, indent=2, sort_keys=True))


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def command(args: list[str], *, env: dict[str, str] | None = None, cwd: Path = ROOT, timeout: int = 1800) -> str:
    completed = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )
    if completed.returncode:
        tail = "\n".join(completed.stdout.splitlines()[-40:])
        raise RuntimeError(f"command failed ({' '.join(args[:3])}):\n{tail}")
    return completed.stdout


def git_state() -> tuple[str, str]:
    commit = command(["git", "rev-parse", "HEAD"]).strip()
    status = command(["git", "status", "--porcelain=v1", "--untracked-files=all"])
    return commit, hashlib.sha256(status.encode()).hexdigest()


def wait_json(url: str, expected: dict[str, Any], timeout: float = 90) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last = "no response"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                value = json.load(response)
                if all(value.get(key) == item for key, item in expected.items()):
                    return value
                last = repr(value)
        except (OSError, ValueError, urllib.error.URLError) as error:
            last = str(error)
        time.sleep(0.5)
    raise RuntimeError(f"readiness timed out for {url}: {last}")


@dataclass
class OwnedResources:
    run_id: str
    names: list[str]
    volumes: list[str]

    def cleanup(self, evidence: Path) -> list[str]:
        errors: list[str] = []
        log_dir = evidence / "containers"
        log_dir.mkdir(exist_ok=True)
        for name in reversed(self.names):
            subprocess.run(
                ["docker", "logs", name],
                text=True,
                stdout=(log_dir / f"{name}.log").open("w"),
                stderr=subprocess.STDOUT,
                timeout=30,
                check=False,
            )
            result = subprocess.run(
                ["docker", "rm", "--force", name], capture_output=True, text=True, timeout=30
            )
            if result.returncode and "No such container" not in result.stderr:
                errors.append(f"could not remove owned container {name}")
        for name in reversed(self.volumes):
            result = subprocess.run(
                ["docker", "volume", "rm", "--force", name],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode and "No such volume" not in result.stderr:
                errors.append(f"could not remove owned volume {name}")
        result = subprocess.run(
            ["docker", "network", "rm", f"doorman-system-{self.run_id}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode and "not found" not in result.stderr.lower():
            errors.append("could not remove owned network")
        return errors


class Runtime:
    def __init__(self, profile: str, seed: int | None = None):
        self.profile = profile
        self.seed = seed if seed is not None else load_json(SYSTEM / "pairwise.json")["seed"]
        self.run_id = secrets.token_hex(12)
        EVIDENCE_ROOT.mkdir(exist_ok=True)
        self.evidence = Path(tempfile.mkdtemp(prefix=f"{self.run_id}-", dir=EVIDENCE_ROOT))
        self.evidence.chmod(0o700)
        self.resources = OwnedResources(self.run_id, [], [])
        self.started = time.monotonic()
        commit, dirty = git_state()
        ledger = validate_contract()
        self.ledger = ledger
        self.report: dict[str, Any] = {
            "schema_version": 1,
            "status": "running",
            "profile": profile,
            "run_id": self.run_id,
            "source_commit": commit,
            "dirty_state_digest": dirty,
            "candidate_image_id": "",
            "fixture_image_ids": {},
            "manifest_hashes": ledger["manifest_hashes"],
            "random_seed": self.seed,
            "topologies": [
                {"name": name, "status": "planned"} for name in PROFILE_TOPOLOGIES[profile]
            ],
            "timings": {"started_at": utc_now()},
            "scenario_counts": {"planned": len(ledger["scenarios"]), "passed": 0, "failed": 0, "skipped": 0},
            "operation_coverage": {"total": len(ledger["operations"]), "covered": 0},
            "pair_coverage": {"valid": ledger["valid_pairs"], "covered": 0},
            "ui_coverage": {"total": len(ledger["dashboard_routes"]), "covered": 0},
            "failures": [],
            "infrastructure_errors": [],
            "approved_differences": load_json(SYSTEM / "approvals.json")["approvals"],
            "artifacts": {
                "report": REPORT_NAME,
                "coverage_ledger": "coverage-ledger.json",
                "junit": "junit.xml",
                "html": "coverage.html",
                "replay": "replay.json",
                "container_logs": "containers/",
            },
        }
        (self.evidence / "coverage-ledger.json").write_text(
            json.dumps(ledger, indent=2, sort_keys=True) + "\n"
        )
        self.save()

    def save(self) -> None:
        (self.evidence / REPORT_NAME).write_text(json.dumps(self.report, indent=2, sort_keys=True) + "\n")

    def build_images(self) -> None:
        candidate_iid = self.evidence / "candidate-image-id.txt"
        fixture_iid = self.evidence / "fixture-image-id.txt"
        command(["docker", "build", "--iidfile", str(candidate_iid), "."], timeout=2400)
        command(
            ["docker", "build", "--iidfile", str(fixture_iid), "system-tests/fixture"], timeout=1200
        )
        candidate = candidate_iid.read_text().strip()
        fixture = fixture_iid.read_text().strip()
        image_pattern = re.compile(r"^sha256:[0-9a-f]{64}$")
        if not image_pattern.fullmatch(candidate) or not image_pattern.fullmatch(fixture):
            raise RuntimeError("Docker did not return immutable image IDs")
        self.report["candidate_image_id"] = candidate
        self.report["fixture_image_ids"] = {"upstream": fixture}
        self.save()

    def start_fixtures(self) -> dict[str, str]:
        network = f"doorman-system-{self.run_id}"
        command(["docker", "network", "create", "--label", f"{LABEL}={self.run_id}", network])
        profiles = load_json(SYSTEM / "upstreams.json")["profiles"]
        urls: dict[str, str] = {}
        fixture_image = self.report["fixture_image_ids"]["upstream"]
        for profile in profiles:
            port = free_port()
            name = f"doorman-system-{self.run_id}-{profile['id']}"
            env = {**os.environ, "FIXTURE_PROFILE": profile["id"]}
            command(
                [
                    "docker", "run", "--detach", "--name", name,
                    "--label", f"{LABEL}={self.run_id}", "--network", network,
                    "--publish", f"127.0.0.1:{port}:8080", "--env", "FIXTURE_PROFILE",
                    fixture_image,
                ],
                env=env,
            )
            self.resources.names.append(name)
            urls[profile["id"]] = f"http://127.0.0.1:{port}"
        for profile, base in urls.items():
            wait_json(base + "/health", {"status": "healthy", "profile": profile})
            request = urllib.request.Request(base + "/__control/reset", method="POST", data=b"{}")
            with urllib.request.urlopen(request, timeout=5) as response:
                value = json.load(response)
                if value.get("reset") is not True:
                    raise RuntimeError(f"fixture reset self-test failed: {profile}")
        (self.evidence / "resolved-fixtures.json").write_text(json.dumps(urls, indent=2) + "\n")
        return urls

    @staticmethod
    def http(
        base: str,
        method: str,
        path: str,
        *,
        token: str | None = None,
        value: Any | None = None,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, Any]:
        outgoing = dict(headers or {})
        if value is not None:
            body = canonical(value)
            outgoing.setdefault("Content-Type", "application/json")
        if token:
            outgoing["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(base + path, data=body, headers=outgoing, method=method)
        try:
            response = urllib.request.urlopen(request, timeout=20)
        except urllib.error.HTTPError as error:
            response = error
        raw = response.read()
        try:
            decoded: Any = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            decoded = raw
        return response.status, decoded

    def start_memory_candidate(self) -> tuple[str, str]:
        api_port, web_port = free_port(), free_port()
        name = f"doorman-system-{self.run_id}-memory"
        volume = f"doorman-system-{self.run_id}-snapshot"
        command(["docker", "volume", "create", "--label", f"{LABEL}={self.run_id}", volume])
        self.resources.volumes.append(volume)
        self.admin_email = f"system-{self.run_id}@example.test"
        self.admin_password = "System!" + secrets.token_hex(24)
        settings = {
            "ENV": "development",
            "HOST": "0.0.0.0",
            "WEB_HOST": "0.0.0.0",
            "PORT": "3001",
            "WEB_PORT": "3000",
            "MEM_OR_EXTERNAL": "MEM",
            "THREADS": "1",
            "MEM_DUMP_PATH": "/app/data/system-e2e.bin",
            "MEM_ENCRYPTION_KEY": secrets.token_hex(32),
            "MEM_AUTO_SAVE_ENABLED": "false",
            "DOORMAN_ADMIN_EMAIL": self.admin_email,
            "DOORMAN_ADMIN_PASSWORD": self.admin_password,
            "JWT_SECRET_KEY": secrets.token_hex(48),
            "JWT_ISSUER": "doorman-system-e2e",
            "JWT_AUDIENCE": "doorman-system-e2e-clients",
            "CORS_STRICT": "true",
            "ALLOWED_ORIGINS": "https://system-e2e.invalid",
            "ALLOW_HEADERS": "*",
            "ALLOW_METHODS": "GET,HEAD,POST,PUT,PATCH,DELETE,OPTIONS",
            "LOCAL_HOST_IP_BYPASS": "false",
            "HTTPS_ONLY": "false",
            "DEMO_SEED": "false",
        }
        env_file = self.evidence / "candidate.env"
        env_file.write_text("\n".join(f"{key}={value}" for key, value in settings.items()) + "\n")
        env_file.chmod(0o600)
        command(
            [
                "docker", "run", "--detach", "--name", name,
                "--label", f"{LABEL}={self.run_id}",
                "--network", f"doorman-system-{self.run_id}",
                "--publish", f"127.0.0.1:{api_port}:3001",
                "--publish", f"127.0.0.1:{web_port}:3000",
                "--mount", f"type=bind,src={env_file},dst=/env/system.env,readonly",
                "--mount", f"type=volume,src={volume},dst=/app/data",
                self.report["candidate_image_id"],
            ]
        )
        self.resources.names.append(name)
        base = f"http://127.0.0.1:{api_port}"
        wait_json(base + "/platform/monitor/liveness", {"status": "alive"}, timeout=180)
        wait_json(base + "/platform/monitor/readiness", {"status": "ready"}, timeout=180)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{web_port}", timeout=3) as response:
                    if response.status == 200:
                        break
            except urllib.error.URLError:
                time.sleep(0.5)
        else:
            raise RuntimeError("candidate dashboard readiness timed out")
        return base, f"http://127.0.0.1:{web_port}"

    def login(self, base: str) -> str:
        status, body = self.http(
            base,
            "POST",
            "/platform/authorization",
            value={"email": self.admin_email, "password": self.admin_password},
        )
        while isinstance(body, dict) and isinstance(body.get("response"), dict):
            body = body["response"]
        token = body.get("access_token") if isinstance(body, dict) else None
        if status != 200 or not isinstance(token, str):
            raise RuntimeError(f"candidate administrator login failed with HTTP {status}")
        return token

    def upload_proto(self, base: str, token: str, api_name: str) -> None:
        proto = (
            'syntax = "proto3"; package fixture.v1; service Resource {'
            " rpc Create (Request) returns (Reply); } message Request { string name = 1; }"
            " message Reply { string message = 1; }"
        )
        boundary = "----doorman-system-" + secrets.token_hex(8)
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"fixture.proto\"\r\n"
            "Content-Type: application/octet-stream\r\n\r\n"
            f"{proto}\r\n--{boundary}--\r\n"
        ).encode()
        status, _ = self.http(
            base,
            "POST",
            f"/platform/proto/{api_name}/v1",
            token=token,
            body=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        if status not in {200, 201}:
            raise RuntimeError(f"proto upload for {api_name} returned HTTP {status}")

    def seed_and_probe(self, base: str) -> None:
        token = self.login(base)
        protocol_paths = {
            "rest": ("REST", "/items", "GET"),
            "graphql": ("GRAPHQL", "/graphql", "POST"),
            "soap": ("SOAP", "/soap", "POST"),
            "grpc": ("GRPC", "/grpc", "POST"),
            "grpc-web": ("GRPC", "/grpc", "POST"),
        }
        results: list[dict[str, Any]] = []
        for profile in load_json(SYSTEM / "upstreams.json")["profiles"]:
            api_name = f"system-{self.run_id[:8]}-{profile['id']}"
            kind, endpoint_path, method = protocol_paths[profile["protocol"]]
            port = 50051 if profile["protocol"] == "grpc" else 8080
            scheme = "grpc" if profile["protocol"] == "grpc" else "http"
            server = f"{scheme}://doorman-system-{self.run_id}-{profile['id']}:{port}"
            payload = {
                "api_name": api_name,
                "api_version": "v1",
                "api_description": f"system fixture {profile['id']}",
                "api_allowed_roles": [],
                "api_allowed_groups": [],
                "api_servers": [server],
                "api_type": kind,
                "api_allowed_retry_count": 0,
                "api_public": True,
                "active": True,
            }
            if kind == "GRPC":
                payload["api_grpc_package"] = "fixture.v1"
                if profile["protocol"] == "grpc-web":
                    payload["api_grpc_web_enabled"] = True
            status, body = self.http(base, "POST", "/platform/api", token=token, value=payload)
            if status not in {200, 201}:
                results.append({"profile": profile["id"], "phase": "create-api", "status": status, "body_class": type(body).__name__})
                continue
            if profile["protocol"] == "grpc":
                try:
                    self.upload_proto(base, token, api_name)
                except RuntimeError as error:
                    results.append({"profile": profile["id"], "phase": "proto", "error": str(error)})
                    continue
            status, body = self.http(
                base,
                "POST",
                "/platform/endpoint",
                token=token,
                value={
                    "api_name": api_name,
                    "api_version": "v1",
                    "endpoint_method": method,
                    "endpoint_uri": endpoint_path,
                    "endpoint_description": f"system fixture {profile['id']}",
                },
            )
            if status not in {200, 201}:
                results.append({"profile": profile["id"], "phase": "create-endpoint", "status": status, "body_class": type(body).__name__})
                continue
            if profile["protocol"] == "rest":
                request = ("GET", f"/api/rest/{api_name}/v1/items", None, {})
            elif profile["protocol"] == "graphql":
                request = ("POST", f"/api/graphql/{api_name}", {"query": "{ hello }"}, {"X-API-Version": "v1"})
            elif profile["protocol"] == "soap":
                if profile["id"] == "soap-2":
                    xml = (
                        b'<?xml version="1.0"?><Envelope><Header><Security>'
                        b"<UsernameToken>fixture</UsernameToken></Security></Header>"
                        b"<Body><Ping/></Body></Envelope>"
                    )
                    media = "application/soap+xml"
                else:
                    xml = b'<?xml version="1.0"?><Envelope><Body><Ping/></Body></Envelope>'
                    media = "text/xml"
                request = (
                    "POST",
                    f"/api/soap/{api_name}/v1/soap",
                    xml,
                    {"Content-Type": media},
                )
            elif profile["protocol"] == "grpc":
                request = ("POST", f"/api/grpc/{api_name}", {"method": "Resource.Create", "message": {"name": "probe"}}, {"X-API-Version": "v1"})
            else:
                # The current Rust implementation handles CRUD gRPC-Web locally;
                # this probe documents the advertised route while the profile's
                # direct self-test proves its upstream framing behavior.
                request = ("OPTIONS", f"/api/grpc-web/{api_name}/fixture.v1.CrudService/ListItems", None, {"Origin": "https://system-e2e.invalid", "Access-Control-Request-Method": "POST"})
            method_name, path, request_value, headers = request
            if isinstance(request_value, bytes):
                status, body = self.http(base, method_name, path, body=request_value, headers=headers)
            else:
                status, body = self.http(base, method_name, path, value=request_value, headers=headers)
            results.append({"profile": profile["id"], "phase": "gateway", "status": status, "body_class": type(body).__name__})
        (self.evidence / "baseline-probes.json").write_text(json.dumps(results, indent=2) + "\n")
        for result in results:
            if result.get("phase") != "gateway" or result.get("status", 500) >= 400:
                self.report["failures"].append(
                    {
                        "scenario_id": f"fixture-baseline::{result['profile']}",
                        "domain": "protocol",
                        "signature": f"{result.get('phase')}-{result.get('status', 'error')}",
                        "message": "upstream onboarding or gateway probe failed",
                    }
                )

    def record_unimplemented_corpus(self) -> None:
        # This is deliberately fail-closed. Infrastructure can be developed and
        # inspected without ever turning absent product assertions into a pass.
        for scenario in self.ledger["scenarios"]:
            self.report["failures"].append(
                {
                    "scenario_id": scenario["id"],
                    "domain": scenario["domain"],
                    "signature": "executor-not-implemented",
                    "message": f"runtime executor {scenario['executor']} has no result",
                }
            )
        self.report["scenario_counts"]["failed"] = len(self.report["failures"])

    def execute(self) -> None:
        self.build_images()
        self.start_fixtures()
        base, _web = self.start_memory_candidate()
        self.seed_and_probe(base)
        for topology in self.report["topologies"]:
            if topology["name"] == "memory":
                topology["status"] = "passed"
        self.record_unimplemented_corpus()

    def write_summary_artifacts(self) -> None:
        failures = self.report["failures"]
        cases = []
        for failure in failures:
            scenario_id = str(failure.get("scenario_id", "unknown"))
            message = str(failure.get("message", "failure"))
            cases.append(
                f'<testcase classname="system-e2e" name="{xml_escape(scenario_id)}">'
                f'<failure message="{xml_escape(message)}"/></testcase>'
            )
        junit = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<testsuite name="system-e2e" tests="{len(failures)}" failures="{len(failures)}">'
            + "".join(cases)
            + "</testsuite>\n"
        )
        (self.evidence / "junit.xml").write_text(junit)
        plan_rows = "".join(
            f"<tr><td>{html.escape(item['name'])}</td><td>{html.escape(item['status'])}</td></tr>"
            for item in self.report["topologies"]
        )
        document = f"""<!doctype html><html><head><meta charset="utf-8"><title>Doorman system E2E</title>
<style>body{{font-family:system-ui;margin:2rem}}table{{border-collapse:collapse}}td,th{{border:1px solid #aaa;padding:.4rem}}.failed{{color:#a00}}</style></head>
<body><h1>Doorman system E2E: {html.escape(self.report['status'])}</h1>
<p>Run {html.escape(self.run_id)}; profile {html.escape(self.profile)}; failures <span class="failed">{len(failures)}</span>.</p>
<table><thead><tr><th>Topology</th><th>Status</th></tr></thead><tbody>{plan_rows}</tbody></table>
<p>Operations: {self.report['operation_coverage']['covered']} / {self.report['operation_coverage']['total']};
pairs: {self.report['pair_coverage']['covered']} / {self.report['pair_coverage']['valid']};
UI: {self.report['ui_coverage']['covered']} / {self.report['ui_coverage']['total']}.</p></body></html>\n"""
        (self.evidence / "coverage.html").write_text(document)

    def finish(self, status: str) -> None:
        cleanup_errors = self.resources.cleanup(self.evidence)
        secret_file = self.evidence / "candidate.env"
        if secret_file.exists():
            secret_file.unlink()
        self.report["infrastructure_errors"].extend(cleanup_errors)
        elapsed = time.monotonic() - self.started
        self.report["timings"].update(finished_at=utc_now(), elapsed_seconds=round(elapsed, 3))
        if elapsed > PROFILE_BUDGETS[self.profile]:
            self.report["failures"].append(
                {"scenario_id": "profile-budget", "signature": "budget-overrun", "message": f"elapsed {elapsed:.1f}s exceeds {PROFILE_BUDGETS[self.profile]}s"}
            )
        clean_pass = (
            status == "passed"
            and not self.report["failures"]
            and not self.report["infrastructure_errors"]
        )
        self.report["status"] = "passed" if clean_pass else (
            "interrupted" if status == "interrupted" else "failed"
        )
        self.save()
        replay = {
            "schema_version": 1,
            "run_id": self.run_id,
            "seed": self.seed,
            "profile": self.profile,
            "command": f"python3 scripts/system_e2e.py --profile {self.profile} --seed {self.seed}",
        }
        (self.evidence / "replay.json").write_text(json.dumps(replay, indent=2) + "\n")
        self.write_summary_artifacts()


def clean_run(run_id: str) -> None:
    if not re.fullmatch(r"[a-f0-9]{24}", run_id):
        raise ContractError("cleanup requires an exact 24-character run ID")
    for resource_type in ("container", "volume", "network"):
        output = command(
            ["docker", resource_type, "ls", "--all", "--quiet", "--filter", f"label={LABEL}={run_id}"]
            if resource_type == "container"
            else ["docker", resource_type, "ls", "--quiet", "--filter", f"label={LABEL}={run_id}"]
        )
        identifiers = [line for line in output.splitlines() if line]
        if identifiers:
            verb = "rm"
            args = ["docker", resource_type, verb]
            if resource_type == "container":
                args.append("--force")
            command([*args, *identifiers])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="validate contracts and generation offline")
    mode.add_argument("--plan", action="store_true", help="print the selected deterministic plan")
    mode.add_argument("--clean", metavar="RUN_ID", help="remove resources with exactly this ownership label")
    parser.add_argument("--profile", choices=sorted(PROFILE_BUDGETS), default="comprehensive")
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()
    try:
        if args.check:
            ledger = validate_contract()
            print(
                f"system E2E contract passed: {len(ledger['operations'])} operations, "
                f"{len(ledger['dashboard_routes'])} UI routes, {ledger['valid_pairs']} valid pairs, "
                f"{len(ledger['scenarios'])} scenarios"
            )
            return 0
        if args.plan:
            print_plan(args.profile)
            return 0
        if args.clean:
            clean_run(args.clean)
            print(f"removed resources owned by system E2E run {args.clean}")
            return 0
        for program in ("docker", "git"):
            if not shutil.which(program):
                raise RuntimeError(f"missing prerequisite: {program}")
        command(["docker", "info"], timeout=30)
        runtime = Runtime(args.profile, args.seed)
        print(f"System E2E evidence: {runtime.evidence}", flush=True)

        def interrupted(*_args: object) -> None:
            raise KeyboardInterrupt

        signal.signal(signal.SIGTERM, interrupted)
        try:
            runtime.execute()
            runtime.finish("failed" if runtime.report["failures"] else "passed")
        except KeyboardInterrupt:
            runtime.finish("interrupted")
            return 130
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            runtime.report["infrastructure_errors"].append(str(error))
            runtime.finish("failed")
        print(f"Report: {runtime.evidence / REPORT_NAME}")
        return 0 if runtime.report["status"] == "passed" else 1
    except (ContractError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"system E2E failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
