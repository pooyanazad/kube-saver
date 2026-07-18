"""Configuration system for kube-saver.

Loads configuration from YAML files with a clear priority cascade:

  1. ~/.kube-saver/config.yaml  (user global)
  2. ./.kube-saver.yaml         (project local, overrides global)
  3. Environment variables       (override everything)
  4. CLI arguments               (highest priority, via Click)

If no config file exists a sensible default is returned, so the tool
works out of the box without any configuration.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

try:
    import yaml  # type: ignore[import-untyped]

    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

from kube_saver.models.core import CloudProvider
from kube_saver.pricing.engine import PricingRate

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path.home() / ".kube-saver" / "config.yaml"
LOCAL_CONFIG_PATH = Path(".kube-saver.yaml")
ENV_PREFIX = "KUBE_SAVER_"


@dataclass
class SafetyConfig:
    """Guardrails that prevent dangerous recommendations in production.

    Attributes:
        min_cpu_millicores: Never recommend below this many millicores.
        min_memory_bytes: Never recommend below this many bytes.
        prod_cpu_floor_ratio: Floor as ratio of current request in prod.
        prod_memory_floor_ratio: Floor as ratio of current request in prod.
        aggressive_mode: If True, ignore floors (for dev/staging use).
    """

    min_cpu_millicores: float = 100.0
    min_memory_bytes: int = 128 * 1024 * 1024  # 128 MiB
    prod_cpu_floor_ratio: float = 0.5
    prod_memory_floor_ratio: float = 0.5
    aggressive_mode: bool = False


@dataclass
class AlertConfig:
    """Thresholds that trigger visual alerts in the TUI.

    Attributes:
        warning_waste_ratio: Warn when waste > this fraction of request.
        critical_waste_ratio: Critical alert when waste > this fraction.
        warning_monthly_usd: Warn when monthly waste exceeds this dollar amount.
        critical_monthly_usd: Critical alert when monthly waste exceeds this.
    """

    warning_waste_ratio: float = 0.4
    critical_waste_ratio: float = 0.8
    warning_monthly_usd: float = 100.0
    critical_monthly_usd: float = 500.0


@dataclass
class PricingOverrides:
    """Custom pricing rates that override the built-in provider defaults.

    Keys are tier names (e.g., "general", "t3"). Values are dicts with
    ``cpu_per_core_hour_usd`` and ``memory_per_gb_hour_usd`` keys.
    """

    cpu_per_core_hour_usd: float = 0.0
    memory_per_gb_hour_usd: float = 0.0
    label: str = "custom (from config)"

    def as_rate(self) -> PricingRate:
        """Convert to a ``PricingRate`` for the pricing engine."""
        return PricingRate(
            cpu_per_core_hour_usd=self.cpu_per_core_hour_usd,
            memory_per_gb_hour_usd=self.memory_per_gb_hour_usd,
            label=self.label,
        )


@dataclass
class TUIConfig:
    """TUI display preferences.

    Attributes:
        refresh_interval_seconds: Auto-refresh period for the TUI.
        show_system_namespaces: Show kube-system and similar namespaces.
        compact_mode: Use condensed display with fewer details.
        color_theme: 'default', 'dark', or 'light'.
    """

    refresh_interval_seconds: int = 30
    show_system_namespaces: bool = False
    compact_mode: bool = False
    color_theme: str = "default"


@dataclass
class ExportConfig:
    """Export-related settings.

    Attributes:
        output_directory: Default directory for exported files.
        dry_run: If True, never actually write export files.
        git_author_name: Author name used when generating Git commits.
        git_author_email: Author email for Git commits.
    """

    output_directory: str = "./kube-saver-exports"
    dry_run: bool = True
    git_author_name: str = "kube-saver"
    git_author_email: str = "kube-saver@localhost"


@dataclass
class KubeSaverConfig:
    """Top-level configuration object for kube-saver.

    All attributes map directly to YAML config keys. Any missing/invalid
    key falls back to the default value for that field.
    """

    cloud_provider: CloudProvider = CloudProvider.UNKNOWN
    provider_tier: str = "general"
    namespace_filter: list[str] = field(default_factory=list)
    exclude_namespaces: set[str] = field(default_factory=lambda: {
        "kube-system", "kube-public", "kube-node-lease",
    })
    kubeconfig_context: Optional[str] = None
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    alerts: AlertConfig = field(default_factory=AlertConfig)
    pricing: PricingOverrides = field(default_factory=PricingOverrides)
    tui: TUIConfig = field(default_factory=TUIConfig)
    export: ExportConfig = field(default_factory=ExportConfig)

    # ── helpers ────────────────────────────────────────────────────────────

    def pricing_has_custom_rates(self) -> bool:
        """Return True if the user supplied non-zero custom pricing."""
        return (
            self.pricing.cpu_per_core_hour_usd > 0
            or self.pricing.memory_per_gb_hour_usd > 0
        )


# ── Loader ─────────────────────────────────────────────────────────────────

def _safe_get(d: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Nested dict.get with multiple key levels."""
    for key in keys:
        if isinstance(d, dict):
            d = d.get(key, default)
        else:
            return default
    return d


