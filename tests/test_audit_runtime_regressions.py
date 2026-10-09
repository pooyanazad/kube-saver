"""Behavior checks for the P0 configuration and recommendation findings."""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from kube_saver import cli as cli_mod
from kube_saver import config as config_mod
from kube_saver.analyzers.resource_waste import analyze_resource_waste
from kube_saver.config import KubeSaverConfig, PricingOverrides, SafetyConfig
from kube_saver.models.core import (
    ActualUsage,
    CloudProvider,
    ContainerResourceInfo,
    MetricSource,
    NamespaceInfo,
    PodResourceInfo,
    ResourceQuantities,
)
from kube_saver.pricing.engine import PricingEngine
from kube_saver.recommenders.engine import generate_recommendations
from kube_saver.tui import data as tui_data
from tests.test_cli_analysis import _FakeClient, _MeasuredRuntime


@pytest.mark.parametrize("explicit", [None, "override"])
def test_doctor_checks_the_context_used_by_scans(monkeypatch, explicit):
    from kube_saver import doctor as doctor_mod

    calls = []
    monkeypatch.setattr(config_mod, "load_config", lambda: KubeSaverConfig(kubeconfig_context="configured"))
    monkeypatch.setattr(doctor_mod, "run_doctor", lambda **kwargs: (
        calls.append(kwargs) or SimpleNamespace(ok=True, render=lambda **_: "ok")
    ))
    args = ["doctor"] + (["--context", explicit] if explicit else [])
    assert CliRunner().invoke(cli_mod.cli, args).exit_code == 0
    assert calls[0]["context"] == (explicit or "configured")


@pytest.mark.parametrize("pipeline", ["cli", "tui"])
@pytest.mark.parametrize("dimension", ["cpu", "memory"])
def test_single_rate_override_preserves_the_other_provider_rate(monkeypatch, pipeline, dimension):
    class Client(_FakeClient):
        def get_cluster_info(self):
            return None

    class Runtime(_MeasuredRuntime):
        def collect_all_pods(self, pods):
            super().collect_all_pods(pods)
            return SimpleNamespace(metrics_available=True, source=MetricSource.METRICS_SERVER, warnings=[])

    overrides = PricingOverrides(
        cpu_per_core_hour_usd=0.1 if dimension == "cpu" else 0,
        memory_per_gb_hour_usd=0.01 if dimension == "memory" else 0,
    )
    cfg = KubeSaverConfig(cloud_provider=CloudProvider.AWS, pricing=overrides)
    module = cli_mod if pipeline == "cli" else tui_data
    monkeypatch.setattr(module, "K8sClient", Client)
    monkeypatch.setattr(module, "RuntimeCollector", Runtime)
    monkeypatch.setattr(config_mod, "load_config", lambda: cfg)
    report = cli_mod._run_analysis()[1] if pipeline == "cli" else tui_data.load_data(cfg).cost_report
    cpu_rate = 0.1 if dimension == "cpu" else 0.042
    mem_rate = 0.01 if dimension == "memory" else 0.005
    assert report is not None
    assert report.total_requested_cost.monthly_usd == pytest.approx(730 * (cpu_rate + mem_rate))


def pod(name="api-a", cpu=50, memory=10 * 1024**2):
    return PodResourceInfo(
        name=name, namespace="prod", workload_kind="Deployment", workload_name="api",
        containers=[ContainerResourceInfo(name="api")],
        resources=ResourceQuantities(cpu_millicores_request=1000, memory_bytes_request=2 * 1024**3),
        actual=ActualUsage(cpu_millicores=cpu, memory_bytes=memory, source=MetricSource.METRICS_SERVER),
    )


def recommend(pods, cfg=None):
    report = analyze_resource_waste([NamespaceInfo(name="prod")], pods, metrics_available=True)
    return generate_recommendations(report, PricingEngine(), config=cfg)


def test_busy_non_candidate_replica_prevents_cpu_downsize():
    recs = recommend([pod(), pod("api-b", cpu=900)])
    assert not any(rec.resource_type == "cpu-request" for rec in recs)


@pytest.mark.parametrize("missing", ["estimated", "excluded", "sidecar"])
def test_controller_patch_cannot_bypass_an_ineligible_sibling(missing):
    sibling = pod("api-b")
    cfg = KubeSaverConfig(exclude_labels={"protected": "true"})
    if missing == "estimated":
        sibling.actual.source = MetricSource.ESTIMATED
    elif missing == "excluded":
        sibling.labels["protected"] = "true"
    else:
        sibling.containers.append(ContainerResourceInfo(name="sidecar"))
    assert recommend([pod(), sibling], cfg) == []


def test_resource_formatting_never_rounds_below_the_usage_buffer():
    observed = pod(cpu=100.1, memory=int(0.99 * 1024**3))
    recs = recommend([observed])
    cpu = next(rec for rec in recs if rec.resource_type == "cpu-request")
    memory = next(rec for rec in recs if rec.resource_type == "memory-request")
    assert int(cpu.suggested_value[:-1]) >= observed.actual.cpu_millicores * 1.5
    assert int(memory.suggested_value[:-2]) * 1024**2 >= observed.actual.memory_bytes * 1.2


