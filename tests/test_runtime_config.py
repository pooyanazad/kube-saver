"""Tests for runtime metrics configuration."""

from __future__ import annotations

from kube_saver.config import (
    RuntimeConfig,
    _apply_env_overrides,
    _build_config,
    default_config_yaml,
)


def test_runtime_config_defaults_and_yaml_parsing() -> None:
    """Use the safe default and parse the nested runtime setting."""
    assert RuntimeConfig().max_metric_age_seconds == 300.0
    config = _build_config({"runtime": {"max_metric_age_seconds": 120}})
    assert config.runtime.max_metric_age_seconds == 120.0


def test_runtime_config_normalizes_invalid_values() -> None:
    """Replace invalid metric age values with the safe default."""
    assert RuntimeConfig(max_metric_age_seconds=0).normalized().max_metric_age_seconds == 300.0
    assert RuntimeConfig(max_metric_age_seconds=-1).normalized().max_metric_age_seconds == 300.0
    assert RuntimeConfig(max_metric_age_seconds=float("nan")).normalized().max_metric_age_seconds == 300.0
    config = _build_config({"runtime": {"max_metric_age_seconds": "invalid"}})
    assert config.runtime.max_metric_age_seconds == 300.0


def test_runtime_config_environment_override(monkeypatch: object) -> None:
    """Read the metric age limit from its environment override."""
    monkeypatch.setenv("KUBE_SAVER_MAX_METRIC_AGE_SECONDS", "45")
    config = _apply_env_overrides(_build_config({}))
    assert config.runtime.max_metric_age_seconds == 45.0


def test_runtime_config_is_in_default_yaml() -> None:
    """Expose the runtime setting in generated configuration."""
    assert "max_metric_age_seconds: 300.0" in default_config_yaml()