def _build_config(raw: dict[str, Any]) -> KubeSaverConfig:
    """Convert a flat YAML dict into a ``KubeSaverConfig``."""
    provider_str = raw.get("cloud_provider", "unknown")
    try:
        provider = CloudProvider(provider_str.lower())
    except ValueError:
        provider = CloudProvider.UNKNOWN

    exclude = raw.get("exclude_namespaces", [
        "kube-system", "kube-public", "kube-node-lease",
    ])

    safety = SafetyConfig(
        min_cpu_millicores=raw.get("min_cpu_millicores", 100),
        min_memory_bytes=raw.get("min_memory_bytes", 128 * 1024 * 1024),
        prod_cpu_floor_ratio=raw.get("prod_cpu_floor_ratio", 0.5),
        prod_memory_floor_ratio=raw.get("prod_memory_floor_ratio", 0.5),
        aggressive_mode=raw.get("aggressive_mode", False),
    )

    alert_raw = raw.get("alerts", {})
    alerts = AlertConfig(
        warning_waste_ratio=alert_raw.get("warning_waste_ratio", 0.4),
        critical_waste_ratio=alert_raw.get("critical_waste_ratio", 0.8),
        warning_monthly_usd=alert_raw.get("warning_monthly_usd", 100.0),
        critical_monthly_usd=alert_raw.get("critical_monthly_usd", 500.0),
    )

    pricing_raw = raw.get("pricing", {})
    pricing = PricingOverrides(
        cpu_per_core_hour_usd=pricing_raw.get("cpu_per_core_hour_usd", 0.0),
        memory_per_gb_hour_usd=pricing_raw.get("memory_per_gb_hour_usd", 0.0),
        label=pricing_raw.get("label", "custom (from config)"),
    )

    tui_raw = raw.get("tui", {})
    tui = TUIConfig(
        refresh_interval_seconds=tui_raw.get("refresh_interval_seconds", 30),
        show_system_namespaces=tui_raw.get("show_system_namespaces", False),
        compact_mode=tui_raw.get("compact_mode", False),
        color_theme=tui_raw.get("color_theme", "default"),
    )

    export_raw = raw.get("export", {})
    export = ExportConfig(
        output_directory=export_raw.get("output_directory", "./kube-saver-exports"),
        dry_run=export_raw.get("dry_run", True),
        git_author_name=export_raw.get("git_author_name", "kube-saver"),
        git_author_email=export_raw.get("git_author_email", "kube-saver@localhost"),
    )

    return KubeSaverConfig(
        cloud_provider=provider,
        provider_tier=raw.get("provider_tier", "general"),
        namespace_filter=raw.get("namespace_filter", []),
        exclude_namespaces=set(exclude),
        kubeconfig_context=raw.get("kubeconfig_context"),
        safety=safety,
        alerts=alerts,
        pricing=pricing,
        tui=tui,
        export=export,
    )


def _apply_env_overrides(cfg: KubeSaverConfig) -> KubeSaverConfig:
    """Override config values from environment variables.

    Recognised variables (all prefixed ``KUBE_SAVER_``):
        KUBE_SAVER_PROVIDER        - cloud_provider
        KUBE_SAVER_TIER            - provider_tier
        KUBE_SAVER_CONTEXT         - kubeconfig_context
        KUBE_SAVER_AGGRESSIVE_MODE - safety.aggressive_mode (true/1/yes)
        KUBE_SAVER_CPU_PER_CORE    - pricing.cpu_per_core_hour_usd
        KUBE_SAVER_MEM_PER_GB      - pricing.memory_per_gb_hour_usd
        KUBE_SAVER_REFRESH_SECS    - tui.refresh_interval_seconds
    """
    env = os.environ

    def _env(key: str) -> Optional[str]:
        return env.get(f"{ENV_PREFIX}{key}")

    if (v := _env("PROVIDER")) is not None:
        try:
            cfg.cloud_provider = CloudProvider(v.lower())
        except ValueError:
            pass
    if (v := _env("TIER")) is not None:
        cfg.provider_tier = v
    if (v := _env("CONTEXT")) is not None:
        cfg.kubeconfig_context = v
    if (v := _env("AGGRESSIVE_MODE")) is not None:
        cfg.safety.aggressive_mode = v.lower() in ("true", "1", "yes")
    if (v := _env("CPU_PER_CORE")) is not None:
        cfg.pricing.cpu_per_core_hour_usd = float(v)
    if (v := _env("MEM_PER_GB")) is not None:
        cfg.pricing.memory_per_gb_hour_usd = float(v)
    if (v := _env("REFRESH_SECS")) is not None:
        cfg.tui.refresh_interval_seconds = int(v)

    return cfg


