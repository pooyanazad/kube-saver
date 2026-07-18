"""Unit tests for Step 41: data models, waste/pricing, and recommendation engine."""

from __future__ import annotations

import os
from pathlib import Path

from kube_saver.config import (
    AlertConfig,
    ExportConfig,
    KubeSaverConfig,
    PricingOverrides,
    SafetyConfig,
    TUIConfig,
    _apply_env_overrides,
    _build_config,
    _safe_get,
    default_config_yaml,
    load_config,
)
from kube_saver.models.core import (
    ActualUsage,
    CloudProvider,
    ClusterInfo,
    CostInfo,
    Currency,
    MetricSource,
    Money,
    NamespaceInfo,
    PodResourceInfo,
    Recommendation,
    ResourceQuantities,
    ResourceWaste,
    WasteReport,
)
from kube_saver.pricing.display import convert_cost, format_yearly
from kube_saver.pricing.engine import PricingEngine, PricingRate
from kube_saver.recommenders.engine import generate_recommendations
from kube_saver.analyzers.resource_waste import PodWaste, ResourceWasteReport


# ── Models ──────────────────────────────────────────────────────────────────


class TestCurrencyEnum:
    def test_symbol_and_code(self) -> None:
        assert Currency.USD.symbol == "$"
        assert Currency.USD.code == "USD"
        assert Currency.EUR.symbol == "€"
        assert Currency.GBP.symbol == "£"
        assert Currency.JPY.symbol == "¥"
        assert Currency.INR.symbol == "₹"
        assert Currency.AED.symbol == "د.إ"


class TestMoney:
    def test_formatted(self) -> None:
        m = Money(amount=123.456, currency=Currency.USD)
        assert m.formatted == "$123.46"

    def test_yearly_formatted(self) -> None:
        m = Money(amount=10.0, currency=Currency.EUR)
        assert m.yearly_formatted == "€120.00"

    def test_repr(self) -> None:
        m = Money(amount=5.0, currency=Currency.GBP)
        assert repr(m) == "£5.00"


class TestCostInfo:
    def test_from_hourly(self) -> None:
        c = CostInfo.from_hourly(0.01)
        assert c.hourly_usd == 0.01
        assert c.daily_usd == 0.24
        assert c.monthly_usd == 0.01 * 730
        assert c.yearly_usd == 0.01 * 730 * 12

    def test_addition(self) -> None:
        a = CostInfo(hourly_usd=1, daily_usd=2, monthly_usd=3, yearly_usd=4)
        b = CostInfo(hourly_usd=10, daily_usd=20, monthly_usd=30, yearly_usd=40)
        c = a + b
        assert c.hourly_usd == 11
        assert c.monthly_usd == 33

    def test_addition_rejects_non_cost_info(self) -> None:
        a = CostInfo()
        result = a.__add__("not a CostInfo")
        assert result is NotImplemented


class TestResourceQuantities:
    def test_has_requests_true(self) -> None:
        rq = ResourceQuantities(cpu_millicores_request=100, memory_bytes_request=200)
        assert rq.has_requests is True

    def test_has_limits_true(self) -> None:
        rq = ResourceQuantities(cpu_millicores_limit=100, memory_bytes_limit=200)
        assert rq.has_limits is True

    def test_has_requests_false(self) -> None:
        rq = ResourceQuantities()
        assert rq.has_requests is False
        assert rq.has_limits is False


class TestClusterInfo:
    def test_defaults(self) -> None:
        c = ClusterInfo(name="c", context="ctx")
        assert c.provider == CloudProvider.UNKNOWN
        assert c.version == "unknown"
        assert c.node_count == 0


class TestNamespaceInfo:
    def test_production_label(self) -> None:
        ns = NamespaceInfo(name="app", labels={"env": "production"})
        assert ns.is_production is True

    def test_production_name(self) -> None:
        ns = NamespaceInfo(name="production")
        assert ns.is_production is True

    def test_non_production(self) -> None:
        ns = NamespaceInfo(name="dev", labels={"env": "dev"})
        assert ns.is_production is False


class TestPodResourceInfo:
    def test_oom_detection(self) -> None:
        pod = PodResourceInfo(name="p", restart_count=0)
        assert pod.had_oom_events is False
        pod.restart_count = 1
        assert pod.had_oom_events is True


class TestRecommendation:
    def test_defaults(self) -> None:
        rec = Recommendation(target_name="x")
        assert rec.target_kind == "Deployment"
        assert rec.confidence == "medium"


