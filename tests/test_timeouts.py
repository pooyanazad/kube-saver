"""Tests for configurable Kubernetes API timeouts (C1.1, C1.2, C1.3).

Covers:
- TimeoutConfig dataclass defaults and normalization
- YAML config parsing of the ``timeouts`` section
- Environment variable overrides (KUBE_SAVER_TIMEOUT_*)
- K8sClient applying operation timeouts to every API call
- run_doctor honoring the operation timeout on version + SAR calls
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from kube_saver.config import (
    KubeSaverConfig,
    TimeoutConfig,
    _apply_env_overrides,
    _build_config,
    default_config_yaml,
    load_config,
)

# ── TimeoutConfig defaults + normalization ─────────────────────────────────


class TestTimeoutConfigDefaults:
    def test_defaults(self) -> None:
        t = TimeoutConfig()
        assert t.connect_seconds == 10.0
        assert t.read_seconds == 30.0
        assert t.operation_seconds == 60.0

    def test_defaults_via_top_level_config(self) -> None:
        cfg = KubeSaverConfig()
        assert cfg.timeouts.connect_seconds == 10.0
        assert cfg.timeouts.read_seconds == 30.0
        assert cfg.timeouts.operation_seconds == 60.0


class TestTimeoutConfigNormalized:
    def test_valid_values_pass_through(self) -> None:
        t = TimeoutConfig(connect_seconds=5, read_seconds=15, operation_seconds=45)
        n = t.normalized()
        assert n.connect_seconds == 5
        assert n.read_seconds == 15
        assert n.operation_seconds == 45

    def test_zero_replaced_with_default(self) -> None:
        t = TimeoutConfig(connect_seconds=0, read_seconds=0, operation_seconds=0)
        n = t.normalized()
        assert n.connect_seconds == 10.0
        assert n.read_seconds == 30.0
        assert n.operation_seconds == 60.0

    def test_negative_replaced_with_default(self) -> None:
        t = TimeoutConfig(connect_seconds=-1, read_seconds=-5, operation_seconds=-10)
        n = t.normalized()
        assert n.connect_seconds == 10.0
        assert n.read_seconds == 30.0
        assert n.operation_seconds == 60.0

    def test_nan_replaced_with_default(self) -> None:
        t = TimeoutConfig(connect_seconds=float("nan"))
        n = t.normalized()
        assert n.connect_seconds == 10.0

    def test_inf_replaced_with_default(self) -> None:
        t = TimeoutConfig(read_seconds=float("inf"))
        n = t.normalized()
        assert n.read_seconds == 30.0

    def test_non_numeric_replaced_with_default(self) -> None:
        t = TimeoutConfig(connect_seconds="not-a-number")  # type: ignore[arg-type]
        n = t.normalized()
        assert n.connect_seconds == 10.0


# ── YAML config parsing ────────────────────────────────────────────────────


class TestBuildConfigTimeouts:
    def test_defaults_when_absent(self) -> None:
        cfg = _build_config({})
        assert cfg.timeouts.connect_seconds == 10.0
        assert cfg.timeouts.read_seconds == 30.0
        assert cfg.timeouts.operation_seconds == 60.0

    def test_custom_values(self) -> None:
        cfg = _build_config(
            {"timeouts": {"connect_seconds": 5, "read_seconds": 20, "operation_seconds": 40}}
        )
        assert cfg.timeouts.connect_seconds == 5
        assert cfg.timeouts.read_seconds == 20
        assert cfg.timeouts.operation_seconds == 40

    def test_invalid_values_normalized(self) -> None:
        cfg = _build_config(
            {"timeouts": {"connect_seconds": 0, "read_seconds": -1, "operation_seconds": "bad"}}
        )
        assert cfg.timeouts.connect_seconds == 10.0
        assert cfg.timeouts.read_seconds == 30.0
        assert cfg.timeouts.operation_seconds == 60.0

    def test_partial_values_keep_defaults_for_missing(self) -> None:
        cfg = _build_config({"timeouts": {"connect_seconds": 7}})
        assert cfg.timeouts.connect_seconds == 7
        assert cfg.timeouts.read_seconds == 30.0
        assert cfg.timeouts.operation_seconds == 60.0


class TestLoadConfigTimeouts:
    def test_loads_from_local_file(self, tmp_path: Path) -> None:
        local = tmp_path / "l.yaml"
        local.write_text(
            "timeouts:\n  connect_seconds: 3\n  read_seconds: 12\n  operation_seconds: 25\n"
        )
        cfg = load_config(global_path=tmp_path / "g.yaml", local_path=local)
        assert cfg.timeouts.connect_seconds == 3
        assert cfg.timeouts.read_seconds == 12
        assert cfg.timeouts.operation_seconds == 25

    def test_invalid_in_file_replaced_with_defaults(self, tmp_path: Path) -> None:
        local = tmp_path / "l.yaml"
        local.write_text("timeouts:\n  connect_seconds: 0\n  read_seconds: -5\n")
        cfg = load_config(global_path=tmp_path / "g.yaml", local_path=local)
        assert cfg.timeouts.connect_seconds == 10.0
        assert cfg.timeouts.read_seconds == 30.0


# ── Environment overrides ──────────────────────────────────────────────────


class TestEnvOverrides:
    def test_connect_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KUBE_SAVER_TIMEOUT_CONNECT", "5")
        cfg = _apply_env_overrides(KubeSaverConfig())
        assert cfg.timeouts.connect_seconds == 5

    def test_read_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KUBE_SAVER_TIMEOUT_READ", "20")
        cfg = _apply_env_overrides(KubeSaverConfig())
        assert cfg.timeouts.read_seconds == 20

    def test_operation_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KUBE_SAVER_TIMEOUT_OPERATION", "45")
        cfg = _apply_env_overrides(KubeSaverConfig())
        assert cfg.timeouts.operation_seconds == 45

    def test_all_three_overrides(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KUBE_SAVER_TIMEOUT_CONNECT", "2")
        monkeypatch.setenv("KUBE_SAVER_TIMEOUT_READ", "8")
        monkeypatch.setenv("KUBE_SAVER_TIMEOUT_OPERATION", "15")
        cfg = _apply_env_overrides(KubeSaverConfig())
        assert cfg.timeouts.connect_seconds == 2
        assert cfg.timeouts.read_seconds == 8
        assert cfg.timeouts.operation_seconds == 15

    def test_invalid_env_replaced_with_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KUBE_SAVER_TIMEOUT_CONNECT", "not-a-number")
        monkeypatch.setenv("KUBE_SAVER_TIMEOUT_READ", "-1")
        monkeypatch.setenv("KUBE_SAVER_TIMEOUT_OPERATION", "0")
        cfg = _apply_env_overrides(KubeSaverConfig())
        assert cfg.timeouts.connect_seconds == 10.0
        assert cfg.timeouts.read_seconds == 30.0
        assert cfg.timeouts.operation_seconds == 60.0

    def test_env_overrides_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        local = tmp_path / "l.yaml"
        local.write_text("timeouts:\n  connect_seconds: 3\n  read_seconds: 12\n")
        monkeypatch.setenv("KUBE_SAVER_TIMEOUT_CONNECT", "7")
        cfg = load_config(global_path=tmp_path / "g.yaml", local_path=local)
        assert cfg.timeouts.connect_seconds == 7
        assert cfg.timeouts.read_seconds == 12  # not overridden


class TestDefaultConfigYamlIncludesTimeouts:
    def test_contains_timeouts_section(self) -> None:
        result = default_config_yaml()
        assert "timeouts" in result
        assert "connect_seconds" in result
        assert "read_seconds" in result
        assert "operation_seconds" in result


# ── K8sClient applies operation timeouts ───────────────────────────────────


def _install_fake_kubernetes(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Patch sys.modules so K8sClient thinks the kubernetes package exists."""
    fake_k8s_client = MagicMock(name="k8s_client")
    fake_k8s_config = MagicMock(name="k8s_config")
    fake_k8s_config.ConfigException = type("ConfigException", (Exception,), {})

    # load_kube_config succeeds by default.
    fake_k8s_config.load_kube_config.return_value = None
    fake_k8s_config.load_incluster_config.return_value = None

    # CoreV1Api / AppsV1Api / VersionApi return mocks.
    fake_core_api = MagicMock(name="CoreV1Api")
    fake_apps_api = MagicMock(name="AppsV1Api")
    fake_version_api = MagicMock(name="VersionApi")
    fake_k8s_client.CoreV1Api.return_value = fake_core_api
    fake_k8s_client.AppsV1Api.return_value = fake_apps_api
    fake_k8s_client.VersionApi.return_value = fake_version_api

    # rest_client with pool_manager for _apply_timeouts_to_clients.
    pool_manager = MagicMock(name="pool_manager")
    pool_manager.connection_pool_kw = {}
    rest_client = MagicMock(name="rest_client")
    rest_client.pool_manager = pool_manager
    api_client = MagicMock(name="api_client")
    api_client.rest_client = rest_client
    fake_core_api.rest_client = rest_client
    fake_core_api.api_client = api_client
    fake_apps_api.rest_client = rest_client
    fake_apps_api.api_client = api_client

    fake_rest_module = MagicMock(name="kubernetes.client.rest")
    fake_rest_module.ApiException = type("ApiException", (Exception,), {})

    fake_pkg = types.ModuleType("kubernetes")
    fake_pkg.client = fake_k8s_client
    fake_pkg.config = fake_k8s_config

    monkeypatch.setitem(sys.modules, "kubernetes", fake_pkg)
    monkeypatch.setitem(sys.modules, "kubernetes.client", fake_k8s_client)
    monkeypatch.setitem(sys.modules, "kubernetes.config", fake_k8s_config)
    monkeypatch.setitem(sys.modules, "kubernetes.client.rest", fake_rest_module)

    from kube_saver.collectors import k8s_client as kmod

    monkeypatch.setattr(kmod, "_K8S_AVAILABLE", True)
    monkeypatch.setattr(kmod, "k8s_client", fake_k8s_client)
    monkeypatch.setattr(kmod, "k8s_config", fake_k8s_config)
    monkeypatch.setattr(kmod, "ApiException", fake_rest_module.ApiException)

    return {
        "client": fake_k8s_client,
        "config": fake_k8s_config,
        "core_api": fake_core_api,
        "apps_api": fake_apps_api,
        "version_api": fake_version_api,
        "pool_manager": pool_manager,
    }


