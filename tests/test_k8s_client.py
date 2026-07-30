"""Tests for kube-saver K8s client parsing helpers and connection validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from kube_saver.collectors.k8s_client import (
    K8sClient,
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


# ── Fast-fail connection tests (B5) ────────────────────────────────────────


class TestK8sClientConnect:
    """Verify that K8sClient.connect() fails fast with clear messages."""

    def test_connect_missing_kubeconfig(self, monkeypatch, tmp_path) -> None:
        """FileNotFoundError when kubeconfig file does not exist."""
        from kube_saver.collectors.k8s_client import K8sClient

        monkeypatch.delenv("KUBECONFIG", raising=False)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        client = K8sClient()
        with pytest.raises(FileNotFoundError, match="Kubeconfig not found"):
            client.connect()

    def test_connect_bad_context_fails_fast(self, monkeypatch, tmp_path) -> None:
        """ConfigException raised immediately when context does not exist."""
        import sys
        import types
        from unittest.mock import MagicMock

        cfg = tmp_path / "config"
        cfg.write_text("apiVersion: v1\n")
        monkeypatch.setenv("KUBECONFIG", str(cfg))

        fake_client = MagicMock(name="k8s_client")
        fake_config = MagicMock(name="k8s_config")
        fake_config.ConfigException = type("ConfigException", (Exception,), {})
        fake_config.list_kube_config_contexts.return_value = (
            [{"name": "dev"}, {"name": "staging"}],
            {"name": "dev"},
        )

        fake_pkg = types.ModuleType("kubernetes")
        fake_pkg.client = fake_client
        fake_pkg.config = fake_config
        monkeypatch.setitem(sys.modules, "kubernetes", fake_pkg)
        monkeypatch.setitem(sys.modules, "kubernetes.client", fake_client)
        monkeypatch.setitem(sys.modules, "kubernetes.config", fake_config)

        from kube_saver.collectors import k8s_client as kmod

        # Force the module to think kubernetes is available.
        monkeypatch.setattr(kmod, "_K8S_AVAILABLE", True)
        monkeypatch.setattr(kmod, "k8s_client", fake_client)
        monkeypatch.setattr(kmod, "k8s_config", fake_config)

        client = K8sClient(context="production")
        with pytest.raises(fake_config.ConfigException, match="production"):
            client.connect()

    def test_resolve_kubeconfig_path_explicit(self, monkeypatch, tmp_path) -> None:
        cfg = tmp_path / "myconfig"
        cfg.write_text("apiVersion: v1\n")
        monkeypatch.setenv("KUBECONFIG", str(cfg))
        assert K8sClient._resolve_kubeconfig_path() == str(cfg)

    def test_resolve_kubeconfig_path_default(self, monkeypatch, tmp_path) -> None:
        monkeypatch.delenv("KUBECONFIG", raising=False)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        expected = str(tmp_path / ".kube" / "config")
        assert K8sClient._resolve_kubeconfig_path() == expected