class TestWasteReport:
    def test_created_at(self) -> None:
        wr = WasteReport(cluster=ClusterInfo(name="demo", context="ctx"))
        assert isinstance(wr.generated_at, __import__("datetime").datetime)


# ── Pricing ─────────────────────────────────────────────────────────────────


class TestPricingRate:
    def test_cpu_per_millicore(self) -> None:
        r = PricingRate(cpu_per_core_hour_usd=0.04, memory_per_gb_hour_usd=0.005)
        assert r.cpu_per_millicore_hour_usd == 0.04 / 1000

    def test_memory_per_byte(self) -> None:
        r = PricingRate(memory_per_gb_hour_usd=0.005)
        assert r.memory_per_byte_hour_usd == 0.005 / (1024**3)
        assert r.memory_per_byte_month_usd > 0


class TestPricingEngine:
    def test_unknown_tier_fallback(self) -> None:
        e = PricingEngine(provider=CloudProvider.AWS, tier="nonexistent")
        assert e.rate.cpu_per_core_hour_usd == 0.042

    def test_custom_rate(self) -> None:
        e = PricingEngine(provider=CloudProvider.AWS)
        e.set_rate(cpu_per_core_hour=0.01, memory_per_gb_hour=0.001)
        assert e.rate.cpu_per_core_hour_usd == 0.01

    def test_cost_from_resources(self) -> None:
        e = PricingEngine(provider=CloudProvider.AWS)
        c = e.cost_from_resources(1000, 0)
        assert c.monthly_usd > 0

    def test_monthly_cost_summary_keys(self) -> None:
        e = PricingEngine(provider=CloudProvider.AWS)
        w = ResourceWaste(cpu_millicores=500, memory_bytes=512 * 1024**2)
        r = ResourceWaste(cpu_millicores=1000, memory_bytes=1024**3)
        s = e.monthly_cost_summary(w, r)
        assert "total_requested_usd_month" in s
        assert "total_waste_usd_month" in s
        assert "waste_ratio" in s
        assert 0 <= s["waste_ratio"] <= 1


class TestPricingDisplay:
    def test_convert_cost(self) -> None:
        c = CostInfo(monthly_usd=100.0)
        m = convert_cost(c, Currency.EUR, rate_from_usd=0.92)
        assert m.amount == 92.0
        assert m.currency == Currency.EUR

    def test_format_yearly(self) -> None:
        c = CostInfo(yearly_usd=1200.0)
        m = format_yearly(c, Currency.GBP, rate_from_usd=0.8)
        assert m.amount == 960.0
        assert m.currency == Currency.GBP


# ── Config ──────────────────────────────────────────────────────────────────


class TestSafeGet:
    def test_single_level(self) -> None:
        assert _safe_get({"a": 1}, "a") == 1

    def test_nested(self) -> None:
        assert _safe_get({"a": {"b": 2}}, "a", "b") == 2

    def test_missing(self) -> None:
        assert _safe_get({"a": 1}, "b") is None

    def test_missing_with_default(self) -> None:
        assert _safe_get({"a": 1}, "b", default="x") == "x"

    def test_non_dict(self) -> None:
        assert _safe_get("not-a-dict", "a") is None


class TestBuildConfig:
    def test_defaults(self) -> None:
        cfg = _build_config({})
        assert cfg.cloud_provider == CloudProvider.UNKNOWN
        assert cfg.currency == Currency.USD
        assert cfg.exchange_rate_from_usd == 1.0
        assert cfg.safety.min_cpu_millicores == 100

    def test_provider(self) -> None:
        cfg = _build_config({"cloud_provider": "aws"})
        assert cfg.cloud_provider == CloudProvider.AWS

    def test_invalid_provider_falls_back(self) -> None:
        cfg = _build_config({"cloud_provider": "invalid"})
        assert cfg.cloud_provider == CloudProvider.UNKNOWN

    def test_currency(self) -> None:
        cfg = _build_config({"currency": "eur"})
        assert cfg.currency == Currency.EUR

    def test_invalid_currency_falls_back(self) -> None:
        cfg = _build_config({"currency": "xyz"})
        assert cfg.currency == Currency.USD

    def test_alerts_nested(self) -> None:
        cfg = _build_config({"alerts": {"critical_monthly_usd": 999.0}})
        assert cfg.alerts.critical_monthly_usd == 999.0

    def test_pricing_nested(self) -> None:
        cfg = _build_config({"pricing": {"cpu_per_core_hour_usd": 0.01}})
        assert cfg.pricing.cpu_per_core_hour_usd == 0.01

    def test_tui_nested(self) -> None:
        cfg = _build_config({"tui": {"refresh_interval_seconds": 60}})
        assert cfg.tui.refresh_interval_seconds == 60

    def test_export_nested(self) -> None:
        cfg = _build_config({"export": {"output_directory": "/tmp/out"}})
        assert cfg.export.output_directory == "/tmp/out"

    def test_exclude_namespaces(self) -> None:
        cfg = _build_config({"exclude_namespaces": ["a", "b"]})
        assert cfg.exclude_namespaces == {"a", "b"}