@pytest.mark.parametrize("aggressive,expected", [(False, 500), (True, 300)])
def test_configured_absolute_and_relative_floors_take_effect(aggressive, expected):
    cfg = KubeSaverConfig(safety=SafetyConfig(min_cpu_millicores=300, aggressive_mode=aggressive))
    rec = next(rec for rec in recommend([pod()], cfg) if rec.resource_type == "cpu-request")
    assert rec.suggested_value == f"{expected}m"


def test_invalid_safety_floors_do_not_disable_protection():
    cfg = KubeSaverConfig(safety=replace(SafetyConfig(), min_cpu_millicores=float("nan"), prod_cpu_floor_ratio=-1))
    rec = next(rec for rec in recommend([pod()], cfg) if rec.resource_type == "cpu-request")
    assert rec.suggested_value == "500m"


def test_defaults_yaml_includes_both_relative_floor_controls():
    import yaml

    assert yaml.safe_load(config_mod.default_config_yaml())["prod_memory_floor_ratio"] == 0.5


@pytest.mark.parametrize("value", ["false", "true", 1, None])
def test_aggressive_mode_requires_an_explicit_boolean(value):
    cfg = KubeSaverConfig(safety=SafetyConfig(aggressive_mode=value))
    rec = next(r for r in recommend([pod()], cfg) if r.resource_type == "cpu-request")
    assert rec.suggested_value == "500m"


def test_non_candidate_sibling_also_controls_confidence_and_reason():
    recs = recommend([pod(), pod("api-b", cpu=610)])
    rec = next(r for r in recs if r.resource_type == "cpu-request")
    assert rec.suggested_value == "915m"
    assert rec.confidence == "low"
    assert "61%" in rec.reason


def test_rolling_request_changes_suppress_only_the_ambiguous_resource():
    sibling = pod("api-b")
    sibling.resources.cpu_millicores_request = 800
    recs = recommend([pod(), sibling])
    assert not any(r.resource_type == "cpu-request" for r in recs)
    assert any(r.resource_type == "memory-request" for r in recs)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1])
def test_invalid_measured_usage_suppresses_the_workload(value):
    sibling = pod("api-b", cpu=value)
    assert recommend([pod(), sibling]) == []


@pytest.mark.parametrize("pipeline", ["cli", "tui"])
@pytest.mark.parametrize("value", [float("inf"), "0.1", "invalid", None])
def test_invalid_custom_rate_cannot_crash_or_poison_costs(monkeypatch, pipeline, value):
    overrides = PricingOverrides(cpu_per_core_hour_usd=value)
    cfg = KubeSaverConfig(cloud_provider=CloudProvider.AWS, pricing=overrides)
    module = cli_mod if pipeline == "cli" else tui_data
    class Client(_FakeClient):
        def get_cluster_info(self):
            return None
    monkeypatch.setattr(module, "K8sClient", Client)
    monkeypatch.setattr(module, "RuntimeCollector", _MeasuredRuntime)
    monkeypatch.setattr(config_mod, "load_config", lambda: cfg)
    if pipeline == "tui":
        class Runtime(_MeasuredRuntime):
            def collect_all_pods(self, pods):
                super().collect_all_pods(pods)
                return SimpleNamespace(metrics_available=True, source=MetricSource.METRICS_SERVER, warnings=[])
        monkeypatch.setattr(module, "RuntimeCollector", Runtime)
    report = cli_mod._run_analysis()[1] if pipeline == "cli" else tui_data.load_data(cfg).cost_report
    assert report is not None
    expected_cpu = 0.1 if value == "0.1" else 0.042
    assert report.total_requested_cost.monthly_usd == pytest.approx(730 * (expected_cpu + 0.005))


@pytest.mark.parametrize("defect", ["empty", "missing-cpu", "missing-memory", "bad-cpu", "negative", "wrong-container", "bad-timestamp"])
def test_incomplete_metrics_never_generate_a_plan(monkeypatch, defect):
    from datetime import datetime, timezone

    from kube_saver.collectors import metrics as metrics_mod
    from kube_saver.collectors.runtime import RuntimeCollector

    observed = pod()
    item = {
        "metadata": {"name": observed.name},
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "containers": [{"name": "api", "usage": {"cpu": "10m", "memory": "10Mi"}}],
    }
    if defect == "empty":
        item["containers"] = []
    elif defect == "bad-timestamp":
        item["timestamp"] = "unknown"
    elif defect == "wrong-container":
        item["containers"][0]["name"] = "other"
    else:
        usage = item["containers"][0]["usage"]
        if defect.startswith("missing"):
            del usage[defect.removeprefix("missing-")]
        else:
            usage["cpu"] = "invalid" if defect == "bad-cpu" else "-1m"
    api = SimpleNamespace(list_namespaced_custom_object=lambda **_: {"items": [item]})
    monkeypatch.setattr(metrics_mod, "k8s_client", SimpleNamespace(CustomObjectsApi=lambda: api))
    runtime = RuntimeCollector(prefer_ebpf=False)
    runtime.collect_all_pods([observed])
    assert observed.actual.source is MetricSource.ESTIMATED
    assert recommend([observed]) == []


