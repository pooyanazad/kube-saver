"""Check an explicitly reviewed GitHub release before a separate PyPI upload."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from scripts.verify_release import source_version, verify_release


def validate_request(tag: str, commit: str, checksum_sha256: str) -> str:
    """Reject noncanonical versions and unsafe/unpinned release selectors."""
    if not tag.startswith("v"):
        raise ValueError("release tag must start with v")
    version = source_version(f'VERSION = {tag[1:]!r}')
    if tag != f"v{version}":
        raise ValueError("noncanonical release tag")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("expected release commit must be a full SHA")
    if not re.fullmatch(r"[0-9a-f]{64}", checksum_sha256):
        raise ValueError("expected checksum manifest must be a SHA256")
    return version


def validate_artifacts(source: Path, dist: Path, tag: str, checksum_sha256: str) -> None:
    """Pin checksum-manifest bytes, then verify package metadata before installation."""
    manifest = dist / "SHA256SUMS.txt"
    if hashlib.sha256(manifest.read_bytes()).hexdigest() != checksum_sha256:
        raise ValueError("release checksum manifest changed since review")
    version = source_version(source.read_text())
    # This pre-install check verifies metadata only. The workflow separately
    # installs the validated wheel and tests its actual CLI with verify_release.py.
    verify_release(source, dist, f"kube-saver {version}", tag, require_checksums=True)


def validate_release_ci(payload: object, commit: str) -> None:
    """Require the latest main CI run for the selected source to have passed."""
    if not isinstance(payload, dict) or not isinstance(payload.get("workflow_runs"), list):
        raise ValueError("invalid CI run response")
    for run in payload["workflow_runs"]:
        if not isinstance(run, dict):
            continue
        if run.get("path") != ".github/workflows/ci.yml" or run.get("head_sha") != commit:
            continue
        if run.get("event") not in ("push", "workflow_dispatch") or run.get("head_branch") != "main":
            continue
        if run.get("status") != "completed" or run.get("conclusion") != "success":
            raise ValueError("latest release-source main CI is pending or failed")
        return
    raise ValueError("no successful main CI evidence for the release source")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--checksum-sha256", required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--dist-dir", type=Path)
    parser.add_argument("--ci-run-json", type=Path)
    args = parser.parse_args()
    version = validate_request(args.tag, args.expected_commit, args.checksum_sha256)
    if args.ci_run_json:
        validate_release_ci(json.loads(args.ci_run_json.read_text()), args.expected_commit)
    if bool(args.source) != bool(args.dist_dir):
        parser.error("--source and --dist-dir must be used together")
    if args.source and args.dist_dir:
        validate_artifacts(args.source, args.dist_dir, args.tag, args.checksum_sha256)
    print(f"Reviewed PyPI release inputs/metadata verified: {version}")


if __name__ == "__main__":
    main()