class TestApplyEnvOverrides:
    def test_provider_override(self) -> None:
        os.environ["KUBE_SAVER_PROVIDER"] = "gcp"
        try:
            cfg = KubeSaverConfig()
            cfg = _apply_env_overrides(cfg)
            assert cfg.cloud_provider == CloudProvider.GCP
        finally:
            del os.environ["KUBE_SAVER_PROVIDER"]

    def test_invalid_provider_no_crash(self) -> None:
        os.environ["KUBE_SAVER_PROVIDER"] = "invalid"
        try:
            cfg = KubeSaverConfig()
            cfg = _apply_env_overrides(cfg)
            assert cfg.cloud_provider == CloudProvider.UNKNOWN
        finally:
            del os.environ["KUBE_SAVER_PROVIDER"]

    def test_currency_override(self) -> None:
        os.environ["KUBE_SAVER_CURRENCY"] = "jpy"
        try:
            cfg = KubeSaverConfig()
            cfg = _apply_env_overrides(cfg)
            assert cfg.currency == Currency.JPY
        finally:
            del os.environ["KUBE_SAVER_CURRENCY"]

    def test_invalid_currency_no_crash(self) -> None:
        os.environ["KUBE_SAVER_CURRENCY"] = "zzz"
        try:
            cfg = KubeSaverConfig()
            cfg = _apply_env_overrides(cfg)
            assert cfg.currency == Currency.USD
        finally:
            del os.environ["KUBE_SAVER_CURRENCY"]

    def test_exchange_rate_override(self) -> None:
        os.environ["KUBE_SAVER_EXCHANGE_RATE_FROM_USD"] = "0.85"
        try:
            cfg = KubeSaverConfig()
            cfg = _apply_env_overrides(cfg)
            assert cfg.exchange_rate_from_usd == 0.85
        finally:
            del os.environ["KUBE_SAVER_EXCHANGE_RATE_FROM_USD"]

    def test_aggressive_mode_override(self) -> None:
        os.environ["KUBE_SAVER_AGGRESSIVE_MODE"] = "true"
        try:
            cfg = KubeSaverConfig()
            cfg = _apply_env_overrides(cfg)
            assert cfg.safety.aggressive_mode is True
        finally:
            del os.environ["KUBE_SAVER_AGGRESSIVE_MODE"]

    def test_pricing_overrides(self) -> None:
        os.environ["KUBE_SAVER_CPU_PER_CORE"] = "0.02"
        os.environ["KUBE_SAVER_MEM_PER_GB"] = "0.003"
        try:
            cfg = KubeSaverConfig()
            cfg = _apply_env_overrides(cfg)
            assert cfg.pricing.cpu_per_core_hour_usd == 0.02
            assert cfg.pricing.memory_per_gb_hour_usd == 0.003
        finally:
            del os.environ["KUBE_SAVER_CPU_PER_CORE"]
            del os.environ["KUBE_SAVER_MEM_PER_GB"]

    def test_refresh_secs_override(self) -> None:
        os.environ["KUBE_SAVER_REFRESH_SECS"] = "120"
        try:
            cfg = KubeSaverConfig()
            cfg = _apply_env_overrides(cfg)
            assert cfg.tui.refresh_interval_seconds == 120
        finally:
            del os.environ["KUBE_SAVER_REFRESH_SECS"]