def test_microcore_metrics_preserve_usage_headroom(monkeypatch):
    from datetime import datetime, timezone

    from kube_saver.collectors import metrics as metrics_mod
    observed = pod()
    api = SimpleNamespace(list_namespaced_custom_object=lambda **_: {"items": [{
        "metadata": {"name": observed.name},
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "containers": [{"name": "api", "usage": {"cpu": "100100u", "memory": "10Mi"}}],
    }]})
    monkeypatch.setattr(metrics_mod, "k8s_client", SimpleNamespace(CustomObjectsApi=lambda: api))
    metrics_mod.MetricsCollector().collect_all_pods([observed])
    assert observed.actual.cpu_millicores == pytest.approx(100.1)
    rec = next(r for r in recommend([observed]) if r.resource_type == "cpu-request")
    assert rec.suggested_value == "151m"


def test_future_metric_timestamp_is_not_treated_as_fresh():
    from datetime import datetime, timedelta, timezone

    from kube_saver.collectors.runtime import RuntimeCollector
    runtime = RuntimeCollector(prefer_ebpf=False)
    observed = pod()
    observed.actual.observed_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1)
    runtime.metrics.available = True
    runtime.metrics.collect_all_pods = lambda _: {"prod/api-a": observed.actual}
    runtime.collect_all_pods([observed])
    assert observed.actual.source is MetricSource.ESTIMATED


@pytest.mark.parametrize("scoped", [True, False])
def test_metrics_reads_are_bounded_and_transport_failure_falls_back(monkeypatch, scoped):
    from urllib3.exceptions import ReadTimeoutError

    from kube_saver.collectors import metrics as metrics_mod
    from kube_saver.config import TimeoutConfig
    calls = []
    def timeout(**kwargs):
        calls.append(kwargs)
        raise ReadTimeoutError(None, '/metrics', 'test timeout')
    api = SimpleNamespace(list_namespaced_custom_object=timeout, list_cluster_custom_object=timeout)
    monkeypatch.setattr(metrics_mod, "k8s_client", SimpleNamespace(CustomObjectsApi=lambda: api))
    collector = metrics_mod.MetricsCollector(timeouts=TimeoutConfig(operation_seconds=7))
    assert collector.collect_pod_metrics([pod()], namespace="prod" if scoped else None) == {}
    assert calls[0]["_request_timeout"] == 7
    assert collector.available is False


def test_doctor_reports_the_explicit_context_not_kubeconfig_current(monkeypatch, tmp_path):
    from kube_saver.doctor import run_doctor
    from tests.test_doctor import _install_fake_kubernetes
    kubeconfig = tmp_path / "config"
    kubeconfig.write_text("apiVersion: v1\n")
    monkeypatch.setenv("KUBECONFIG", str(kubeconfig))
    _install_fake_kubernetes(monkeypatch, contexts=[{"name": "prod"}, {"name": "staging"}], current_context={"name": "prod"})
    report = run_doctor(context="staging")
    assert report.context == "staging"
    assert "active context is 'staging'" in report.render(use_color=False)


def test_apply_script_requires_explicit_context_and_quotes_it(tmp_path):
    import os
    import subprocess

    from kube_saver.exporters.pr_generator import generate_pr_plan
    script = tmp_path / "apply.sh"
    script.write_text(generate_pr_plan(recommend([pod()])).files["apply-patches.sh"])
    env = dict(os.environ)
    env.pop("KUBE_SAVER_APPLY_CONTEXT", None)
    assert subprocess.run(["bash", str(script)], env=env, capture_output=True).returncode != 0
    kubectl = tmp_path / "kubectl"
    kubectl.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$@" >> "$TEST_ARGS"\n')
    kubectl.chmod(0o755)
    env.update(PATH=str(tmp_path) + os.pathsep + env["PATH"], TEST_ARGS=str(tmp_path / "args"), KUBE_SAVER_APPLY_CONTEXT="reviewed; $(touch unwanted)")
    assert subprocess.run(["bash", str(script)], cwd=tmp_path, env=env, capture_output=True).returncode == 0
    args = (tmp_path / "args").read_text().splitlines()
    assert args[:2] == ["--context", "reviewed; $(touch unwanted)"]
    assert not (tmp_path / "unwanted").exists()
    kubectl.write_text('#!/usr/bin/env bash\necho called >> "$TEST_ARGS"\nexit 9\n')
    (tmp_path / "args").write_text("")
    assert subprocess.run(["bash", str(script)], env=env, capture_output=True).returncode == 9
    assert (tmp_path / "args").read_text().splitlines() == ["called"]
