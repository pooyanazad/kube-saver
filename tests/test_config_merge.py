"""Tests for the deep-merge config layering introduced in load_config.

Covers:
- _deep_merge unit behaviour (scalars, nested dicts, lists, nulls)
- Timeout siblings preserved when local file overrides one nested key
- Pricing siblings preserved across global/local split
- Alert siblings preserved across global/local split
- Env vars still win over file values after the merge
- Edge cases: global-only, local-only, neither file present
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kube_saver.config import (
    _deep_merge,
    load_config,
)

# ── _deep_merge unit tests ─────────────────────────────────────────────────


class TestDeepMerge:
    def test_flat_scalar_override(self) -> None:
        result = _deep_merge({"a": 1, "b": 2}, {"b": 99})
        assert result == {"a": 1, "b": 99}

    def test_nested_dict_merges_key_by_key(self) -> None:
        base = {"timeouts": {"connect_seconds": 9, "read_seconds": 30}}
        override = {"timeouts": {"read_seconds": 7}}
        result = _deep_merge(base, override)
        assert result["timeouts"]["connect_seconds"] == 9, (
            "connect_seconds must be preserved when only read_seconds is overridden"
        )
        assert result["timeouts"]["read_seconds"] == 7

    def test_list_in_override_replaces_base_list(self) -> None:
        base = {"codes": [429, 500, 502]}
        override = {"codes": [503, 504]}
        result = _deep_merge(base, override)
        assert result["codes"] == [503, 504]

    def test_list_in_override_replaces_base_dict(self) -> None:
        """A list override should replace a dict base, not try to merge."""
        base = {"key": {"nested": 1}}
        override = {"key": [1, 2, 3]}
        result = _deep_merge(base, override)
        assert result["key"] == [1, 2, 3]

    def test_null_override_removes_key(self) -> None:
        base = {"connect_seconds": 9, "read_seconds": 30}
        override = {"connect_seconds": None}
        result = _deep_merge(base, override)
        assert "connect_seconds" not in result
        assert result["read_seconds"] == 30

    def test_null_override_in_nested_dict_removes_key(self) -> None:
        base = {"timeouts": {"connect_seconds": 9, "read_seconds": 30}}
        override = {"timeouts": {"connect_seconds": None}}
        result = _deep_merge(base, override)
        assert "connect_seconds" not in result["timeouts"]
        assert result["timeouts"]["read_seconds"] == 30

    def test_new_key_in_override_added(self) -> None:
        result = _deep_merge({"a": 1}, {"b": 2})
        assert result == {"a": 1, "b": 2}

    def test_original_dicts_not_mutated(self) -> None:
        base = {"x": {"y": 1}}
        override = {"x": {"z": 2}}
        _deep_merge(base, override)
        assert base == {"x": {"y": 1}}
        assert override == {"x": {"z": 2}}

    def test_deeply_nested_merge(self) -> None:
        base = {"a": {"b": {"c": 1, "d": 2}}}
        override = {"a": {"b": {"c": 99}}}
        result = _deep_merge(base, override)
        assert result["a"]["b"]["c"] == 99
        assert result["a"]["b"]["d"] == 2


# ── Timeout sibling preservation ───────────────────────────────────────────


class TestTimeoutSiblingPreservation:
    """Regression: overriding one timeout must not reset its siblings."""

    def test_local_read_seconds_preserves_global_connect_seconds(
        self, tmp_path: Path
    ) -> None:
        global_cfg = tmp_path / "global.yaml"
        local_cfg = tmp_path / "local.yaml"
        global_cfg.write_text("timeouts:\n  connect_seconds: 9\n")
        local_cfg.write_text("timeouts:\n  read_seconds: 7\n")

        cfg = load_config(global_path=global_cfg, local_path=local_cfg)

        assert cfg.timeouts.connect_seconds == 9, (
            "connect_seconds from global config was reset despite not being in local"
        )
        assert cfg.timeouts.read_seconds == 7

    def test_local_connect_seconds_preserves_global_operation_seconds(
        self, tmp_path: Path
    ) -> None:
        global_cfg = tmp_path / "global.yaml"
        local_cfg = tmp_path / "local.yaml"
        global_cfg.write_text("timeouts:\n  operation_seconds: 45\n")
        local_cfg.write_text("timeouts:\n  connect_seconds: 3\n")

        cfg = load_config(global_path=global_cfg, local_path=local_cfg)

        assert cfg.timeouts.operation_seconds == 45
        assert cfg.timeouts.connect_seconds == 3

    def test_local_full_section_overrides_all_siblings(
        self, tmp_path: Path
    ) -> None:
        """When local specifies all keys, global values should not leak."""
        global_cfg = tmp_path / "global.yaml"
        local_cfg = tmp_path / "local.yaml"
        global_cfg.write_text(
            "timeouts:\n  connect_seconds: 9\n  read_seconds: 25\n  operation_seconds: 50\n"
        )
        local_cfg.write_text(
            "timeouts:\n  connect_seconds: 2\n  read_seconds: 5\n  operation_seconds: 10\n"
        )

        cfg = load_config(global_path=global_cfg, local_path=local_cfg)

        assert cfg.timeouts.connect_seconds == 2
        assert cfg.timeouts.read_seconds == 5
        assert cfg.timeouts.operation_seconds == 10


# ── Pricing sibling preservation ───────────────────────────────────────────


class TestPricingSiblingPreservation:
    def test_local_cpu_rate_preserves_global_memory_rate(
        self, tmp_path: Path
    ) -> None:
        global_cfg = tmp_path / "global.yaml"
        local_cfg = tmp_path / "local.yaml"
        global_cfg.write_text(
            "pricing:\n  cpu_per_core_hour_usd: 0.04\n  memory_per_gb_hour_usd: 0.005\n"
        )
        local_cfg.write_text("pricing:\n  cpu_per_core_hour_usd: 0.07\n")

        cfg = load_config(global_path=global_cfg, local_path=local_cfg)

        assert cfg.pricing.cpu_per_core_hour_usd == pytest.approx(0.07)
        assert cfg.pricing.memory_per_gb_hour_usd == pytest.approx(0.005), (
            "memory rate from global config was lost when local set only cpu rate"
        )

    def test_local_memory_rate_preserves_global_label(
        self, tmp_path: Path
    ) -> None:
        global_cfg = tmp_path / "global.yaml"
        local_cfg = tmp_path / "local.yaml"
        global_cfg.write_text(
            "pricing:\n  cpu_per_core_hour_usd: 0.04\n  memory_per_gb_hour_usd: 0.005\n  label: corp-rates\n"
        )
        local_cfg.write_text("pricing:\n  memory_per_gb_hour_usd: 0.009\n")

        cfg = load_config(global_path=global_cfg, local_path=local_cfg)

        assert cfg.pricing.memory_per_gb_hour_usd == pytest.approx(0.009)
        assert cfg.pricing.label == "corp-rates"


# ── Alert sibling preservation ─────────────────────────────────────────────


class TestAlertSiblingPreservation:
    def test_local_critical_threshold_preserves_global_warning(
        self, tmp_path: Path
    ) -> None:
        global_cfg = tmp_path / "global.yaml"
        local_cfg = tmp_path / "local.yaml"
        global_cfg.write_text(
            "alerts:\n  warning_waste_ratio: 0.3\n  critical_waste_ratio: 0.7\n"
        )
        local_cfg.write_text("alerts:\n  critical_waste_ratio: 0.9\n")

        cfg = load_config(global_path=global_cfg, local_path=local_cfg)

        assert cfg.alerts.warning_waste_ratio == pytest.approx(0.3), (
            "warning_waste_ratio from global was lost when local set only critical"
        )
        assert cfg.alerts.critical_waste_ratio == pytest.approx(0.9)


# ── Environment variables win over merged file values ──────────────────────


class TestEnvVarsWinAfterMerge:
    def test_env_connect_timeout_overrides_global_and_local(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        global_cfg = tmp_path / "global.yaml"
        local_cfg = tmp_path / "local.yaml"
        global_cfg.write_text("timeouts:\n  connect_seconds: 9\n")
        local_cfg.write_text("timeouts:\n  read_seconds: 7\n")
        monkeypatch.setenv("KUBE_SAVER_TIMEOUT_CONNECT", "2")

        cfg = load_config(global_path=global_cfg, local_path=local_cfg)

        assert cfg.timeouts.connect_seconds == 2, "Env var must beat merged file value"
        assert cfg.timeouts.read_seconds == 7

    def test_env_pricing_overrides_merged_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        global_cfg = tmp_path / "global.yaml"
        local_cfg = tmp_path / "local.yaml"
        global_cfg.write_text(
            "pricing:\n  cpu_per_core_hour_usd: 0.04\n  memory_per_gb_hour_usd: 0.005\n"
        )
        local_cfg.write_text("pricing:\n  cpu_per_core_hour_usd: 0.07\n")
        monkeypatch.setenv("KUBE_SAVER_CPU_PER_CORE", "0.10")

        cfg = load_config(global_path=global_cfg, local_path=local_cfg)

        assert cfg.pricing.cpu_per_core_hour_usd == pytest.approx(0.10)
        assert cfg.pricing.memory_per_gb_hour_usd == pytest.approx(0.005)


# ── Edge cases ─────────────────────────────────────────────────────────────


class TestLoadConfigEdgeCases:
    def test_no_files_returns_defaults(self, tmp_path: Path) -> None:
        cfg = load_config(
            global_path=tmp_path / "missing.yaml",
            local_path=tmp_path / "also-missing.yaml",
        )
        assert cfg.timeouts.connect_seconds == 10.0
        assert cfg.timeouts.read_seconds == 30.0
        assert cfg.pricing.cpu_per_core_hour_usd == 0.0

    def test_global_only_no_local(self, tmp_path: Path) -> None:
        global_cfg = tmp_path / "global.yaml"
        global_cfg.write_text("timeouts:\n  connect_seconds: 6\n")

        cfg = load_config(
            global_path=global_cfg, local_path=tmp_path / "missing.yaml"
        )

        assert cfg.timeouts.connect_seconds == 6
        assert cfg.timeouts.read_seconds == 30.0  # default preserved

    def test_local_null_resets_to_default(self, tmp_path: Path) -> None:
        global_cfg = tmp_path / "global.yaml"
        local_cfg = tmp_path / "local.yaml"
        global_cfg.write_text("timeouts:\n  connect_seconds: 9\n  read_seconds: 20\n")
        # Explicit null in local should drop connect_seconds → builder default (10)
        local_cfg.write_text("timeouts:\n  connect_seconds: null\n")

        cfg = load_config(global_path=global_cfg, local_path=local_cfg)

        assert cfg.timeouts.connect_seconds == 10.0, (
            "null in local config should reset to builder default, not keep global"
        )
        assert cfg.timeouts.read_seconds == 20

    def test_local_top_level_key_does_not_affect_unrelated_section(
        self, tmp_path: Path
    ) -> None:
        global_cfg = tmp_path / "global.yaml"
        local_cfg = tmp_path / "local.yaml"
        global_cfg.write_text(
            "timeouts:\n  connect_seconds: 9\nalerts:\n  warning_waste_ratio: 0.3\n"
        )
        local_cfg.write_text("cloud_provider: aws\n")

        cfg = load_config(global_path=global_cfg, local_path=local_cfg)

        assert cfg.timeouts.connect_seconds == 9
        assert cfg.alerts.warning_waste_ratio == pytest.approx(0.3)
