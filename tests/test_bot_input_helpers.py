from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.bot.keyboards.subscriptions import place_suggestions_keyboard, subscription_actions_keyboard
from app.bot.handlers.subscriptions import (
    _build_help_text,
    _format_place_option,
    _normalize_place_suggestions,
    _parse_date_range,
    _parse_price_input,
    _render_state_summary,
)


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
    assert "➕ Новая подписка" in help_text
    assert "редактировать подписку" in help_text.lower()


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


def test_subscription_actions_keyboard_has_edit_button() -> None:
    keyboard = subscription_actions_keyboard("sub-id", enabled=True)
    labels = [button.text for row in keyboard.inline_keyboard for button in row]
    assert "Редактировать" in labels


def test_normalize_place_suggestions_deduplicates_codes_and_limits_to_five() -> None:
    options = [
        {"code": "NHA", "name": "Cam Ranh", "city_name": "Нячанг", "country_name": "Вьетнам", "type": "airport"},
        {"code": "NHA", "name": "Nha Trang", "city_name": "Нячанг", "country_name": "Вьетнам", "type": "city"},
        {"code": "SGN", "name": "Хошимин", "country_name": "Вьетнам", "type": "city"},
        {"code": "BKK", "name": "Бангкок", "country_name": "Таиланд", "type": "city"},
        {"code": "HKT", "name": "Пхукет", "country_name": "Таиланд", "type": "city"},
        {"code": "DME", "name": "Домодедово", "city_name": "Москва", "country_name": "Россия", "type": "airport"},
        {"code": "SVO", "name": "Шереметьево", "city_name": "Москва", "country_name": "Россия", "type": "airport"},
    ]

    suggestions = _normalize_place_suggestions(options)

    assert len(suggestions) == 5
    assert suggestions[0]["code"] == "NHA"
    assert suggestions[0]["label"] == "Нячанг — Cam Ranh, Вьетнам (NHA)"
    assert [item["code"] for item in suggestions].count("NHA") == 1


def test_format_place_option_uses_city_airport_country_label() -> None:
    label = _format_place_option(
        {"code": "DME", "name": "Домодедово", "city_name": "Москва", "country_name": "Россия", "type": "airport"}
    )
    assert label == "Москва — Домодедово, Россия (DME)"


def test_place_suggestions_keyboard_has_retry_button() -> None:
    keyboard = place_suggestions_keyboard("origin", [{"code": "NHA", "label": "Нячанг, Вьетнам (NHA)"}])
    labels = [button.text for row in keyboard.inline_keyboard for button in row]
    assert "Нячанг, Вьетнам (NHA)" in labels
    assert "Ввести по-другому" in labels
