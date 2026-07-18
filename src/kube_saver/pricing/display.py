"""Display helpers for kube-saver.

Formats cost values in the user's chosen currency.
"""

from __future__ import annotations

from kube_saver.models.core import CostInfo, Currency, Money


def convert_cost(cost: CostInfo, currency: Currency, rate_from_usd: float = 1.0) -> Money:
    """Convert a ``CostInfo`` to a Money amount in the chosen currency."""
    return Money(amount=cost.monthly_usd * rate_from_usd, currency=currency)


def format_yearly(cost: CostInfo, currency: Currency, rate_from_usd: float = 1.0) -> Money:
    """Convert a ``CostInfo`` to a Money amount showing yearly value."""
    return Money(amount=cost.yearly_usd * rate_from_usd, currency=currency)


def _money(amount: float, currency: Currency) -> str:
    return f"{currency.symbol}{amount:.2f}"


__all__ = ["convert_cost", "format_yearly"]
