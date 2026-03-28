from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.bot.handlers.subscriptions import _parse_date_range, _parse_price_input


def test_parse_date_range_supports_russian_format() -> None:
    date_from, date_to = _parse_date_range("01.06.2026 - 12.06.2026")
    assert date_from == date(2026, 6, 1)
    assert date_to == date(2026, 6, 12)


def test_parse_date_range_supports_iso_format() -> None:
    date_from, date_to = _parse_date_range("2026-06-01:2026-06-12")
    assert date_from == date(2026, 6, 1)
    assert date_to == date(2026, 6, 12)


def test_parse_price_input_supports_plain_thousands() -> None:
    assert _parse_price_input("45") == Decimal("45000")


def test_parse_price_input_supports_suffix_k() -> None:
    assert _parse_price_input("12.5к") == Decimal("12500")

