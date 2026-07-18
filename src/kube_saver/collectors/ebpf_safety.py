"""Phase 4 eBPF safety and capability checks.

Determines whether the current environment can safely attempt eBPF-based
collection, and provides clear reasons when it cannot.
"""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass, field
from pathlib import Path

MIN_KERNEL_MAJOR = 5
MIN_KERNEL_MINOR = 8


@dataclass
class EbpfSafetyReport:
    """Environment safety report for eBPF support."""

    supported: bool = False
    kernel_version: str = "unknown"
    kernel_ok: bool = False
    bcc_available: bool = False
    running_as_root: bool = False
    in_container: bool = False
    has_bpf_fs: bool = False
    has_trace_fs: bool = False
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if self.supported:
            return "eBPF supported"
        if self.reasons:
            return "; ".join(self.reasons)
        return "eBPF unavailable"


def _parse_kernel_release(release: str) -> tuple[int, int]:
    parts = release.split(".")
    major = int(parts[0]) if parts and parts[0].isdigit() else 0
    minor = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    return major, minor


def _looks_like_container() -> bool:
    if Path("/.dockerenv").exists():
        return True
    try:
        cgroup = Path("/proc/1/cgroup").read_text()
    except Exception:
        return False
    markers = ("docker", "containerd", "kubepods", "lxc")
    return any(marker in cgroup for marker in markers)


def _path_exists_safe(path: str) -> bool:
    """Return True if a system path exists, without failing on PermissionError."""
    try:
        return Path(path).exists()
    except PermissionError:
        return False
    except OSError:
        return False


def check_ebpf_safety() -> EbpfSafetyReport:
    """Check whether the environment is ready for eBPF collection."""
    report = EbpfSafetyReport()

    release = platform.release()
    report.kernel_version = release
    major, minor = _parse_kernel_release(release)
    report.kernel_ok = (major, minor) >= (MIN_KERNEL_MAJOR, MIN_KERNEL_MINOR)
    if not report.kernel_ok:
        report.reasons.append(
            f"kernel {release} is too old; need >= {MIN_KERNEL_MAJOR}.{MIN_KERNEL_MINOR}"
        )

    report.running_as_root = hasattr(os, "geteuid") and os.geteuid() == 0
    if not report.running_as_root:
        report.warnings.append("not running as root; some eBPF probes may fail")

    report.in_container = _looks_like_container()
    if report.in_container:
        report.warnings.append("running inside a container; CAP_BPF/CAP_SYS_ADMIN may be required")

    report.has_bpf_fs = _path_exists_safe("/sys/fs/bpf")
    if not report.has_bpf_fs:
        report.warnings.append("/sys/fs/bpf not mounted")

    report.has_trace_fs = _path_exists_safe("/sys/kernel/debug/tracing") or _path_exists_safe("/sys/kernel/tracing")
    if not report.has_trace_fs:
        report.warnings.append("tracefs/debugfs not available")

    try:
        import bcc  # type: ignore[import-not-found,import-untyped]

        _ = bcc
        report.bcc_available = True
    except Exception:
        report.bcc_available = False
        report.reasons.append("Python BCC bindings are not installed")

    report.supported = report.kernel_ok and report.bcc_available
    return report


__all__ = ["EbpfSafetyReport", "check_ebpf_safety"]