class TestK8sClientTimeouts:
    def test_default_timeouts_on_construction(self) -> None:
        from kube_saver.collectors.k8s_client import K8sClient

        client = K8sClient()
        assert client.timeouts.connect_seconds == 10.0
        assert client.timeouts.read_seconds == 30.0
        assert client.timeouts.operation_seconds == 60.0

    def test_custom_timeouts_accepted(self) -> None:
        from kube_saver.collectors.k8s_client import K8sClient

        t = TimeoutConfig(connect_seconds=3, read_seconds=9, operation_seconds=12)
        client = K8sClient(timeouts=t)
        assert client.timeouts.connect_seconds == 3
        assert client.timeouts.operation_seconds == 12

    def test_connect_applies_pool_timeout(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from kube_saver.collectors.k8s_client import K8sClient

        cfg = tmp_path / "config"
        cfg.write_text("apiVersion: v1\n")
        monkeypatch.setenv("KUBECONFIG", str(cfg))

        fakes = _install_fake_kubernetes(monkeypatch)
        client = K8sClient(timeouts=TimeoutConfig(connect_seconds=4, read_seconds=11))
        client.connect()

        # connect/read tuple pushed into the urllib3 pool.
        assert fakes["pool_manager"].connection_pool_kw["timeout"] == (4, 11)

    def test_get_cluster_info_passes_operation_timeout(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from kube_saver.collectors.k8s_client import K8sClient

        cfg = tmp_path / "config"
        cfg.write_text("apiVersion: v1\n")
        monkeypatch.setenv("KUBECONFIG", str(cfg))

        fakes = _install_fake_kubernetes(monkeypatch)
        version_info = MagicMock()
        version_info.git_version = "v1.30.0"
        fakes["version_api"].get_code.return_value = version_info
        fakes["core_api"].list_node.return_value = MagicMock(items=[])

        client = K8sClient(timeouts=TimeoutConfig(operation_seconds=42))
        client.connect()
        client.get_cluster_info()

        # Version call used the operation timeout.
        _, kwargs = fakes["version_api"].get_code.call_args
        assert kwargs.get("_request_timeout") == 42
        # list_node also used the operation timeout.
        _, kwargs = fakes["core_api"].list_node.call_args
        assert kwargs.get("_request_timeout") == 42

    def test_get_namespaces_passes_operation_timeout(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from kube_saver.collectors.k8s_client import K8sClient

        cfg = tmp_path / "config"
        cfg.write_text("apiVersion: v1\n")
        monkeypatch.setenv("KUBECONFIG", str(cfg))

        fakes = _install_fake_kubernetes(monkeypatch)
        fakes["core_api"].list_namespace.return_value = MagicMock(items=[])

        client = K8sClient(timeouts=TimeoutConfig(operation_seconds=17))
        client.connect()
        client.get_namespaces()

        _, kwargs = fakes["core_api"].list_namespace.call_args
        assert kwargs.get("_request_timeout") == 17

    def test_get_pods_passes_operation_timeout(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from kube_saver.collectors.k8s_client import K8sClient

        cfg = tmp_path / "config"
        cfg.write_text("apiVersion: v1\n")
        monkeypatch.setenv("KUBECONFIG", str(cfg))

        fakes = _install_fake_kubernetes(monkeypatch)
        fakes["core_api"].list_namespaced_pod.return_value = MagicMock(items=[])

        client = K8sClient(timeouts=TimeoutConfig(operation_seconds=23))
        client.connect()
        client.get_pods("default")

        _, kwargs = fakes["core_api"].list_namespaced_pod.call_args
        assert kwargs.get("_request_timeout") == 23

    def test_get_nodes_with_pods_passes_operation_timeout(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from kube_saver.collectors.k8s_client import K8sClient

        cfg = tmp_path / "config"
        cfg.write_text("apiVersion: v1\n")
        monkeypatch.setenv("KUBECONFIG", str(cfg))

        fakes = _install_fake_kubernetes(monkeypatch)
        fakes["core_api"].list_pod_for_all_namespaces.return_value = MagicMock(items=[])

        client = K8sClient(timeouts=TimeoutConfig(operation_seconds=31))
        client.connect()
        client.get_nodes_with_pods()

        _, kwargs = fakes["core_api"].list_pod_for_all_namespaces.call_args
        assert kwargs.get("_request_timeout") == 31


# ── run_doctor honors operation timeout ────────────────────────────────────


def _install_doctor_fake_kubernetes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    contexts: list[dict] | None = None,
    current_context: dict | None = None,
    server_version: str = "v1.30.0",
    sar_allowed: bool = True,
) -> dict:
    """Patch sys.modules for kube_saver.doctor imports."""
    if contexts is None:
        contexts = [{"name": "prod"}]
    if current_context is None:
        current_context = {"name": "prod"}

    fake_k8s_client = MagicMock(name="k8s_client")
    fake_k8s_config = MagicMock(name="k8s_config")
    fake_api_exc_cls = type("ApiException", (Exception,), {})

    fake_k8s_config.ConfigException = type("ConfigException", (Exception,), {})
    fake_k8s_config.list_kube_config_contexts.return_value = (contexts, current_context)

    version_info = MagicMock()
    version_info.git_version = server_version
    fake_k8s_client.VersionApi.return_value.get_code.return_value = version_info

    sar_response = MagicMock()
    sar_response.status.allowed = sar_allowed
    fake_k8s_client.AuthorizationV1Api.return_value.create_self_subject_access_review.return_value = sar_response

    fake_rest_module = MagicMock(name="kubernetes.client.rest")
    fake_rest_module.ApiException = fake_api_exc_cls

    fake_kubernetes_pkg = types.ModuleType("kubernetes")
    fake_kubernetes_pkg.client = fake_k8s_client
    fake_kubernetes_pkg.config = fake_k8s_config

    monkeypatch.setitem(sys.modules, "kubernetes", fake_kubernetes_pkg)
    monkeypatch.setitem(sys.modules, "kubernetes.client", fake_k8s_client)
    monkeypatch.setitem(sys.modules, "kubernetes.config", fake_k8s_config)
    monkeypatch.setitem(sys.modules, "kubernetes.client.rest", fake_rest_module)

    return {"client": fake_k8s_client, "config": fake_k8s_config}


class TestDoctorTimeouts:
    def test_run_doctor_defaults_when_timeouts_none(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from kube_saver.doctor import run_doctor

        cfg = tmp_path / "config"
        cfg.write_text("apiVersion: v1\n")
        monkeypatch.setenv("KUBECONFIG", str(cfg))

        _install_doctor_fake_kubernetes(monkeypatch)
        report = run_doctor()  # timeouts=None → built-in defaults
        assert report.ok, [c.name for c in report.checks if not c.ok]

    def test_run_doctor_passes_operation_timeout_to_version(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from kube_saver.doctor import run_doctor

        cfg = tmp_path / "config"
        cfg.write_text("apiVersion: v1\n")
        monkeypatch.setenv("KUBECONFIG", str(cfg))

        fakes = _install_doctor_fake_kubernetes(monkeypatch)
        run_doctor(timeouts=TimeoutConfig(operation_seconds=19))

        _, kwargs = fakes["client"].VersionApi.return_value.get_code.call_args
        assert kwargs.get("_request_timeout") == 19

    def test_run_doctor_passes_operation_timeout_to_sar(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from kube_saver.doctor import REQUIRED_RBAC, run_doctor

        cfg = tmp_path / "config"
        cfg.write_text("apiVersion: v1\n")
        monkeypatch.setenv("KUBECONFIG", str(cfg))

        fakes = _install_doctor_fake_kubernetes(monkeypatch)
        run_doctor(timeouts=TimeoutConfig(operation_seconds=27))

        sar_calls = fakes["client"].AuthorizationV1Api.return_value.create_self_subject_access_review.call_args_list
        assert len(sar_calls) >= len(REQUIRED_RBAC)
        for _args, kwargs in sar_calls:
            assert kwargs.get("_request_timeout") == 27
