Memory-Mode (MEM) Dumps: Localhost and AWS Docker

Overview

- Memory-mode keeps state in-process (Mongo memory-only). This doc shows how to persist and restore that state via encrypted memory dumps on localhost and on AWS with Docker/ECS.

What’s implemented

- Auto-dump on graceful shutdown, plus signal handlers for SIGTERM/SIGINT/SIGUSR1.
- Encrypted dumps written to `MEM_DUMP_PATH` (native default: `generated/memory_dump.bin`).
- Optional autosave with `MEM_AUTO_SAVE_ENABLED` and `MEM_AUTO_SAVE_FREQ` (seconds). When enabled, it dumps immediately, then waits for the configured interval, with a minimum wait of 60 seconds. Positive environment intervals below 60 are preserved in settings; nonpositive or invalid values use the 900-second default. The settings API requires intervals of at least 60 seconds.
- Frequency strings accept Unicode decimal digits, surrounding whitespace, and underscores between digits, such as `1_200`.
- Settings API interval strings are limited to 4,300 characters, including signs, whitespace, and separators. `PYTHONINTMAXSTRDIGITS` separately limits decimal digits in API interval strings and autosave environment values (default 4,300; `0` disables the digit limit). This setting is read once at startup; disabling it leaves the API character limit in place.
- Security settings are mirrored to `SECURITY_SETTINGS_FILE` (native default: `generated/security_settings.json`). On startup, settings restored from a dump take precedence; the JSON file is a fallback when no settings document exists. The file alone does not restore users or other gateway data.
- Startup selects the dump directory from the saved settings file, falling back to `MEM_DUMP_PATH`, and restores before starting autosave. Settings inside the restored dump then take precedence over the file. A corrupt or wrong-key selected snapshot prevents startup.

Requirements

- `MEM_OR_EXTERNAL=MEM` and `THREADS=1` (single worker for memory mode).
- `MEM_ENCRYPTION_KEY` set to a strong secret (>= 8 chars).
- The directory for `MEM_DUMP_PATH` must be writable and persisted (bind mount or volume).

Localhost (docker compose)

- `docker-compose.yml` mounts the named volume `doorman-generated` at `/app/data` and defaults both persistence paths there. Set `MEM_DUMP_PATH=/app/data/memory_dump.bin` when using a `.env` copied from the native example; its relative path otherwise overrides the Compose default. Any `SECURITY_SETTINGS_FILE` override must also point to a writable, persisted directory.
- Configure environment in `.env` (recommended):

  - `MEM_ENCRYPTION_KEY=some-strong-secret`
  - Optional: `MEM_AUTO_SAVE_ENABLED=true`
  - Optional: `MEM_AUTO_SAVE_FREQ=900`  # seconds (default when enabled)

- Or override via shell when running `docker compose up`.

AWS ECS (task definition outline)

- Persist dumps to a mounted volume (EFS or EBS). Example container config:

  - Mount EFS to `/app/data` (same path used in compose)
  - Set env vars:
    - `MEM_OR_EXTERNAL=MEM`
    - `THREADS=1`
    - `MEM_ENCRYPTION_KEY=your-strong-key`
    - `MEM_DUMP_PATH=/app/data/memory_dump.bin`
    - `SECURITY_SETTINGS_FILE=/app/data/security_settings.json`
    - `MEM_AUTO_SAVE_ENABLED=true`
    - `MEM_AUTO_SAVE_FREQ=900`

- Ensure your service sends `SIGTERM` on scale-in/stop and allows a short drain period so the dump completes.

Signals / Manual dump

- SIGTERM / SIGINT: stops accepting requests, waits for active requests to finish, stops snapshot workers, and writes a final dump using the current security setting's `dump_path`.
- SIGUSR1: writes an on-demand dump using the current security setting's `dump_path` without terminating, even when autosave is disabled.
- HTTP route (requires auth): `POST /platform/memory/dump` accepts optional `{ "path": "<dir or file>" }`.
- HTTP restore requires `manage_security`: `POST /platform/memory/restore`
  accepts `{ "path": "<exact filename returned by dump>" }`. Unlike startup,
  this route does not search for another backup when the file is missing; it
  returns 404/MEM003 without replacing current data.

Verification tips

- After changes (onboard user/API), send SIGUSR1 and check a new `*.bin` in the dump directory.
- Restart the service; logs will report "restored from dump <path>" if a dump exists.

Notes

- Dumps are encrypted (AES-GCM with derived key) using `MEM_ENCRYPTION_KEY`.
- In multi-worker or HA, use Redis-backed persistence and external databases (MEM mode is single-worker only).
