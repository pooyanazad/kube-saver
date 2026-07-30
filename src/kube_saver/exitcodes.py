"""Exit codes for kube-saver CLI automation.

Codes are stable and documented — CI scripts and automation can depend
on them across versions.

Exit code summary:
    0   Success
    1   General / unexpected error
    2   Configuration error (missing kubeconfig, invalid context)
    3   Cluster connection error (API unreachable, auth failure)
    4   Analysis error (data collection failed, partial data)
"""

from __future__ import annotations

# Success — all outputs generated as expected.
OK: int = 0

# General or unexpected error.
GENERAL_ERROR: int = 1

# kubeconfig missing, context not found, or config file malformed.
CONFIG_ERROR: int = 2

# Cluster API unreachable, TLS handshake failed, or authentication rejected.
CONNECTION_ERROR: int = 3

# Analysis or data collection failed mid-run (e.g., API returned
# unexpected shapes, metrics pipeline broken, partial data).
ANALYSIS_ERROR: int = 4


__all__ = [
    "OK",
    "GENERAL_ERROR",
    "CONFIG_ERROR",
    "CONNECTION_ERROR",
    "ANALYSIS_ERROR",
]
