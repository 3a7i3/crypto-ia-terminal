#!/usr/bin/env bash
# scripts/verify_env_separation.sh — ENV-01 Human-Only Environment Verifier
#
# ═══════════════════════════════════════════════════════════════════════════
#  THIS SCRIPT MUST BE RUN BY THE HUMAN OPERATOR.
#  AI agents MUST NOT invoke this script against real runtime secret files
#  (.env / .env.secrets). It may only be executed by an AI against TEMPORARY
#  DUMMY fixtures (see tests/test_verify_env_separation.py) for development
#  and CI purposes.
# ═══════════════════════════════════════════════════════════════════════════
#
# Purpose: sanity-check the separation between the non-secret runtime config
# (.env) and the secret/restricted values (.env.secrets) WITHOUT ever
# printing a single credential value. Only variable NAMES, counts, and
# YES/NO status flags are ever emitted.
#
# Usage:
#   scripts/verify_env_separation.sh [--env PATH] [--secrets PATH]
#                                     [--registry PATH] [--verbose-names]
#
#   --env PATH        Path to the runtime .env file to check
#                      (default: .env in the repo root)
#   --secrets PATH     Path to the runtime .env.secrets file to check
#                      (default: .env.secrets in the repo root)
#   --registry PATH    Path to a newline-separated list of secret-class
#                       variable NAMES expected to live only in .env.secrets
#                       (default: derived from .env.secrets.example)
#   --verbose-names     OPT-IN human-only mode: also print, for each expected
#                       secret variable, NAME=SET or NAME=UNSET. NEVER prints
#                       values, under any flag, in any mode.
#
# Exit code: 0 always (this is a report tool, not a hard gate). Read the
# printed flags — ENV_MODE_OK / SECRETS_MODE_OK / SECRET_KEYS_IN_ENV_COUNT /
# DUPLICATE_WITHIN_ENV_COUNT / DUPLICATE_WITHIN_SECRETS_COUNT /
# CROSS_FILE_DUPLICATE_KEY_COUNT — to decide whether certification criteria
# are met (see docs/architecture/ENVIRONMENT_CONFIGURATION_CONSTITUTION.md
#  § Human .env Certification Contract).
#
# ENV-01R metric definitions (do not confuse these — they measure different
# properties):
#   - DUPLICATE_WITHIN_ENV_COUNT       : same key name appearing more than
#                                         once WITHIN .env itself.
#   - DUPLICATE_WITHIN_SECRETS_COUNT   : same key name appearing more than
#                                         once WITHIN .env.secrets itself.
#   - CROSS_FILE_DUPLICATE_KEY_COUNT   : a key name defined in BOTH .env AND
#                                         .env.secrets (the property named
#                                         "no name defined in both files" in
#                                         the ENV constitution). Computed as
#                                         the size of the intersection of key
#                                         names between the two files — never
#                                         inspects or emits values.
#
# What this script NEVER does:
#   - it never echoes, greps, or otherwise displays the right-hand side
#     (value) of any KEY=VALUE line from .env or .env.secrets
#   - it never sources, exports, or evaluates the files it inspects
#   - it never transmits file contents anywhere
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"
SECRETS_FILE="${REPO_ROOT}/.env.secrets"
REGISTRY_FILE=""
VERBOSE_NAMES=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) ENV_FILE="$2"; shift 2 ;;
    --secrets) SECRETS_FILE="$2"; shift 2 ;;
    --registry) REGISTRY_FILE="$2"; shift 2 ;;
    --verbose-names) VERBOSE_NAMES=1; shift ;;
    -h|--help)
      sed -n '2,40p' "${BASH_SOURCE[0]}"
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

# ── Key-name extraction — NEVER touches the value side of KEY=VALUE ────────
# Strips comments/blank lines, keeps only the NAME portion (left of the
# first '=', trimmed). The value is discarded immediately and never bound
# to a variable, printed, or logged.
extract_key_names() {
  local file="$1"
  [[ -f "$file" ]] || return 0
  grep -vE '^[[:space:]]*(#|$)' "$file" \
    | sed -E 's/^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*=.*/\1/' \
    | grep -E '^[A-Za-z_][A-Za-z0-9_]*$' \
    || true
}

ENV_FILE_PRESENT="NO"
[[ -f "$ENV_FILE" ]] && ENV_FILE_PRESENT="YES"

SECRETS_FILE_PRESENT="NO"
[[ -f "$SECRETS_FILE" ]] && SECRETS_FILE_PRESENT="YES"

# ── File mode checks (metadata only — never content) ───────────────────────
ENV_MODE_OK="N/A"
SECRETS_MODE_OK="N/A"
if [[ "$ENV_FILE_PRESENT" == "YES" ]]; then
  ENV_PERMS="$(stat -c '%a' "$ENV_FILE" 2>/dev/null || stat -f '%Lp' "$ENV_FILE" 2>/dev/null || echo "")"
  # .env is non-secret config — reject world-writable, otherwise OK.
  if [[ -n "$ENV_PERMS" && "${ENV_PERMS: -1}" -lt 2 ]]; then
    ENV_MODE_OK="YES"
  else
    ENV_MODE_OK="NO"
  fi
