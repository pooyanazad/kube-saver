#!/usr/bin/env bash
# Capture kube-saver CLI output (HTML + Markdown) for the README.
#
# This script runs kube-saver against the local kind demo cluster and writes
# the resulting self-contained HTML report plus a markdown summary to
# docs/screenshots/ so they can be embedded in the README.
#
# Prerequisites:
#   * kind cluster running with the demo workloads from /tmp/big-demo.yaml
#   * kube-saver installed (`pip install -e .` inside the project venv)
#
# Usage:
#   bash scripts/capture_cli.sh
set -euo pipefail

cd "$(dirname "$0")/.."

OUT_DIR="docs/screenshots"
mkdir -p "$OUT_DIR"

# 1) Self-contained HTML report (full demo)
echo "[capture_cli] generating HTML report..."
kube-saver report -o "$OUT_DIR/report.html"

# 2) PR plan files (summary + patches + review) into a dedicated folder
echo "[capture_cli] generating PR plan files..."
rm -rf "$OUT_DIR/pr-plan"
kube-saver pr-plan -d "$OUT_DIR/pr-plan"

# 3) Daily notification markdown files (short, terminal-sized summary)
echo "[capture_cli] generating notification markdown..."
rm -rf "$OUT_DIR/notifications"
kube-saver notify -d "$OUT_DIR/notifications"

# 4) Capture a short terminal recording of a CLI command via asciinema
#    (only if the binary is available — skip silently otherwise).
if command -v asciinema >/dev/null 2>&1; then
    echo "[capture_cli] recording asciinema terminal capture..."
    asciinema rec \
        --quiet \
        --cols 110 \
        --rows 32 \
        --title "kube-saver CLI demo" \
        "$OUT_DIR/cli-demo.cast"
else
    echo "[capture_cli] asciinema not installed; skipping terminal capture."
fi

echo "[capture_cli] done. Files in $OUT_DIR/:"
ls -lh "$OUT_DIR" | sed 's/^/    /'
