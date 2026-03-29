from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.domain.enums import TripType
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


def test_build_request_sets_one_way_false_for_fixed_round_trip(travelpayouts_client) -> None:
    subscription = SimpleNamespace(
        trip_type=TripType.ROUND_TRIP,
        origin_iata="KZN",
        destination_iata="NHA",
        departure_date_from=date(2026, 6, 1),
        departure_date_to=date(2026, 6, 1),
        return_date_from=date(2026, 6, 12),
        return_date_to=date(2026, 6, 12),
        min_trip_duration_days=None,
        max_trip_duration_days=None,
        direct_only=False,
        currency="RUB",
        market="ru",
    )

    endpoint, params = travelpayouts_client._build_request(subscription)  # noqa: SLF001

    assert endpoint == "/aviasales/v3/prices_for_dates"
    assert params["return_at"] == "2026-06-12"
    assert params["one_way"] == "false"


def test_should_retry_round_trip_with_grouped_prices_when_prices_for_dates_has_no_return(
    travelpayouts_client,
) -> None:
    subscription = SimpleNamespace(
        trip_type=TripType.ROUND_TRIP,
        origin_iata="KZN",
        destination_iata="MRV",
        departure_date_from=date(2026, 6, 1),
        departure_date_to=date(2026, 6, 1),
        return_date_from=date(2026, 6, 3),
        return_date_to=date(2026, 6, 3),
        min_trip_duration_days=None,
        max_trip_duration_days=None,
        direct_only=False,
        currency="RUB",
        market="ru",
    )
    offers = [
        SimpleNamespace(return_at=None),
        SimpleNamespace(return_at=None),
    ]

    should_retry = travelpayouts_client.should_retry_round_trip_with_grouped_prices(
        subscription,
        endpoint="/aviasales/v3/prices_for_dates",
        offers=offers,
    )

    assert should_retry is True


def test_build_round_trip_grouped_fallback_request_uses_exact_dates(travelpayouts_client) -> None:
    subscription = SimpleNamespace(
        trip_type=TripType.ROUND_TRIP,
        origin_iata="KZN",
        destination_iata="MRV",
        departure_date_from=date(2026, 6, 1),
        departure_date_to=date(2026, 6, 1),
        return_date_from=date(2026, 6, 3),
        return_date_to=date(2026, 6, 3),
        min_trip_duration_days=None,
        max_trip_duration_days=None,
        direct_only=False,
        currency="RUB",
        market="ru",
    )

    endpoint, params = travelpayouts_client.build_round_trip_grouped_fallback_request(subscription)

    assert endpoint == "/aviasales/v3/grouped_prices"
    assert params["departure_at"] == "2026-06-01"
    assert params["return_at"] == "2026-06-03"
