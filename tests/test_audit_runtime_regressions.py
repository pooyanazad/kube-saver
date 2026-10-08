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
