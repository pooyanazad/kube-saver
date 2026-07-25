#!/usr/bin/env bash
# verify-install.sh
# Sanity check that kube-saver works end-to-end after install.
#
# Usage:
#   ./scripts/verify-install.sh
#   ./scripts/verify-install.sh --docker      # also run the Docker image check
#   ./scripts/verify-install.sh --keep-artifacts
#
# Exits 0 if every check passes. Prints a summary at the end.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

KEEP_ARTIFACTS=0
RUN_DOCKER=0

for arg in "$@"; do
  case "$arg" in
    --keep-artifacts) KEEP_ARTIFACTS=1 ;;
    --docker) RUN_DOCKER=1 ;;
    -h|--help)
      echo "Usage: $0 [--docker] [--keep-artifacts]"
      echo ""
      echo "Options:"
      echo "  --docker        Also verify the Docker image runs."
      echo "  --keep-artifacts Keep temp files for inspection."
      exit 0
      ;;
  esac
done

PASS=0
FAIL=0
TMP_DIR="$(mktemp -d -t kube-saver-verify.XXXXXX)"
trap 'if [ "$KEEP_ARTIFACTS" -eq 0 ]; then rm -rf "$TMP_DIR"; else echo "Artifacts kept at: $TMP_DIR"; fi' EXIT

ok() { PASS=$((PASS + 1)); printf "  \033[32m[PASS]\033[0m %s\n" "$1"; }
bad() { FAIL=$((FAIL + 1)); printf "  \033[31m[FAIL]\033[0m %s\n" "$1"; }
hdr() { printf "\n\033[1m== %s ==\033[0m\n" "$1"; }

hdr "1. Python version"
PYTHON_BIN="${PYTHON_BIN:-python3}"
PY_VERSION="$($PYTHON_BIN -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [[ "$PY_VERSION" == "3.10" || "$PY_VERSION" == "3.11" || "$PY_VERSION" == "3.12" ]]; then
  ok "Python $PY_VERSION"
else
  bad "Python $PY_VERSION (need 3.10, 3.11, or 3.12)"
fi

hdr "2. CLI is on PATH"
if command -v kube-saver >/dev/null 2>&1; then
  ok "kube-saver found at $(command -v kube-saver)"
else
  bad "kube-saver not on PATH"
fi

hdr "3. Version command"
if kube-saver version >/dev/null 2>&1; then
  VERSION_OUT="$(kube-saver version 2>&1)"
  ok "kube-saver version: $(echo "$VERSION_OUT" | head -n1)"
else
  bad "kube-saver version failed"
fi

hdr "4. --help renders"
if kube-saver --help >/dev/null 2>&1; then
  ok "kube-saver --help works"
else
  bad "kube-saver --help failed"
fi

hdr "5. report --help renders"
if kube-saver report --help >/dev/null 2>&1; then
  ok "kube-saver report --help works"
else
  bad "kube-saver report --help failed"
fi

hdr "6. Generate a real HTML report"
REPORT_PATH="$TMP_DIR/report.html"
if kube-saver report -o "$REPORT_PATH" >/dev/null 2>&1 && [ -s "$REPORT_PATH" ]; then
  REPORT_BYTES="$(wc -c < "$REPORT_PATH")"
  if [ "$REPORT_BYTES" -gt 1024 ]; then
    ok "Report generated ($REPORT_BYTES bytes)"
  else
    bad "Report suspiciously small ($REPORT_BYTES bytes)"
  fi
else
  bad "Report generation failed (likely no cluster reachable — run inside a cluster context)"
fi

hdr "7. JSON output is parseable"
JSON_PATH="$TMP_DIR/report.json"
if kube-saver report -o "$REPORT_PATH" --json "$JSON_PATH" >/dev/null 2>&1 && [ -s "$JSON_PATH" ]; then
  if $PYTHON_BIN -c "import json,sys; json.load(open('$JSON_PATH'))" 2>/dev/null; then
    ok "JSON output is valid"
  else
    bad "JSON output is not valid JSON"
  fi
else
  bad "JSON output not generated"
fi

hdr "8. notify command writes files"
NOTIFY_DIR="$TMP_DIR/notify"
if kube-saver notify --out-dir "$NOTIFY_DIR" >/dev/null 2>&1; then
  if [ -d "$NOTIFY_DIR" ] && [ "$(ls -A "$NOTIFY_DIR" 2>/dev/null)" ]; then
    ok "notify wrote $(ls "$NOTIFY_DIR" | wc -l) file(s)"
  else
    bad "notify ran but wrote no files"
  fi
else
  bad "notify command failed"
fi

hdr "9. pr-plan command writes files"
PR_DIR="$TMP_DIR/pr-plan"
if kube-saver pr-plan --out-dir "$PR_DIR" >/dev/null 2>&1; then
  if [ -d "$PR_DIR" ] && [ "$(ls -A "$PR_DIR" 2>/dev/null)" ]; then
    ok "pr-plan wrote $(ls "$PR_DIR" | wc -l) file(s)"
  else
    bad "pr-plan ran but wrote no files"
  fi
else
  bad "pr-plan command failed"
fi

hdr "10. serve starts and responds"
SVC_LOG="$TMP_DIR/serve.log"
SVC_PID=""
if kube-saver serve --port 18765 --bind 127.0.0.1 >"$SVC_LOG" 2>&1 &
then
  SVC_PID=$!
  sleep 2
  if curl -sf http://127.0.0.1:18765/ >/dev/null 2>&1; then
    ok "serve responded on 127.0.0.1:18765"
  else
    bad "serve did not respond"
  fi
  if [[ -n "$SVC_PID" ]] && kill -0 "$SVC_PID" 2>/dev/null; then
    kill "$SVC_PID" 2>/dev/null || true
    wait "$SVC_PID" 2>/dev/null || true
  fi
else
  bad "serve command failed to start"
fi

if [ "$RUN_DOCKER" -eq 1 ]; then
  hdr "11. Docker image runs"
  if command -v docker >/dev/null 2>&1; then
    if docker run --rm pooyanazad/kube-saver:latest --version >/dev/null 2>&1; then
      ok "Docker image runs"
    else
      bad "Docker image failed (do you have a kubeconfig mounted?)"
    fi
  else
    bad "docker not installed"
  fi
fi

hdr "Summary"
printf "  Passed: \033[32m%d\033[0m\n  Failed: \033[31m%d\033[0m\n" "$PASS" "$FAIL"

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
echo "All checks passed."
