"""Tests for kube-saver K8s client parsing helpers."""

from kube_saver.collectors.k8s_client import (
    _parse_cpu_to_millicores,
    _parse_memory_to_bytes,
)


class TestParseCpu:
    def test_millicores(self) -> None:
        assert _parse_cpu_to_millicores("500m") == 500.0

    def test_full_cores(self) -> None:
        assert _parse_cpu_to_millicores("2") == 2000.0
        assert _parse_cpu_to_millicores("1") == 1000.0

    def test_decimal_cores(self) -> None:
        assert _parse_cpu_to_millicores("0.5") == 500.0
        assert _parse_cpu_to_millicores("2.5") == 2500.0

    def test_empty_returns_zero(self) -> None:
        assert _parse_cpu_to_millicores(None) == 0.0
        assert _parse_cpu_to_millicores("") == 0.0


class TestParseMemory:
    def test_mebibytes(self) -> None:
        assert _parse_memory_to_bytes("256Mi") == 256 * 1024 * 1024

    def test_gibibytes(self) -> None:
        assert _parse_memory_to_bytes("1Gi") == 1024**3
        assert _parse_memory_to_bytes("4Gi") == 4 * 1024**3

    def test_kibibytes(self) -> None:
        assert _parse_memory_to_bytes("512Ki") == 512 * 1024

    def test_kilobytes_decimal(self) -> None:
        assert _parse_memory_to_bytes("1000K") == 1_000_000

    def test_plain_bytes(self) -> None:
        assert _parse_memory_to_bytes("1024") == 1024

    def test_empty_returns_zero(self) -> None:
        assert _parse_memory_to_bytes(None) == 0
        assert _parse_memory_to_bytes("") == 0
