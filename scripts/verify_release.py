"""Verify release artifact versions before publishing; never publish anything."""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
import tarfile
import zipfile
from email.parser import Parser
from pathlib import Path


def source_version(text: str) -> str:
    for node in ast.parse(text).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "VERSION"
            for target in node.targets
        ):
            value = ast.literal_eval(node.value)
            if isinstance(value, str) and re.fullmatch(r"[0-9][A-Za-z0-9.!+_-]*", value):
                return value
    raise ValueError("VERSION must be a literal version string")


def verify_release(source: Path, dist: Path, cli_output: str, tag: str | None = None) -> str:
    """Require exactly one wheel/sdist and agreeing source, metadata and CLI."""
    version = source_version(source.read_text())
    if tag is not None and tag != f"v{version}":
        raise ValueError(f"tag {tag!r} does not match source v{version}")
    versions = {"source": version}
    wheels = list(dist.glob("*.whl"))
    sdists = list(dist.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise ValueError("expected exactly one wheel and one sdist")
    with zipfile.ZipFile(wheels[0]) as wheel:
        paths = [p for p in wheel.namelist() if p.endswith(".dist-info/METADATA")]
        if len(paths) != 1:
            raise ValueError("expected one wheel METADATA")
        metadata = Parser().parsestr(wheel.read(paths[0]).decode())
        if metadata.get("Name") != "kube-saver":
            raise ValueError("unexpected wheel package name")
        versions["wheel metadata"] = metadata.get("Version", "")
        versions["wheel source"] = source_version(wheel.read("kube_saver/version.py").decode())
    with tarfile.open(sdists[0], "r:gz") as sdist:
        paths = [p for p in sdist.getnames() if len(p.split("/")) == 2 and p.endswith("/PKG-INFO")]
        sources = [p for p in sdist.getnames() if p.endswith("/src/kube_saver/version.py")]
        if len(paths) != 1 or len(sources) != 1:
            raise ValueError("expected one sdist PKG-INFO and version source")
        meta_file, version_file = sdist.extractfile(paths[0]), sdist.extractfile(sources[0])
        if meta_file is None or version_file is None:
            raise ValueError("missing sdist metadata/source")
        metadata = Parser().parsestr(meta_file.read().decode())
        if metadata.get("Name") != "kube-saver":
            raise ValueError("unexpected sdist package name")
        versions["sdist metadata"] = metadata.get("Version", "")
        versions["sdist source"] = source_version(version_file.read().decode())
    if cli_output.strip() != f"kube-saver {version}":
        raise ValueError(f"installed CLI version mismatch: {cli_output.strip()!r}")
    mismatches = {name: value for name, value in versions.items() if value != version}
    if mismatches:
        raise ValueError(f"artifact version mismatch: {mismatches}")
    return version


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist-dir", type=Path, default=Path("dist"))
    parser.add_argument("--source", type=Path, default=Path("src/kube_saver/version.py"))
    parser.add_argument("--tag", default=None)
    args = parser.parse_args()
    try:
        cli_output = subprocess.check_output(
            [sys.executable, "-m", "kube_saver.cli", "version"], text=True
        )
        version = verify_release(args.source, args.dist_dir, cli_output, args.tag)
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError, tarfile.TarError, zipfile.BadZipFile) as exc:
        print(f"Release validation failed: {exc}", file=sys.stderr)
        return 1
    print(f"Release versions agree: {version}" + (f" ({args.tag})" if args.tag else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
