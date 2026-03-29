from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.bot.handlers.subscriptions import _build_help_text, _parse_date_range, _parse_price_input, _render_state_summary


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


def test_build_help_text_lists_user_commands() -> None:
    help_text = _build_help_text()
    assert "/new" in help_text
    assert "/subscriptions" in help_text
    assert "/help" in help_text
    assert "60 минут" in help_text


def test_render_state_summary_uses_rub_by_default() -> None:
    summary = _render_state_summary(
        {
            "name": "Тест",
            "origin_iata": "KZN",
            "destination_iata": "NHA",
            "trip_type": "one_way",
            "departure_date_from": "2026-06-01",
            "departure_date_to": None,
            "direct_only": False,
            "check_interval_minutes": 60,
            "preferred_airlines": [],
            "baggage_policy": "ignore",
            "max_price": "45000",
        }
    )
    assert "Валюта: RUB (по умолчанию)" in summary
    assert "Проверка: каждые 60 минут" in summary
