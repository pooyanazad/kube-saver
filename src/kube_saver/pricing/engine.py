"""Pricing engine for kube-saver.

Converts Kubernetes resource waste (CPU millicores, memory bytes) into
real USD costs using cloud-provider pricing data.

Pricing covers AWS, GCP, and Azure defaults. Custom overrides can be
provided via the configuration system (Step 8).

Reference: AWS EKS pricing model (effective July 2026)
  - t3.medium  : 2 vCPU  = $0.0416/hr   => $0.0208/vCPU/hr
  - m5.large   : 2 vCPU  = $0.0960/hr   => $0.0480/vCPU/hr
  - c5.xlarge  : 4 vCPU  = $0.1700/hr   => $0.0425/vCPU/hr
  - Average on-demand: ~$0.035/vCPU/hr, ~$0.005/GB/hr (memory)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from kube_saver.models.core import CloudProvider, CostInfo, ResourceWaste

HOURS_PER_MONTH = 730  # AWS billing standard


@dataclass
class PricingRate:
    """Hourly rate for a resource dimension.

    Attributes:
        cpu_per_core_hour_usd: Cost per CPU core per hour, USD.
        memory_per_gb_hour_usd: Cost per GB memory per hour, USD.
        label: Human-readable label for this pricing tier.
    """

    cpu_per_core_hour_usd: float = 0.0
    memory_per_gb_hour_usd: float = 0.0
    label: str = "custom"

    @property
    def cpu_per_millicore_hour_usd(self) -> float:
        """Cost per millicore-hour, USD."""
        return self.cpu_per_core_hour_usd / 1000

    @property
    def cpu_per_millicore_month_usd(self) -> float:
        """Cost per millicore-month, USD."""
        return self.cpu_per_millicore_hour_usd * HOURS_PER_MONTH

    @property
    def memory_per_byte_hour_usd(self) -> float:
        """Cost per byte-hour, USD."""
        return self.memory_per_gb_hour_usd / (1024**3)

    @property
    def memory_per_byte_month_usd(self) -> float:
        """Cost per byte-month, USD."""
        return self.memory_per_byte_hour_usd * HOURS_PER_MONTH


# ── Default pricing tiers ──────────────────────────────────────────────────

_AWS_RATES = {
    "general": PricingRate(
        cpu_per_core_hour_usd=0.042,
        memory_per_gb_hour_usd=0.005,
        label="AWS general-purpose (m5/c5 avg)",
    ),
    "t3": PricingRate(
        cpu_per_core_hour_usd=0.021,
        memory_per_gb_hour_usd=0.003,
        label="AWS t3 burstable",
    ),
    "r5": PricingRate(
        cpu_per_core_hour_usd=0.038,
        memory_per_gb_hour_usd=0.007,
        label="AWS r5 memory-optimized",
    ),
}

_GCP_RATES = {
    "general": PricingRate(
        cpu_per_core_hour_usd=0.0475,
        memory_per_gb_hour_usd=0.0052,
        label="GCP e2/n2 standard",
    ),
    "e2_small": PricingRate(
        cpu_per_core_hour_usd=0.0168,
        memory_per_gb_hour_usd=0.0023,
        label="GCP e2-small burstable",
    ),
}

_AZURE_RATES = {
    "general": PricingRate(
        cpu_per_core_hour_usd=0.040,
        memory_per_gb_hour_usd=0.0048,
        label="Azure D-series general",
    ),
}

_ON_PREM_RATES = {
    "general": PricingRate(
        cpu_per_core_hour_usd=0.020,
        memory_per_gb_hour_usd=0.003,
        label="On-prem estimate (depreciated)",
    ),
}

_PROVIDER_RATES: dict[CloudProvider, dict[str, PricingRate]] = {
    CloudProvider.AWS: _AWS_RATES,
    CloudProvider.GCP: _GCP_RATES,
    CloudProvider.AZURE: _AZURE_RATES,
    CloudProvider.ON_PREM: _ON_PREM_RATES,
}

# Default fallback used for UNKNOWN provider
_DEFAULT_RATE = PricingRate(
    cpu_per_core_hour_usd=0.040,
    memory_per_gb_hour_usd=0.005,
    label="unknown provider estimate",
)


@dataclass
class PricingEngine:
    """Converts resource waste to USD costs.

    Attributes:
        provider: Cloud provider.
        tier: Pricing tier within the provider ('general', 't3', etc.).
        rate: Effective ``PricingRate`` after resolution.
        custom_overrides: Caller-supplied overrides (from config).
    """

    provider: CloudProvider = CloudProvider.UNKNOWN
    tier: str = "general"
    rate: PricingRate = field(default_factory=lambda: _DEFAULT_RATE)
    custom_overrides: dict[str, PricingRate] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Resolve the pricing rate from provider + tier."""
        self._resolve_rate()

    def _resolve_rate(self) -> None:
        """Pick the right pricing rate from provider and tier."""
        if self.custom_overrides and self.tier in self.custom_overrides:
            self.rate = self.custom_overrides[self.tier]
            return
        provider_tiers = _PROVIDER_RATES.get(self.provider, {})
        self.rate = provider_tiers.get(self.tier, provider_tiers.get("general", _DEFAULT_RATE))

    def set_rate(
        self,
        cpu_per_core_hour: float | None = None,
        memory_per_gb_hour: float | None = None,
        label: str | None = None,
    ) -> None:
        """Override individual pricing parameters at runtime."""
        cpu = cpu_per_core_hour if cpu_per_core_hour is not None else self.rate.cpu_per_core_hour_usd
        mem = memory_per_gb_hour if memory_per_gb_hour is not None else self.rate.memory_per_gb_hour_usd
        lbl = label or self.rate.label
        self.rate = PricingRate(cpu_per_core_hour_usd=cpu, memory_per_gb_hour_usd=mem, label=lbl)

    def cost_from_waste(self, waste: ResourceWaste) -> CostInfo:
        """Convert a ``ResourceWaste`` into a ``CostInfo`` with all time scales."""
        cpu_cost_month = waste.cpu_millicores * self.rate.cpu_per_millicore_month_usd
        mem_cost_month = waste.memory_bytes * self.rate.memory_per_byte_month_usd
        monthly = cpu_cost_month + mem_cost_month
        return CostInfo.from_hourly(monthly / HOURS_PER_MONTH)

    def cost_from_resources(self, cpu_millicores: float, memory_bytes: int) -> CostInfo:
        """Calculate the cost of a given CPU/memory allocation."""
        waste = ResourceWaste(cpu_millicores=cpu_millicores, memory_bytes=memory_bytes)
        return self.cost_from_waste(waste)

    def monthly_cost_summary(
        self,
        total_waste: ResourceWaste,
        total_requested: ResourceWaste,
    ) -> dict[str, float]:
        """Return a summary dict of waste cost ratios.

        Keys:
            total_requested_usd_month: cost of all requested resources
            total_waste_usd_month:     cost of the wasted portion
            waste_ratio:               waste / requested (0.0 – 1.0)
        """
        req_info = self.cost_from_waste(total_requested)
        waste_info = self.cost_from_waste(total_waste)
        ratio = (
            req_info.monthly_usd
            and waste_info.monthly_usd / req_info.monthly_usd
        ) or 0.0
        return {
            "total_requested_usd_month": req_info.monthly_usd,
            "total_waste_usd_month": waste_info.monthly_usd,
            "waste_ratio": min(ratio, 1.0),
        }


__all__ = [
    "PricingEngine",
    "PricingRate",
    "HOURS_PER_MONTH",
]
