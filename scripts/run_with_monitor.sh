#!/usr/bin/env bash
# Monitored `make run`: build the frontend, serve from FastAPI, and print
# basic live memory/RAM stats while uvicorn is up.
#
# macOS-only helper. Uses only built-in tools (ps, sysctl, vm_stat, awk) —
# no extra libraries required. Compatible with macOS's bundled bash 3.2.

set -euo pipefail
cd "$(dirname "$0")/.."

npm --prefix frontend run build

uv run --directory backend uvicorn app.main:app --host 127.0.0.1 --port 8000 &
SERVER_PID=$!

cleanup() {
  kill "$SERVER_PID" 2>/dev/null || true
  wait "$SERVER_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# macOS system memory facts (sampled once; total RAM is constant).
TOTAL_BYTES=$(sysctl -n hw.memsize)
PAGE_SIZE=$(sysctl -n hw.pagesize)

total_gb() { awk -v b="$1" 'BEGIN { printf "%.1f", b / (1024*1024*1024) }'; }

# Extract a field's page count from `vm_stat`, e.g. "Pages free:  12345." -> 12345.
vm_field() {
  awk -v key="$1" '$0 ~ key { gsub(/[^0-9]/, "", $NF); print $NF; exit }'
}

printf '\n[monitor] server started (pid %s) — memory stats every 5s. Ctrl+C to stop.\n' "$SERVER_PID"

while kill -0 "$SERVER_PID" 2>/dev/null; do
  stats=$(vm_stat)

  # Used ≈ active + wired + compressor; "free-ish" ≈ free + inactive + speculative.
  free_pg=$(( $(printf '%s' "$stats" | vm_field 'Pages free') \
            + $(printf '%s' "$stats" | vm_field 'Pages inactive') \
            + $(printf '%s' "$stats" | vm_field 'Pages speculative') ))
  used_pg=$(( $(printf '%s' "$stats" | vm_field 'Pages active') \
            + $(printf '%s' "$stats" | vm_field 'Pages wired down') \
            + $(printf '%s' "$stats" | vm_field 'Pages occupied by compressor') ))

  free_b=$(awk -v p="$PAGE_SIZE" -v n="$free_pg" 'BEGIN { printf "%.0f", p * n }')
  used_b=$(awk -v p="$PAGE_SIZE" -v n="$used_pg" 'BEGIN { printf "%.0f", p * n }')

  rss_kb=$(ps -o rss= -p "$SERVER_PID" | tr -d ' ')
  rss_mb=$(awk -v kb="$rss_kb" 'BEGIN { printf "%.1f", kb / 1024 }')

  printf '[monitor] uvicorn RSS: %s MB | RAM used: %s / %s GB | free-ish: %s GB\n' \
    "$rss_mb" "$(total_gb "$used_b")" "$(total_gb "$TOTAL_BYTES")" "$(total_gb "$free_b")"

  sleep 5
done

printf '[monitor] server stopped\n'
wait "$SERVER_PID"