fi
if [[ "$SECRETS_FILE_PRESENT" == "YES" ]]; then
  SECRETS_PERMS="$(stat -c '%a' "$SECRETS_FILE" 2>/dev/null || stat -f '%Lp' "$SECRETS_FILE" 2>/dev/null || echo "")"
  # .env.secrets must be owner-only readable: 600 or 400.
  if [[ "$SECRETS_PERMS" == "600" || "$SECRETS_PERMS" == "400" ]]; then
    SECRETS_MODE_OK="YES"
  else
    SECRETS_MODE_OK="NO"
  fi
fi

# ── Registry of secret-class names (derived from .env.secrets.example
#    unless --registry overrides it) ────────────────────────────────────────
if [[ -z "$REGISTRY_FILE" ]]; then
  DEFAULT_SECRETS_TEMPLATE="${REPO_ROOT}/.env.secrets.example"
  if [[ -f "$DEFAULT_SECRETS_TEMPLATE" ]]; then
    SECRET_KEY_NAMES="$(extract_key_names "$DEFAULT_SECRETS_TEMPLATE")"
  else
    SECRET_KEY_NAMES=""
  fi
else
  SECRET_KEY_NAMES="$(extract_key_names "$REGISTRY_FILE")"
fi

ENV_KEY_NAMES=""
if [[ "$ENV_FILE_PRESENT" == "YES" ]]; then
  ENV_KEY_NAMES="$(extract_key_names "$ENV_FILE")"
fi

SECRETS_KEY_NAMES=""
if [[ "$SECRETS_FILE_PRESENT" == "YES" ]]; then
  SECRETS_KEY_NAMES="$(extract_key_names "$SECRETS_FILE")"
fi

# ── SECRET_KEYS_IN_ENV_COUNT — secret-class names that leaked into .env ────
SECRET_KEYS_IN_ENV_COUNT=0
if [[ -n "$SECRET_KEY_NAMES" && -n "$ENV_KEY_NAMES" ]]; then
  SECRET_KEYS_IN_ENV_COUNT="$(comm -12 \
    <(printf '%s\n' "$SECRET_KEY_NAMES" | sort -u) \
    <(printf '%s\n' "$ENV_KEY_NAMES" | sort -u) \
    | grep -c . || true)"
fi

# ── DUPLICATE_WITHIN_*_COUNT — same key name defined more than once WITHIN
#    the SAME file (either .env or .env.secrets) ───────────────────────────
count_duplicates() {
  local names="$1"
  [[ -z "$names" ]] && { echo 0; return; }
  printf '%s\n' "$names" | sort | uniq -d | grep -c . || true
}
DUPLICATE_WITHIN_ENV_COUNT="$(count_duplicates "$ENV_KEY_NAMES")"
DUPLICATE_WITHIN_SECRETS_COUNT="$(count_duplicates "$SECRETS_KEY_NAMES")"

# ── CROSS_FILE_DUPLICATE_KEY_COUNT — a key name defined in BOTH .env AND
#    .env.secrets (size of the intersection of key-name sets). This is the
#    "no name defined in both files" property from the ENV constitution —
#    distinct from the within-file duplicate counts above. Only key NAMES
#    are compared; values are never inspected or emitted. ──────────────────
CROSS_FILE_DUPLICATE_KEY_COUNT=0
if [[ -n "$ENV_KEY_NAMES" && -n "$SECRETS_KEY_NAMES" ]]; then
  CROSS_FILE_DUPLICATE_KEY_COUNT="$(comm -12 \
    <(printf '%s\n' "$ENV_KEY_NAMES" | sort -u) \
    <(printf '%s\n' "$SECRETS_KEY_NAMES" | sort -u) \
    | grep -c . || true)"
fi

# ── Sanitized report — counts and status flags only, NEVER values ──────────
echo "ENV_FILE_PRESENT=${ENV_FILE_PRESENT}"
echo "SECRETS_FILE_PRESENT=${SECRETS_FILE_PRESENT}"
echo "ENV_MODE_OK=${ENV_MODE_OK}"
echo "SECRETS_MODE_OK=${SECRETS_MODE_OK}"
echo "SECRET_KEYS_IN_ENV_COUNT=${SECRET_KEYS_IN_ENV_COUNT}"
echo "DUPLICATE_WITHIN_ENV_COUNT=${DUPLICATE_WITHIN_ENV_COUNT}"
echo "DUPLICATE_WITHIN_SECRETS_COUNT=${DUPLICATE_WITHIN_SECRETS_COUNT}"
echo "CROSS_FILE_DUPLICATE_KEY_COUNT=${CROSS_FILE_DUPLICATE_KEY_COUNT}"

if [[ "$VERBOSE_NAMES" -eq 1 && -n "$SECRET_KEY_NAMES" ]]; then
  echo "--- verbose-names (SET/UNSET only — NEVER values) ---"
  while IFS= read -r name; do
    [[ -z "$name" ]] && continue
    if printf '%s\n' "$SECRETS_KEY_NAMES" | grep -qx -- "$name"; then
      echo "${name}=SET"
    else
      echo "${name}=UNSET"
    fi
  done <<< "$(printf '%s\n' "$SECRET_KEY_NAMES" | sort -u)"
fi

exit 0
