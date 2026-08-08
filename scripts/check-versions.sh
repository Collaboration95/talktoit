#!/usr/bin/env bash
# Ensure the app version is stated consistently across the backend
# distribution, frontend package, and the runtime /health banner.
# Gated in CI and in `make check`.
set -euo pipefail
cd "$(dirname "$0")/.."

backend_version=$(sed -n 's/^version = "\([^"]*\)"/\1/p' backend/pyproject.toml | head -n1)
frontend_version=$(sed -n 's/.*"version": *"\([^"]*\)".*/\1/p' frontend/package.json | head -n1)
app_version=$(sed -n 's/^APP_VERSION = "\([^"]*\)"/\1/p' backend/app/main.py | head -n1)

fail=0
for spec in "backend/pyproject.toml:$backend_version" "frontend/package.json:$frontend_version" "backend/app/main.py (APP_VERSION):$app_version"; do
  file=${spec%%:*}
  ver=${spec#*:}
  if [[ -z "$ver" ]]; then
    echo "ERROR: could not parse a version token from $file" >&2
    fail=1
  fi
done

if [[ -n "$backend_version" && "$backend_version" != "$frontend_version" ]]; then
  echo "ERROR: backend ($backend_version) != frontend ($frontend_version) version" >&2
  fail=1
fi
if [[ -n "$backend_version" && "$backend_version" != "$app_version" ]]; then
  echo "ERROR: backend ($backend_version) != runtime APP_VERSION ($app_version)" >&2
  fail=1
fi

if (( fail )); then
  echo "Versions must agree across pyproject.toml, package.json, and main.APP_VERSION." >&2
  exit 1
fi

echo "version-consistent: $backend_version"
