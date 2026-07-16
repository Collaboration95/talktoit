#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
env_file="$repo_root/.env"

if [[ ! -f "$env_file" ]]; then
  echo "Missing .env file at $env_file" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$env_file"
set +a

: "${LLM_API_KEY:?LLM_API_KEY is required in .env}"
LLM_BASE_URL="${LLM_BASE_URL:-https://api.groq.com/openai/v1}"
LLM_MODEL="${LLM_MODEL:-llama-3.3-70b-versatile}"

prompt="${*:-Say hello in one short sentence.}"

payload="$(cat <<EOF
{
  "model": "${LLM_MODEL}",
  "messages": [
    {"role": "user", "content": "${prompt//\"/\\\"}"}
  ],
  "temperature": 0.2
}
EOF
)"

curl --fail-with-body --silent --show-error \
  "${LLM_BASE_URL%/}/chat/completions" \
  -H "Authorization: Bearer ${LLM_API_KEY}" \
  -H "Content-Type: application/json" \
  --data "$payload"
