"""Tests for currency and custom pricing."""

from kube_saver.config import KubeSaverConfig, load_config, default_config_yaml
from kube_saver.models.core import Currency, Money, ResourceWaste
from kube_saver.pricing.display import convert_cost, format_yearly
from kube_saver.pricing.engine import PricingEngine
from kube_saver.models.core import CloudProvider, CostInfo


def test_currency_symbols() -> None:
    assert Currency.USD.symbol == "$"
    assert Currency.EUR.symbol == "€"
    assert Currency.GBP.symbol == "£"
    assert Currency.AED.symbol == "د.إ"
    assert Currency.JPY.symbol == "¥"


def test_money_format() -> None:
    m = Money(amount=62.05, currency=Currency.EUR)
    assert m.formatted == "€62.05"


def test_money_yearly() -> None:
    m = Money(amount=62.05, currency=Currency.USD)
    assert m.yearly_formatted == "$744.60"


def test_default_currency_is_usd() -> None:
    cfg = KubeSaverConfig()
    assert cfg.currency == Currency.USD
    assert cfg.exchange_rate_from_usd == 1.0


def test_default_config_yaml_has_currency() -> None:
    yaml = default_config_yaml()
    assert "currency:" in yaml
    assert "exchange_rate_from_usd:" in yaml


def test_pricing_overrides() -> None:
    engine = PricingEngine(provider=CloudProvider.AWS, tier="general")
    engine.set_rate(cpu_per_core_hour=0.10, memory_per_gb_hour=0.01, label="custom")

    waste = ResourceWaste(cpu_millicores=1000, memory_bytes=1024**3)
    cost = engine.cost_from_waste(waste)

    expected_cpu = 1 * 0.10 * 730
    expected_mem = 1 * 0.01 * 730
    assert abs(cost.monthly_usd - (expected_cpu + expected_mem)) < 0.01


def test_convert_cost_to_currency() -> None:
    cost = CostInfo.from_hourly(0.1)
    money = convert_cost(cost, Currency.EUR, rate_from_usd=0.92)
    assert money.currency == Currency.EUR
    assert money.amount > 0


def test_format_yearly_helper() -> None:
    cost = CostInfo.from_hourly(0.05)
    money = format_yearly(cost, Currency.GBP, rate_from_usd=0.79)
    assert money.currency == Currency.GBP
    assert money.amount == cost.yearly_usd * 0.79