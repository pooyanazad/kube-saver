"""Data models for advanced runtime metrics collected in Phase 4."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class NetworkIO:
    rx_bytes: int = 0
    tx_bytes: int = 0
    packets_rx: int = 0
    packets_tx: int = 0

    @property
    def total_bytes(self) -> int:
        return self.rx_bytes + self.tx_bytes


@dataclass
class DiskIO:
    read_bytes: int = 0
    write_bytes: int = 0
    read_ops: int = 0
    write_ops: int = 0

    @property
    def total_bytes(self) -> int:
        return self.read_bytes + self.write_bytes


@dataclass
class MemoryBreakdown:
    rss_bytes: int = 0
    cache_bytes: int = 0
    swap_bytes: int = 0
    working_set_bytes: int = 0


@dataclass
class AdvancedRuntimeMetrics:
    pod_name: str
    namespace: str
    collected_at: datetime = field(default_factory=datetime.now)
    cpu_millicores: float = 0.0
    memory: MemoryBreakdown = field(default_factory=MemoryBreakdown)
    network: NetworkIO = field(default_factory=NetworkIO)
    disk: DiskIO = field(default_factory=DiskIO)
    source: str = "unknown"
    idle_hint: bool = False
    memory_leak_hint: bool = False


__all__ = [
    "AdvancedRuntimeMetrics",
    "DiskIO",
    "MemoryBreakdown",
    "NetworkIO",
]
