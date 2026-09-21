#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project="doorman-external-test-$$"
: "${DOORMAN_TEST_MONGO_PORT:=$((27018 + ($$ % 10000)))}"
: "${DOORMAN_TEST_REDIS_PORT:=$((16379 + ($$ % 10000)))}"
export DOORMAN_TEST_MONGO_PORT DOORMAN_TEST_REDIS_PORT
compose=(docker compose --project-name "$project" --file "$repo_root/docker-compose.test.yml")

cleanup() {
  if [[ -n "${DOORMAN_EXTERNAL_STORAGE_LOG_DIR:-}" ]]; then
    mkdir -p "$DOORMAN_EXTERNAL_STORAGE_LOG_DIR"
    "${compose[@]}" logs --no-color > "$DOORMAN_EXTERNAL_STORAGE_LOG_DIR/compose.log" || true
  fi
  "${compose[@]}" down --volumes --remove-orphans
}
trap cleanup EXIT

"${compose[@]}" up --detach --wait
cd "$repo_root"
if [[ -n "${CARGO:-}" ]]; then
  cargo_runner=("$CARGO")
elif command -v cargo >/dev/null 2>&1; then
  cargo_runner=(cargo)
else
  # Keep the external gate runnable on Docker-only Linux hosts. The test
  # services are published on loopback, so the temporary toolchain container
  # needs the host network to reach them.
  cargo_runner=(
    docker run --rm --network host
    -e CARGO_HOME=/tmp/cargo
    -e CARGO_TARGET_DIR=/tmp/target
    -v "$repo_root:/workspace:ro"
    -w /workspace
    rust:1.88-slim
    cargo
  )
fi

external_test=(
  env
  DOORMAN_EXTERNAL_STORAGE_TEST=1
  "DOORMAN_TEST_MONGO_PORT=$DOORMAN_TEST_MONGO_PORT"
  "DOORMAN_TEST_REDIS_PORT=$DOORMAN_TEST_REDIS_PORT"
  "${cargo_runner[@]}"
  test
  --manifest-path gateway-rs/Cargo.toml
  --locked
  --test external_storage
)

if [[ -n "${EXTERNAL_STORAGE_LOG:-}" ]]; then
  mkdir -p "$(dirname "$EXTERNAL_STORAGE_LOG")"
  "${external_test[@]}" 2>&1 | tee "$EXTERNAL_STORAGE_LOG"
else
  "${external_test[@]}"
fi
