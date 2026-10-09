"""Validate the OCI labels needed for Artifact Hub, without changing an image."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from scripts.verify_release import source_version


def verify_labels(labels: object, version: str, revision: str) -> None:
    """Require source-specific labels and a real UTC build timestamp."""
    source_version(f'VERSION = {version!r}')
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("revision must be a full commit SHA")
    if not isinstance(labels, dict):
        raise ValueError("image config labels are missing")
    expected = {
        "io.artifacthub.package.readme-url":
            f"https://raw.githubusercontent.com/pooyanazad/kube-saver/{revision}/README.md",
        "org.opencontainers.image.description":
            "Kubernetes cost estimates and resource right-sizing with local reports and review plans.",
        "org.opencontainers.image.documentation": "https://pooyanazad.github.io/kube-saver/",
        "org.opencontainers.image.source": "https://github.com/pooyanazad/kube-saver",
        "org.opencontainers.image.revision": revision,
        "org.opencontainers.image.version": version,
        "org.opencontainers.image.licenses": "MIT",
    }
    for key, value in expected.items():
        if labels.get(key) != value:
            raise ValueError(f"missing or incorrect image label: {key}")
    created = labels.get("org.opencontainers.image.created")
    if not isinstance(created, str) or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", created):
        raise ValueError("created must be an RFC3339 UTC timestamp")
    parsed = datetime.strptime(created, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    if parsed > datetime.now(timezone.utc):
        raise ValueError("image creation timestamp is in the future")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("labels", type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    verify_labels(json.loads(args.labels.read_text()), args.version, args.revision)
    print("Image metadata agrees with the tested source and package version.")


if __name__ == "__main__":
    main()