def load_config(
    global_path: Optional[Path] = None,
    local_path: Optional[Path] = None,
) -> KubeSaverConfig:
    """Load and merge configuration from all sources.

    Priority (highest wins):
        1. Environment variables (``KUBE_SAVER_*``)
        2. Local config file (``.kube-saver.yaml`` in cwd)
        3. Global config file (``~/.kube-saver/config.yaml``)
        4. Built-in defaults

    Args:
        global_path: Override for global config path.
        local_path: Override for local config path.

    Returns:
        Merged ``KubeSaverConfig`` instance.
    """
    gpath = global_path or DEFAULT_CONFIG_PATH
    lpath = local_path or LOCAL_CONFIG_PATH

    raw: dict[str, Any] = {}

    # Layer 1: global
    if gpath.is_file() and _YAML_AVAILABLE:
        try:
            raw.update(yaml.safe_load(gpath.read_text()) or {})
            logger.debug("Loaded global config from %s", gpath)
        except Exception as exc:
            logger.warning("Error reading global config %s: %s", gpath, exc)

    # Layer 2: local (overrides global)
    if lpath.is_file() and _YAML_AVAILABLE:
        try:
            raw.update(yaml.safe_load(lpath.read_text()) or {})
            logger.debug("Loaded local config from %s", lpath)
        except Exception as exc:
            logger.warning("Error reading local config %s: %s", lpath, exc)

    # Layer 3: env overrides
    cfg = _build_config(raw) if raw else KubeSaverConfig()
    cfg = _apply_env_overrides(cfg)

    return cfg


def default_config_yaml() -> str:
    """Return the default configuration as a YAML string.

    Useful for ``kube-saver init`` to scaffold ``.kube-saver.yaml``.
    """
    if not _YAML_AVAILABLE:
        return "# pyyaml not installed — cannot generate YAML"
    default = KubeSaverConfig()
    data: dict[str, Any] = {
        "cloud_provider": default.cloud_provider.value,
        "provider_tier": default.provider_tier,
        "kubeconfig_context": None,
        "namespace_filter": [],
        "exclude_namespaces": sorted(default.exclude_namespaces),
        "min_cpu_millicores": default.safety.min_cpu_millicores,
        "min_memory_bytes": default.safety.min_memory_bytes,
        "prod_cpu_floor_ratio": default.safety.prod_cpu_floor_ratio,
        "aggressive_mode": default.safety.aggressive_mode,
        "alerts": {
            "warning_waste_ratio": default.alerts.warning_waste_ratio,
            "critical_waste_ratio": default.alerts.critical_waste_ratio,
            "warning_monthly_usd": default.alerts.warning_monthly_usd,
            "critical_monthly_usd": default.alerts.critical_monthly_usd,
        },
        "pricing": {
            "cpu_per_core_hour_usd": 0.0,
            "memory_per_gb_hour_usd": 0.0,
            "label": "cloud defaults",
        },
        "tui": {
            "refresh_interval_seconds": default.tui.refresh_interval_seconds,
            "show_system_namespaces": default.tui.show_system_namespaces,
            "compact_mode": default.tui.compact_mode,
            "color_theme": default.tui.color_theme,
        },
        "export": {
            "output_directory": default.export.output_directory,
            "dry_run": default.export.dry_run,
            "git_author_name": default.export.git_author_name,
            "git_author_email": default.export.git_author_email,
        },
    }
    return yaml.dump(data, default_flow_style=False, sort_keys=False)


__all__ = [
    "KubeSaverConfig",
    "SafetyConfig",
    "AlertConfig",
    "PricingOverrides",
    "TUIConfig",
    "ExportConfig",
    "load_config",
    "default_config_yaml",
    "ENV_PREFIX",
]
