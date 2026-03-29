from __future__ import annotations

from datetime import datetime, timezone

from app.clients.travelpayouts_rest import _flatten_offer_items, _parse_dt, _stored_offer_payload


def test_parse_dt_supports_short_date() -> None:
    value = _parse_dt("2026-05-01")
    assert value == datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc)


def test_flatten_offer_items_handles_grouped_prices_payload() -> None:
    payload = {
        "2026-05-01": {
            "origin": "MOW",
            "destination": "IST",
            "price": 12345,
        }
    }
    result = _flatten_offer_items(payload)
    assert result == [{"origin": "MOW", "destination": "IST", "price": 12345}]


def test_normalize_offers_extracts_nested_offers(travelpayouts_client) -> None:
    payload = {
        "success": True,
        "currency": "rub",
        "data": {
            "2026-05-01": {
                "origin": "MOW",
                "destination": "IST",
                "origin_airport": "SVO",
                "destination_airport": "IST",
                "departure_at": "2026-05-01T08:00:00+03:00",
                "return_at": "2026-05-05T10:00:00+03:00",
                "price": 12345,
                "airline": "TK",
                "flight_number": "123",
                "transfers": 0,
                "return_transfers": 0,
                "duration": 240,
                "link": "/search/mock",
            }
        },
    }

    offers = travelpayouts_client._normalize_offers(payload=payload, endpoint="/aviasales/v3/grouped_prices")  # noqa: SLF001

    assert len(offers) == 1
    offer = offers[0]
    assert offer.origin_iata == "MOW"
    assert offer.destination_iata == "IST"
    assert offer.currency == "RUB"
    assert offer.price_amount == 12345
    assert offer.airline_iata == "TK"
    assert offer.deeplink == "/search/mock"
    assert offer.provider_found_at is None


def test_normalize_offers_parses_provider_found_at_when_present(travelpayouts_client) -> None:
    payload = {
        "success": True,
        "currency": "rub",
        "data": [
            {
                "origin": "MOW",
                "destination": "IST",
                "departure_at": "2026-05-01T08:00:00+03:00",
                "price": 12345,
                "found_at": "2026-04-20T12:34:56+00:00",
            }
        ],
    }

    offers = travelpayouts_client._normalize_offers(payload=payload, endpoint="/aviasales/v3/prices_for_dates")  # noqa: SLF001

    assert len(offers) == 1
    assert offers[0].provider_found_at == datetime(2026, 4, 20, 12, 34, 56, tzinfo=timezone.utc)


def test_normalize_offers_skips_invalid_items(travelpayouts_client) -> None:
    payload = {
        "success": True,
        "currency": "rub",
        "data": [
            {"origin": "MOW", "destination": "IST", "price": "oops"},
            {"origin": "MOW", "destination": "IST", "price": 9900},
        ],
    }

    offers = travelpayouts_client._normalize_offers(payload=payload, endpoint="/aviasales/v3/prices_for_dates")  # noqa: SLF001

    assert len(offers) == 1
    assert offers[0].price_amount == 9900


def test_stored_offer_payload_can_be_compacted() -> None:
    payload = _stored_offer_payload(
        {
            "origin": "MOW",
            "destination": "IST",
            "price": 9900,
            "airline": "TK",
            "extra_field": "drop-me",
        },
        store_raw_payload=False,
    )
    assert payload == {
        "origin": "MOW",
        "destination": "IST",
        "price": 9900,
        "airline": "TK",
    }
