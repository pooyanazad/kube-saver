"""Tests for retry configuration wiring (C2.1a, C2.1b).

Covers:
- RetryConfig dataclass defaults and normalization (C2.1a)
- YAML config parsing of the ``retries`` section (C2.1b)
- Environment variable overrides (KUBE_SAVER_RETRY_*) (C2.1b)
- default_config_yaml including the retries section (C2.1b)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kube_saver.config import (
    KubeSaverConfig,
    RetryConfig,
    _apply_env_overrides,
    _build_config,
    default_config_yaml,
    load_config,
)

# ── RetryConfig defaults + normalization (C2.1a) ──────────────────────────


class TestRetryConfigDefaults:
    def test_defaults(self) -> None:
        r = RetryConfig()
        assert r.max_attempts == 3
        assert r.initial_backoff_ms == 200
        assert r.max_backoff_ms == 5_000
        assert 429 in r.retryable_status_codes
        assert 503 in r.retryable_status_codes

    def test_defaults_via_top_level_config(self) -> None:
        cfg = KubeSaverConfig()
        assert cfg.retries.max_attempts == 3
        assert cfg.retries.initial_backoff_ms == 200
        assert cfg.retries.max_backoff_ms == 5_000
        assert 429 in cfg.retries.retryable_status_codes


class TestRetryConfigNormalized:
    def test_valid_values_pass_through(self) -> None:
        r = RetryConfig(max_attempts=5, initial_backoff_ms=100, max_backoff_ms=2_000)
        n = r.normalized()
        assert n.max_attempts == 5
        assert n.initial_backoff_ms == 100
        assert n.max_backoff_ms == 2_000

    def test_zero_attempts_clamped_to_one(self) -> None:
        r = RetryConfig(max_attempts=0).normalized()
        assert r.max_attempts == 1

    def test_negative_attempts_clamped_to_one(self) -> None:
        r = RetryConfig(max_attempts=-3).normalized()
        assert r.max_attempts == 1

    def test_non_numeric_attempts_replaced_with_default(self) -> None:
        r = RetryConfig(max_attempts="nope").normalized()  # type: ignore[arg-type]
        assert r.max_attempts == 3

    def test_zero_backoff_replaced_with_default(self) -> None:
        r = RetryConfig(initial_backoff_ms=0, max_backoff_ms=0).normalized()
        assert r.initial_backoff_ms == 200
        assert r.max_backoff_ms == 5_000

    def test_negative_backoff_replaced_with_default(self) -> None:
        r = RetryConfig(initial_backoff_ms=-5, max_backoff_ms=-1).normalized()
        assert r.initial_backoff_ms == 200
        assert r.max_backoff_ms == 5_000

    def test_non_numeric_backoff_replaced_with_default(self) -> None:
        r = RetryConfig(initial_backoff_ms="bad", max_backoff_ms="x").normalized()  # type: ignore[arg-type]
        assert r.initial_backoff_ms == 200
        assert r.max_backoff_ms == 5_000

    def test_initial_capped_to_max(self) -> None:
        r = RetryConfig(initial_backoff_ms=10_000, max_backoff_ms=500).normalized()
        assert r.initial_backoff_ms == 500
        assert r.max_backoff_ms == 500

    def test_empty_status_codes_restored(self) -> None:
        r = RetryConfig(retryable_status_codes=frozenset()).normalized()
        assert 429 in r.retryable_status_codes
        assert 503 in r.retryable_status_codes

    def test_non_set_status_codes_restored(self) -> None:
        r = RetryConfig(retryable_status_codes="oops").normalized()  # type: ignore[arg-type]
        assert 429 in r.retryable_status_codes

    def test_custom_status_codes_preserved(self) -> None:
        r = RetryConfig(retryable_status_codes=frozenset({503})).normalized()
        assert r.retryable_status_codes == frozenset({503})


# ── YAML config parsing (C2.1b) ────────────────────────────────────────────


class TestBuildConfigRetries:
    def test_defaults_when_absent(self) -> None:
        cfg = _build_config({})
        assert cfg.retries.max_attempts == 3
        assert cfg.retries.initial_backoff_ms == 200
        assert cfg.retries.max_backoff_ms == 5_000

    def test_custom_values(self) -> None:
        cfg = _build_config(
            {
                "retries": {
                    "max_attempts": 5,
                    "initial_backoff_ms": 50,
                    "max_backoff_ms": 1_000,
                    "retryable_status_codes": [429, 503],
                }
            }
        )
        assert cfg.retries.max_attempts == 5
        assert cfg.retries.initial_backoff_ms == 50
        assert cfg.retries.max_backoff_ms == 1_000
        assert cfg.retries.retryable_status_codes == frozenset({429, 503})

    def test_invalid_values_normalized(self) -> None:
        cfg = _build_config(
            {
                "retries": {
                    "max_attempts": 0,
                    "initial_backoff_ms": -1,
                    "max_backoff_ms": "bad",
                }
            }
        )
        assert cfg.retries.max_attempts == 1
        assert cfg.retries.initial_backoff_ms == 200
        assert cfg.retries.max_backoff_ms == 5_000

    def test_partial_values_keep_defaults_for_missing(self) -> None:
        cfg = _build_config({"retries": {"max_attempts": 7}})
        assert cfg.retries.max_attempts == 7
        assert cfg.retries.initial_backoff_ms == 200
        assert cfg.retries.max_backoff_ms == 5_000

    def test_bad_status_codes_restored(self) -> None:
        cfg = _build_config({"retries": {"retryable_status_codes": ["not", "numbers"]}})
        assert 429 in cfg.retries.retryable_status_codes
        assert 503 in cfg.retries.retryable_status_codes


class TestLoadConfigRetries:
    def test_loads_from_local_file(self, tmp_path: Path) -> None:
        local = tmp_path / "l.yaml"
        local.write_text(
            "retries:\n  max_attempts: 4\n  initial_backoff_ms: 100\n  max_backoff_ms: 2_000\n"
        )
        cfg = load_config(global_path=tmp_path / "g.yaml", local_path=local)
        assert cfg.retries.max_attempts == 4
        assert cfg.retries.initial_backoff_ms == 100
        assert cfg.retries.max_backoff_ms == 2_000

    def test_invalid_in_file_replaced_with_defaults(self, tmp_path: Path) -> None:
        local = tmp_path / "l.yaml"
        local.write_text("retries:\n  max_attempts: 0\n  initial_backoff_ms: -5\n")
        cfg = load_config(global_path=tmp_path / "g.yaml", local_path=local)
        assert cfg.retries.max_attempts == 1
        assert cfg.retries.initial_backoff_ms == 200


# ── Environment overrides (C2.1b) ──────────────────────────────────────────


class TestRetryEnvOverrides:
    def test_max_attempts_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KUBE_SAVER_RETRY_MAX_ATTEMPTS", "6")
        cfg = _apply_env_overrides(KubeSaverConfig())
        assert cfg.retries.max_attempts == 6

    def test_initial_backoff_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KUBE_SAVER_RETRY_INITIAL_BACKOFF", "250")
        cfg = _apply_env_overrides(KubeSaverConfig())
        assert cfg.retries.initial_backoff_ms == 250

    def test_max_backoff_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KUBE_SAVER_RETRY_MAX_BACKOFF", "3_000")
        cfg = _apply_env_overrides(KubeSaverConfig())
        assert cfg.retries.max_backoff_ms == 3_000

    def test_all_three_overrides(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KUBE_SAVER_RETRY_MAX_ATTEMPTS", "4")
        monkeypatch.setenv("KUBE_SAVER_RETRY_INITIAL_BACKOFF", "50")
        monkeypatch.setenv("KUBE_SAVER_RETRY_MAX_BACKOFF", "800")
        cfg = _apply_env_overrides(KubeSaverConfig())
        assert cfg.retries.max_attempts == 4
        assert cfg.retries.initial_backoff_ms == 50
        assert cfg.retries.max_backoff_ms == 800

    def test_invalid_env_replaced_with_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KUBE_SAVER_RETRY_MAX_ATTEMPTS", "not-a-number")
        monkeypatch.setenv("KUBE_SAVER_RETRY_INITIAL_BACKOFF", "-1")
        monkeypatch.setenv("KUBE_SAVER_RETRY_MAX_BACKOFF", "0")
        cfg = _apply_env_overrides(KubeSaverConfig())
        assert cfg.retries.max_attempts == 3
        assert cfg.retries.initial_backoff_ms == 200
        assert cfg.retries.max_backoff_ms == 5_000

    def test_env_overrides_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        local = tmp_path / "l.yaml"
        local.write_text("retries:\n  max_attempts: 4\n  initial_backoff_ms: 100\n")
        monkeypatch.setenv("KUBE_SAVER_RETRY_MAX_ATTEMPTS", "8")
        cfg = load_config(global_path=tmp_path / "g.yaml", local_path=local)
        assert cfg.retries.max_attempts == 8
        assert cfg.retries.initial_backoff_ms == 100  # not overridden


class TestDefaultConfigYamlIncludesRetries:
    def test_contains_retries_section(self) -> None:
        result = default_config_yaml()
        assert "retries" in result
        assert "max_attempts" in result
        assert "initial_backoff_ms" in result
        assert "max_backoff_ms" in result
        assert "retryable_status_codes" in result
