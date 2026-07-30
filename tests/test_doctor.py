"""Tests for ``kube-saver doctor``."""

from __future__ import annotations

import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from kube_saver.doctor import (
    REQUIRED_RBAC,
    CheckResult,
    DoctorReport,
    _resolve_kubeconfig_path,
    run_doctor,
)

# ── Unit tests for helpers ────────────────────────────────────────────────


class TestResolveKubeconfigPath:
    def test_explicit_env_var(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = tmp_path / "config"
        cfg.write_text("apiVersion: v1\n")
        monkeypatch.setenv("KUBECONFIG", str(cfg))
        assert _resolve_kubeconfig_path() == str(cfg)

    def test_env_var_multiple(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        a = tmp_path / "a"
        a.write_text("apiVersion: v1\n")
        b = tmp_path / "b"
        b.write_text("apiVersion: v1\n")
        monkeypatch.setenv("KUBECONFIG", f"{a}{os.pathsep}{b}")
        assert _resolve_kubeconfig_path() == str(a)

    def test_default_home(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.delenv("KUBECONFIG", raising=False)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        assert _resolve_kubeconfig_path() == str(tmp_path / ".kube" / "config")

    def test_default_home_exists(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.delenv("KUBECONFIG", raising=False)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        kube_dir = tmp_path / ".kube"
        kube_dir.mkdir()
        (kube_dir / "config").write_text("apiVersion: v1\n")
        assert _resolve_kubeconfig_path() == str(kube_dir / "config")


class TestRender:
    def test_render_no_color(self) -> None:
        report = DoctorReport(
            kubeconfig_path="/tmp/kubeconfig",
            context="prod",
            checks=[
                CheckResult(name="kubeconfig", ok=True, detail="found"),
                CheckResult(name="cluster reachable", ok=False, detail="nope", hint="check VPN"),
            ],
        )
        out = report.render(use_color=False)
        assert "kubeconfig" in out
        assert "cluster reachable" in out
        assert "1 check(s) failed" in out

    def test_render_all_pass(self) -> None:
        report = DoctorReport(
            checks=[CheckResult(name="ok-check", ok=True, detail="yep")],
        )
        out = report.render(use_color=False)
        assert "All checks passed" in out
        assert report.ok is True


# ── Helpers ────────────────────────────────────────────────────────────────


def _fake_api_exception(*args, **kwargs):
    """Creates a fake ApiException. Ignores constructor args."""
    exc = Exception(*args)
    exc.__class__ = type("ApiException", (Exception,), {})
    return exc


def _install_fake_kubernetes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    contexts: list[dict] | None = None,
    current_context: dict | None = None,
    server_version: str = "v1.30.0",
    sar_allowed: bool = True,
    version_error: Exception | None = None,
) -> dict:
    """Patch ``sys.modules`` so the kubernetes imports inside
    ``kube_saver.doctor`` resolve to mock objects.

    Returns a dict with ``client`` and ``config`` keys for assertions.
    """
    if contexts is None:
        contexts = [{"name": "prod"}]
    if current_context is None:
        current_context = {"name": "prod"}

    fake_k8s_client = MagicMock(name="k8s_client")
    fake_k8s_config = MagicMock(name="k8s_config")
    fake_api_exc_cls = type("ApiException", (Exception,), {})

    fake_k8s_config.ConfigException = type("ConfigException", (Exception,), {})
    fake_k8s_config.list_kube_config_contexts.return_value = (contexts, current_context)

    if version_error is None:
        version_info = MagicMock()
        version_info.git_version = server_version
        fake_k8s_client.VersionApi.return_value.get_code.return_value = version_info
    else:
        fake_k8s_client.VersionApi.return_value.get_code.side_effect = version_error

    sar_response = MagicMock()
    sar_response.status.allowed = sar_allowed
    fake_k8s_client.AuthorizationV1Api.return_value.create_self_subject_access_review.return_value = sar_response

    fake_rest_module = MagicMock(name="kubernetes.client.rest")
    fake_rest_module.ApiException = fake_api_exc_cls

    # Create a fake kubernetes package that exposes `client` and `config` as
    # attributes that resolve to the same modules registered in sys.modules.
    fake_kubernetes_pkg = types.ModuleType("kubernetes")
    fake_kubernetes_pkg.client = fake_k8s_client
    fake_kubernetes_pkg.config = fake_k8s_config

    monkeypatch.setitem(sys.modules, "kubernetes", fake_kubernetes_pkg)
    monkeypatch.setitem(sys.modules, "kubernetes.client", fake_k8s_client)
    monkeypatch.setitem(sys.modules, "kubernetes.config", fake_k8s_config)
    monkeypatch.setitem(sys.modules, "kubernetes.client.rest", fake_rest_module)

    return {"client": fake_k8s_client, "config": fake_k8s_config}


# ── Failure scenarios ─────────────────────────────────────────────────────


class TestRunDoctorFailures:
    def test_no_kubeconfig(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.delenv("KUBECONFIG", raising=False)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        report = run_doctor()
        assert not report.ok
        assert report.checks[0].name == "kubeconfig"
        assert report.checks[0].ok is False

    def test_missing_kubernetes_package(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        cfg = tmp_path / "config"
        cfg.write_text("apiVersion: v1\n")
        monkeypatch.setenv("KUBECONFIG", str(cfg))

        import builtins

        original_import = builtins.__import__

        def _fake_import(name, *args, **kwargs):
            if name == "kubernetes":
                raise ImportError("simulated missing kubernetes")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _fake_import)

        report = run_doctor()
        assert not report.ok
        names = [c.name for c in report.checks]
        assert "kubeconfig" in names
        assert "kubernetes client" in names

    def test_cluster_unreachable(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        cfg = tmp_path / "config"
        cfg.write_text("apiVersion: v1\n")
        monkeypatch.setenv("KUBECONFIG", str(cfg))

        _install_fake_kubernetes(
            monkeypatch,
            contexts=[{"name": "prod"}],
            current_context={"name": "prod"},
            version_error=Exception("API unreachable"),
        )

        report = run_doctor(context="prod")
        assert not report.ok
        cluster_check = next(c for c in report.checks if c.name == "cluster reachable")
        assert cluster_check.ok is False

    def test_unknown_context(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        cfg = tmp_path / "config"
        cfg.write_text("apiVersion: v1\n")
        monkeypatch.setenv("KUBECONFIG", str(cfg))

        _install_fake_kubernetes(
            monkeypatch,
            contexts=[{"name": "dev"}],
            current_context={"name": "dev"},
        )

        report = run_doctor(context="nope")
        assert not report.ok
        ctx_check = next(c for c in report.checks if c.name == "context")
        assert ctx_check.ok is False


# ── Success scenarios ─────────────────────────────────────────────────────


class TestRunDoctorSuccess:
    def test_all_checks_pass(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        cfg = tmp_path / "config"
        cfg.write_text("apiVersion: v1\n")
        monkeypatch.setenv("KUBECONFIG", str(cfg))

        _install_fake_kubernetes(
            monkeypatch,
            contexts=[{"name": "prod"}, {"name": "dev"}],
            current_context={"name": "prod"},
            sar_allowed=True,
        )

        report = run_doctor()
        assert report.ok, [c.name for c in report.checks if not c.ok]
        assert report.context == "prod"
        assert report.server_version == "v1.30.0"
        names = {c.name for c in report.checks}
        assert "kubeconfig" in names
        assert "context" in names
        assert "cluster reachable" in names
        for api_group, kind, verb in REQUIRED_RBAC:
            display_name = f"{api_group}/{kind}" if api_group else kind
            assert f"rbac {verb} {display_name}" in names

    def test_sar_constructs_resource_attributes(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Each RBAC check should be sent as a SAR with proper resource_attributes."""
        cfg = tmp_path / "config"
        cfg.write_text("apiVersion: v1\n")
        monkeypatch.setenv("KUBECONFIG", str(cfg))

        fakes = _install_fake_kubernetes(
            monkeypatch,
            contexts=[{"name": "prod"}],
            current_context={"name": "prod"},
            sar_allowed=True,
        )

        run_doctor()
        # Each SAR call should have used V1ResourceAttributes(resource=..., verb=...)
        # and wrapped it in V1SelfSubjectAccessReviewSpec(resource_attributes=...).
        client = fakes["client"]
        assert client.V1ResourceAttributes.called, "V1ResourceAttributes was not constructed"
        assert client.V1SelfSubjectAccessReviewSpec.called, "V1SelfSubjectAccessReviewSpec was not constructed"

        # Verify resource/verb were passed to V1ResourceAttributes for at least one call.
        ra_calls = client.V1ResourceAttributes.call_args_list
        kinds_passed = {call.kwargs.get("resource") for call in ra_calls}
        verbs_passed = {call.kwargs.get("verb") for call in ra_calls}
        assert REQUIRED_RBAC[0][1] in kinds_passed
        assert REQUIRED_RBAC[0][2] in verbs_passed

    def test_rbac_denied(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        cfg = tmp_path / "config"
        cfg.write_text("apiVersion: v1\n")
        monkeypatch.setenv("KUBECONFIG", str(cfg))

        _install_fake_kubernetes(
            monkeypatch,
            contexts=[{"name": "prod"}],
            current_context={"name": "prod"},
            sar_allowed=False,
        )

        report = run_doctor()
        assert not report.ok
        denied = [c for c in report.checks if c.name.startswith("rbac") and not c.ok]
        assert denied, "at least one RBAC check should fail"


# ── CLI integration ───────────────────────────────────────────────────────


class TestDoctorCli:
    def test_cli_doctor_passes(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        from click.testing import CliRunner

        from kube_saver.cli import cli as click_cli

        cfg = tmp_path / "config"
        cfg.write_text("apiVersion: v1\n")
        monkeypatch.setenv("KUBECONFIG", str(cfg))

        _install_fake_kubernetes(
            monkeypatch,
            contexts=[{"name": "prod"}],
            current_context={"name": "prod"},
            sar_allowed=True,
        )

        runner = CliRunner()
        result = runner.invoke(click_cli, ["doctor"], color=False)
        assert result.exit_code == 0, result.output
        assert "kubeconfig" in result.output
        assert "cluster reachable" in result.output

    def test_cli_doctor_fails_no_kubeconfig(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        from click.testing import CliRunner

        from kube_saver.cli import cli as click_cli

        monkeypatch.delenv("KUBECONFIG", raising=False)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        runner = CliRunner()
        result = runner.invoke(click_cli, ["doctor"], color=False)
        assert result.exit_code == 1
        assert "kubeconfig" in result.output
