"""Tests for kube-saver pricing engine."""

from kube_saver.models.core import CloudProvider, CostInfo, ResourceWaste
from kube_saver.pricing.engine import PricingEngine, PricingRate


class TestPricingRate:
    def test_derived_properties(self) -> None:
        rate = PricingRate(cpu_per_core_hour_usd=0.04, memory_per_gb_hour_usd=0.005)
        assert rate.cpu_per_millicore_hour_usd == 0.04 / 1000
        assert rate.cpu_per_millicore_month_usd == (0.04 / 1000) * 730

    def test_memory_per_byte_hour(self) -> None:
        rate = PricingRate(memory_per_gb_hour_usd=0.005)
        assert rate.memory_per_byte_hour_usd == 0.005 / (1024**3)
        assert rate.memory_per_byte_month_usd > 0


class TestPricingEngine:
    def test_aws_general_tier(self) -> None:
        engine = PricingEngine(provider=CloudProvider.AWS, tier="general")
        assert engine.rate.cpu_per_core_hour_usd == 0.042
        assert "general" in engine.rate.label.lower()

    def test_gcp_general_tier(self) -> None:
        engine = PricingEngine(provider=CloudProvider.GCP, tier="general")
        assert engine.rate.cpu_per_core_hour_usd == 0.0475

    def test_unknown_provider_uses_default(self) -> None:
        engine = PricingEngine(provider=CloudProvider.UNKNOWN)
        assert engine.rate.cpu_per_core_hour_usd == 0.040

    def test_unknown_tier_falls_back_to_general(self) -> None:
        engine = PricingEngine(provider=CloudProvider.AWS, tier="nonexistent")
        assert engine.rate.cpu_per_core_hour_usd == 0.042  # general

    def test_custom_rate_override(self) -> None:
        engine = PricingEngine(provider=CloudProvider.AWS)
        engine.set_rate(cpu_per_core_hour=0.01, memory_per_gb_hour=0.001)
        assert engine.rate.cpu_per_core_hour_usd == 0.01
        assert engine.rate.memory_per_gb_hour_usd == 0.001

    def test_cost_from_waste(self) -> None:
        engine = PricingEngine(provider=CloudProvider.AWS, tier="general")
        # 1000 millicores = 1 core = $0.042/hr = $30.66/mo
        waste = ResourceWaste(cpu_millicores=1000, memory_bytes=0)
        cost = engine.cost_from_waste(waste)
        assert cost.hourly_usd > 0
        assert cost.monthly_usd > 0
        assert cost.yearly_usd > 0
        assert cost.monthly_usd > cost.daily_usd

    def test_cost_from_waste_addition(self) -> None:
        engine = PricingEngine(provider=CloudProvider.AWS)
        waste = ResourceWaste(cpu_millicores=1000, memory_bytes=1024**3)
        cost = engine.cost_from_waste(waste)
        # CPU + memory both contribute
        cpu_cost = engine.cost_from_waste(ResourceWaste(cpu_millicores=1000, memory_bytes=0))
        mem_cost = engine.cost_from_waste(ResourceWaste(cpu_millicores=0, memory_bytes=1024**3))
        assert abs(cost.monthly_usd - (cpu_cost.monthly_usd + mem_cost.monthly_usd)) < 0.01

    def test_monthly_cost_summary(self) -> None:
        engine = PricingEngine(provider=CloudProvider.AWS)
        waste = ResourceWaste(cpu_millicores=5000, memory_bytes=10 * 1024**3)
        requested = ResourceWaste(cpu_millicores=10000, memory_bytes=20 * 1024**3)
        summary = engine.monthly_cost_summary(waste, requested)
        assert "total_requested_usd_month" in summary
        assert "total_waste_usd_month" in summary
        assert "waste_ratio" in summary
        assert 0 <= summary["waste_ratio"] <= 1.0