class TestLoadConfig:
    def test_no_files_returns_defaults(self, tmp_path: Path) -> None:
        cfg = load_config(global_path=tmp_path / "nonexistent.yaml", local_path=tmp_path / "nonexistent.yaml")
        assert cfg.cloud_provider == CloudProvider.UNKNOWN
        assert cfg.currency == Currency.USD

    def test_local_overrides_global(self, tmp_path: Path) -> None:
        g = tmp_path / "g.yaml"
        l = tmp_path / "l.yaml"
        g.write_text("cloud_provider: aws\ncurrency: eur\n")
        l.write_text("cloud_provider: gcp\n")
        cfg = load_config(global_path=g, local_path=l)
        assert cfg.cloud_provider == CloudProvider.GCP
        assert cfg.currency == Currency.EUR

    def test_env_overrides_files(self, tmp_path: Path) -> None:
        l = tmp_path / "l.yaml"
        l.write_text("cloud_provider: aws\n")
        os.environ["KUBE_SAVER_PROVIDER"] = "azure"
        try:
            cfg = load_config(global_path=tmp_path / "x.yaml", local_path=l)
            assert cfg.cloud_provider == CloudProvider.AZURE
        finally:
            del os.environ["KUBE_SAVER_PROVIDER"]


class TestDefaultConfigYaml:
    def test_produces_string(self) -> None:
        result = default_config_yaml()
        assert isinstance(result, str)
        assert "cloud_provider" in result


class TestKubeSaverConfigHelpers:
    def test_pricing_has_custom_rates_zero(self) -> None:
        cfg = KubeSaverConfig()
        assert cfg.pricing_has_custom_rates() is False

    def test_pricing_has_custom_rates_cpu(self) -> None:
        cfg = KubeSaverConfig(pricing=PricingOverrides(cpu_per_core_hour_usd=0.01))
        assert cfg.pricing_has_custom_rates() is True

    def test_pricing_has_custom_rates_mem(self) -> None:
        cfg = KubeSaverConfig(pricing=PricingOverrides(memory_per_gb_hour_usd=0.001))
        assert cfg.pricing_has_custom_rates() is True


class TestConfigDataclassDefaults:
    def test_safety_defaults(self) -> None:
        s = SafetyConfig()
        assert s.min_cpu_millicores == 100.0
        assert s.aggressive_mode is False

    def test_alert_defaults(self) -> None:
        a = AlertConfig()
        assert a.warning_waste_ratio == 0.4
        assert a.critical_monthly_usd == 500.0

    def test_tui_defaults(self) -> None:
        t = TUIConfig()
        assert t.refresh_interval_seconds == 30
        assert t.compact_mode is False

    def test_export_defaults(self) -> None:
        e = ExportConfig()
        assert e.dry_run is True
        assert e.output_directory == "./kube-saver-exports"

    def test_pricing_overrides_as_rate(self) -> None:
        p = PricingOverrides(cpu_per_core_hour_usd=0.05, memory_per_gb_hour_usd=0.004)
        rate = p.as_rate()
        assert rate.cpu_per_core_hour_usd == 0.05
        assert rate.memory_per_gb_hour_usd == 0.004


# ── Recommendation engine ──────────────────────────────────────────────────


def _make_pod_waste(
    name: str = "api",
    ns: str = "default",
    cpu_req: float = 1000,
    cpu_act: float = 100,
    mem_req: int = 1024 * 1024**2,
    mem_act: int = 50 * 1024**2,
    kind: str = "Deployment",
) -> PodWaste:
    pod = PodResourceInfo(
        name=f"{name}-pod",
        namespace=ns,
        workload_kind=kind,
        workload_name=name,
        resources=ResourceQuantities(
            cpu_millicores_request=cpu_req,
            memory_bytes_request=mem_req,
        ),
        actual=ActualUsage(
            cpu_millicores=cpu_act,
            memory_bytes=mem_act,
            source=MetricSource.METRICS_SERVER,
        ),
    )
    cpu_waste = max(cpu_req - cpu_act, 0)
    mem_waste = max(mem_req - mem_act, 0)
    cpu_ratio = cpu_waste / cpu_req if cpu_req else 0
    mem_ratio = mem_waste / mem_req if mem_req else 0
    return PodWaste(
        pod=pod,
        cpu_waste_millicores=cpu_waste,
        memory_waste_bytes=mem_waste,
        cpu_waste_ratio=min(cpu_ratio, 1.0),
        memory_waste_ratio=min(mem_ratio, 1.0),
        has_usage_data=cpu_act > 0 or mem_act > 0,
    )


