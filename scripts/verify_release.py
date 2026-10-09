"""Verify release artifact versions before publishing; never publish anything."""

from __future__ import annotations

import argparse
import ast
import hashlib
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
            if isinstance(value, str) and re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:(?:a|b|rc)[0-9]+|\.post[0-9]+)?", value):
                return value
    raise ValueError("VERSION must be a canonical major.minor.patch version (optional a/b/rc/post suffix)")


def verify_checksums(dist: Path, artifacts: list[Path], required: bool = False) -> None:
    manifest = dist / "SHA256SUMS.txt"
    if not manifest.exists():
        if required:
            raise ValueError("missing SHA256SUMS.txt")
        return
    entries: dict[str, str] = {}
    for line in manifest.read_text().splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (?:dist/)?([^/\\]+)", line)
        if match is None or match[2] in entries:
            raise ValueError("invalid or duplicate checksum entry")
        entries[match[2]] = match[1]
    if set(entries) != {artifact.name for artifact in artifacts}:
        raise ValueError("checksum manifest must cover exactly the wheel and sdist")
    for artifact in artifacts:
        if hashlib.sha256(artifact.read_bytes()).hexdigest() != entries[artifact.name]:
            raise ValueError(f"checksum mismatch: {artifact.name}")


def verify_release(source: Path, dist: Path, cli_output: str, tag: str | None = None, *, require_checksums: bool = False) -> str:
    """Require exactly one wheel/sdist and agreeing source, metadata and CLI."""
    version = source_version(source.read_text())
    if tag is not None and tag != f"v{version}":
        raise ValueError(f"tag {tag!r} does not match source v{version}")
    versions = {"source": version}
    wheels = list(dist.glob("*.whl"))
    sdists = list(dist.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise ValueError("expected exactly one wheel and one sdist")
    verify_checksums(dist, wheels + sdists, require_checksums)
    if {p.name for p in dist.iterdir()} - {wheels[0].name, sdists[0].name, "SHA256SUMS.txt"}:
        raise ValueError("unexpected distribution files")
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
    if not re.fullmatch(rf"kube_saver-{re.escape(version)}-[^-]+-[^-]+-[^-]+\.whl", wheels[0].name):
        raise ValueError("wheel filename does not match source version")
    if sdists[0].name != f"kube_saver-{version}.tar.gz":
        raise ValueError("sdist filename does not match source version")
    return version


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist-dir", type=Path, default=Path("dist"))
    parser.add_argument("--source", type=Path, default=Path("src/kube_saver/version.py"))
    parser.add_argument("--tag", default=None)
    parser.add_argument("--require-checksums", action="store_true")
    args = parser.parse_args()
    try:
        cli_output = subprocess.check_output(
            [sys.executable, "-m", "kube_saver.cli", "version"], text=True
        )
        version = verify_release(args.source, args.dist_dir, cli_output, args.tag, require_checksums=args.require_checksums)
    except (ValueError, SyntaxError, OSError, KeyError, subprocess.CalledProcessError, tarfile.TarError, zipfile.BadZipFile) as exc:
        print(f"Release validation failed: {exc}", file=sys.stderr)
        return 1
    print(f"Release versions agree: {version}" + (f" ({args.tag})" if args.tag else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