def _make_report(pod_wastes: list[PodWaste]) -> ResourceWasteReport:
    report = ResourceWasteReport()
    for pw in pod_wastes:
        report.namespaces.append(
            __import__("kube_saver.analyzers.resource_waste", fromlist=["NamespaceAnalysis"]).NamespaceAnalysis(
                namespace=NamespaceInfo(name=pw.pod.namespace),
                pod_waste=[pw],
                cpu_waste_millicores=pw.cpu_waste_millicores,
                memory_waste_bytes=pw.memory_waste_bytes,
            )
        )
        report.total_cpu_waste_millicores += pw.cpu_waste_millicores
        report.total_memory_waste_bytes += pw.memory_waste_bytes
        report.total_pods += 1
    return report


class TestRecommendationEngine:
    def test_generates_cpu_recommendation_for_high_waste(self) -> None:
        pw = _make_pod_waste(cpu_req=1000, cpu_act=100, mem_req=1024 * 1024**2, mem_act=512 * 1024**2)
        report = _make_report([pw])
        pricing = PricingEngine(provider=CloudProvider.AWS)
        recs = generate_recommendations(report, pricing)
        cpu_recs = [r for r in recs if r.resource_type == "cpu-request"]
        assert len(cpu_recs) == 1
        assert cpu_recs[0].suggested_value == "150m"

    def test_generates_memory_recommendation_for_high_waste(self) -> None:
        pw = _make_pod_waste(cpu_req=500, cpu_act=400, mem_req=1024 * 1024**2, mem_act=50 * 1024**2)
        report = _make_report([pw])
        pricing = PricingEngine(provider=CloudProvider.AWS)
        recs = generate_recommendations(report, pricing)
        mem_recs = [r for r in recs if r.resource_type == "memory-request"]
        assert len(mem_recs) == 1

    def test_no_recommendations_for_low_waste(self) -> None:
        pw = _make_pod_waste(cpu_req=500, cpu_act=450, mem_req=256 * 1024**2, mem_act=240 * 1024**2)
        report = _make_report([pw])
        pricing = PricingEngine(provider=CloudProvider.AWS)
        recs = generate_recommendations(report, pricing)
        assert len(recs) == 0

    def test_empty_report(self) -> None:
        report = ResourceWasteReport()
        pricing = PricingEngine(provider=CloudProvider.AWS)
        recs = generate_recommendations(report, pricing)
        assert recs == []

    def test_sorted_by_savings_desc(self) -> None:
        pw1 = _make_pod_waste("big", cpu_req=2000, cpu_act=100, mem_req=2 * 1024**3, mem_act=50 * 1024**2)
        pw2 = _make_pod_waste("small", ns="other", cpu_req=800, cpu_act=400, mem_req=512 * 1024**2, mem_act=200 * 1024**2)
        report = _make_report([pw1, pw2])
        pricing = PricingEngine(provider=CloudProvider.AWS)
        recs = generate_recommendations(report, pricing)
        if len(recs) >= 2:
            assert recs[0].estimated_savings.monthly_usd >= recs[1].estimated_savings.monthly_usd

    def test_suggested_cpu_never_below_50(self) -> None:
        pw = _make_pod_waste(cpu_req=200, cpu_act=5, mem_req=256 * 1024**2, mem_act=100 * 1024**2)
        report = _make_report([pw])
        pricing = PricingEngine(provider=CloudProvider.AWS)
        recs = generate_recommendations(report, pricing)
        cpu_recs = [r for r in recs if r.resource_type == "cpu-request"]
        assert cpu_recs
        suggested_millicores = int(cpu_recs[0].suggested_value.replace("m", ""))
        assert suggested_millicores >= 50

    def test_confidence_high_for_extreme_waste(self) -> None:
        pw = _make_pod_waste(cpu_req=1000, cpu_act=10, mem_req=1024 * 1024**2, mem_act=10 * 1024**2)
        report = _make_report([pw])
        pricing = PricingEngine(provider=CloudProvider.AWS)
        recs = generate_recommendations(report, pricing)
        assert any(r.confidence == "high" for r in recs)

    def test_multiple_workloads(self) -> None:
        pws = [
            _make_pod_waste("svc-a", ns="ns1", cpu_req=1000, cpu_act=50, mem_req=1024 * 1024**2, mem_act=50 * 1024**2),
            _make_pod_waste("svc-b", ns="ns2", cpu_req=2000, cpu_act=200, mem_req=2 * 1024**3, mem_act=100 * 1024**2),
        ]
        report = _make_report(pws)
        pricing = PricingEngine(provider=CloudProvider.AWS)
        recs = generate_recommendations(report, pricing)
        namespaces_hit = {r.target_namespace for r in recs}
        assert len(namespaces_hit) == 2
