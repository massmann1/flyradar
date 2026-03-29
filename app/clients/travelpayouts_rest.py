from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import httpx
from pydantic import ValidationError

from app.core.config import Settings
from app.domain.enums import TripType
from app.domain.models import Subscription
from app.domain.schemas import OfferDTO

logger = logging.getLogger(__name__)


class TravelpayoutsError(Exception):
    pass


class TravelpayoutsRestClient:
    def __init__(self, http_client: httpx.AsyncClient, settings: Settings) -> None:
        self._http_client = http_client
        self._settings = settings
        self._airline_names: dict[str, str] = {}
        self._airline_cache_expires_at: datetime | None = None

    async def autocomplete_places(self, term: str) -> list[dict]:
        response = await self._http_client.get(
            "https://autocomplete.travelpayouts.com/places2",
            params={"term": term, "locale": self._settings.travelpayouts_locale, "types[]": ["city", "airport"]},
            timeout=self._settings.http_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, list) else []

    async def search_subscription(self, subscription: Subscription) -> tuple[list[OfferDTO], str, str, dict]:
        endpoint, params = self._build_request(subscription)
        payload = await self._request(endpoint, params)
        offers = self._normalize_offers(payload=payload, endpoint=endpoint)
        request_hash = self.make_cache_key(endpoint, params)
        return offers, endpoint, request_hash, payload

    async def get_airline_name(self, airline_code: str | None) -> str | None:
        if not airline_code:
            return None

        code = airline_code.strip().upper()
        now = datetime.now(timezone.utc)
        if self._airline_cache_expires_at is None or now >= self._airline_cache_expires_at:
            await self._refresh_airline_directory(now)
        return self._airline_names.get(code)

    def make_cache_key(self, endpoint: str, params: dict) -> str:
        normalized = "&".join(f"{key}={params[key]}" for key in sorted(params))
        return hashlib.sha256(f"{endpoint}:{normalized}".encode("utf-8")).hexdigest()

    def should_retry_round_trip_with_grouped_prices(
        self,
        subscription: Subscription,
        *,
        endpoint: str,
        offers: list[OfferDTO],
    ) -> bool:
        departure_exact = subscription.departure_date_to is None or subscription.departure_date_to == subscription.departure_date_from
        has_fixed_return = subscription.return_date_from and (
            subscription.return_date_to is None or subscription.return_date_to == subscription.return_date_from
        )
        if subscription.trip_type != TripType.ROUND_TRIP or endpoint != "/aviasales/v3/prices_for_dates":
            return False
        if not departure_exact or not has_fixed_return:
            return False
        return not any(offer.return_at is not None for offer in offers)

    def build_round_trip_grouped_fallback_request(self, subscription: Subscription) -> tuple[str, dict]:
        return "/aviasales/v3/grouped_prices", {
            "origin": subscription.origin_iata,
            "destination": subscription.destination_iata,
            "group_by": "departure_at",
            "departure_at": subscription.departure_date_from.isoformat(),
            "return_at": subscription.return_date_from.isoformat(),
            "direct": str(subscription.direct_only).lower(),
            "currency": subscription.currency,
            "market": subscription.market,
            "token": self._settings.travelpayouts_api_token,
        }

    def _build_request(self, subscription: Subscription) -> tuple[str, dict]:
        departure_exact = subscription.departure_date_to is None or subscription.departure_date_to == subscription.departure_date_from
        has_fixed_return = subscription.return_date_from and (
            subscription.return_date_to is None or subscription.return_date_to == subscription.return_date_from
        )

        if subscription.trip_type == TripType.ONE_WAY and departure_exact:
            endpoint = "/aviasales/v3/prices_for_dates"
            params = {
                "origin": subscription.origin_iata,
                "destination": subscription.destination_iata,
                "departure_at": subscription.departure_date_from.isoformat(),
                "one_way": "true",
                "direct": str(subscription.direct_only).lower(),
                "currency": subscription.currency,
                "market": subscription.market,
                "limit": 30,
                "page": 1,
                "token": self._settings.travelpayouts_api_token,
            }
            return endpoint, params

        if subscription.trip_type == TripType.ROUND_TRIP and departure_exact and has_fixed_return:
            endpoint = "/aviasales/v3/prices_for_dates"
            params = {
                "origin": subscription.origin_iata,
                "destination": subscription.destination_iata,
                "departure_at": subscription.departure_date_from.isoformat(),
                "return_at": subscription.return_date_from.isoformat(),
                "one_way": "false",
                "direct": str(subscription.direct_only).lower(),
                "currency": subscription.currency,
                "market": subscription.market,
                "limit": 30,
                "page": 1,
                "token": self._settings.travelpayouts_api_token,
            }
            return endpoint, params

        endpoint = "/aviasales/v3/grouped_prices"
        params = {
            "origin": subscription.origin_iata,
            "destination": subscription.destination_iata,
            "group_by": "departure_at",
            "departure_at": _format_grouped_date(subscription.departure_date_from, subscription.departure_date_to),
            "direct": str(subscription.direct_only).lower(),
            "currency": subscription.currency,
            "market": subscription.market,
            "token": self._settings.travelpayouts_api_token,
        }
        if subscription.trip_type == TripType.ROUND_TRIP:
            if subscription.return_date_from and subscription.return_date_to and subscription.return_date_from == subscription.return_date_to:
                params["return_at"] = subscription.return_date_from.isoformat()
            if subscription.min_trip_duration_days:
                params["min_trip_duration"] = subscription.min_trip_duration_days
            if subscription.max_trip_duration_days:
                params["max_trip_duration"] = subscription.max_trip_duration_days
        return endpoint, params

    async def _request(self, endpoint: str, params: dict) -> dict:
        last_error: Exception | None = None
        url = f"{self._settings.travelpayouts_base_url.rstrip('/')}{endpoint}"

        for attempt in range(1, self._settings.http_max_retries + 1):
            try:
                response = await self._http_client.get(
                    url,
                    params=params,
                    timeout=self._settings.http_timeout_seconds,
                    headers={"Accept-Encoding": "gzip, deflate"},
                )

                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else self._settings.http_retry_backoff_seconds * attempt
                    await asyncio.sleep(delay)
                    continue

                response.raise_for_status()
                payload = response.json()
                if payload.get("success") is False:
                    raise TravelpayoutsError(str(payload))
                return payload
            except (httpx.HTTPError, ValueError, TravelpayoutsError) as exc:
                last_error = exc
                if attempt >= self._settings.http_max_retries:
                    break
                await asyncio.sleep(self._settings.http_retry_backoff_seconds * attempt)

        raise TravelpayoutsError(f"Travelpayouts request failed: {last_error}") from last_error

    async def _refresh_airline_directory(self, now: datetime) -> None:
        url = f"{self._settings.travelpayouts_base_url.rstrip('/')}/data/{self._settings.travelpayouts_locale}/airlines.json"
        try:
            response = await self._http_client.get(url, timeout=self._settings.http_timeout_seconds)
            response.raise_for_status()
            payload = response.json()
            mapping: dict[str, str] = {}
            if isinstance(payload, list):
                for item in payload:
                    if not isinstance(item, dict):
                        continue
                    code = str(item.get("code") or item.get("iata") or item.get("iata_code") or "").strip().upper()
                    name = _extract_airline_name(item, self._settings.travelpayouts_locale)
                    if code and name:
                        mapping[code] = name

            if mapping:
                self._airline_names = mapping
                self._airline_cache_expires_at = now + timedelta(hours=24)
                return
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            logger.warning("airline_directory_fetch_failed", extra={"error": str(exc)})

        self._airline_cache_expires_at = now + timedelta(hours=1)

    def _normalize_offers(self, *, payload: dict, endpoint: str) -> list[OfferDTO]:
        data = payload.get("data")
        currency = payload.get("currency", self._settings.travelpayouts_default_currency)
        items = _flatten_offer_items(data)

        offers: list[OfferDTO] = []
        for item in items:
            offer = self._build_offer(item=item, endpoint=endpoint, currency=currency)
            if offer is not None:
                offers.append(offer)
        return offers

    def _build_offer(self, *, item: dict, endpoint: str, currency: str) -> OfferDTO | None:
        try:
            departure_at = _parse_dt(item.get("departure_at"))
            return_at = _parse_dt(item.get("return_at"))
            airline = item.get("airline")
            flight_number = item.get("flight_number")
            transfers = item.get("transfers")
            return_transfers = item.get("return_transfers")
            duration = item.get("duration")
            price = Decimal(str(item.get("price")))

            stable_variant_key = hashlib.sha256(
                "|".join(
                    [
                        str(item.get("origin") or item.get("origin_code") or ""),
                        str(item.get("destination") or item.get("destination_code") or ""),
                        str(item.get("origin_airport") or ""),
                        str(item.get("destination_airport") or ""),
                        departure_at.isoformat() if departure_at else "",
                        return_at.isoformat() if return_at else "",
                        str(airline or ""),
                        str(flight_number or ""),
                        str(transfers or ""),
                        str(return_transfers or ""),
                        currency,
                    ]
                ).encode("utf-8")
            ).hexdigest()

            exact_offer_key = hashlib.sha256(f"{stable_variant_key}|{price}|{currency}".encode("utf-8")).hexdigest()

            return OfferDTO(
                stable_variant_key=stable_variant_key,
                exact_offer_key=exact_offer_key,
                origin_iata=(item.get("origin") or item.get("origin_code") or "").upper(),
                destination_iata=(item.get("destination") or item.get("destination_code") or "").upper(),
                origin_airport_iata=item.get("origin_airport"),
                destination_airport_iata=item.get("destination_airport"),
                departure_at=departure_at,
                return_at=return_at,
                airline_iata=airline,
                flight_number=str(flight_number) if flight_number is not None else None,
                transfers=int(transfers) if transfers is not None else None,
                return_transfers=int(return_transfers) if return_transfers is not None else None,
                duration_minutes=int(duration) if duration is not None else None,
                price_amount=price,
                currency=currency.upper(),
                deeplink=item.get("link"),
                source_endpoint=endpoint,
                provider_found_at=_parse_dt(item.get("found_at")),
                raw_payload=_stored_offer_payload(item, store_raw_payload=self._settings.store_raw_payload),
            )
        except (ValidationError, TypeError, ValueError, ArithmeticError) as exc:
            logger.warning("skip_invalid_offer", extra={"endpoint": endpoint, "error": str(exc), "item": item})
            return None


def _format_grouped_date(date_from: date, date_to: date | None) -> str:
    if date_to is None or date_to == date_from:
        return date_from.isoformat()
    if date_from.day == 1 and date_to.day >= 28 and date_from.month == date_to.month and date_from.year == date_to.year:
        return date_from.strftime("%Y-%m")
    return date_from.isoformat()


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    if len(value) == 10:
        return datetime.fromisoformat(f"{value}T00:00:00+00:00")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _flatten_offer_items(data: object) -> list[dict]:
    items: list[dict] = []
    if isinstance(data, list):
        for value in data:
            if isinstance(value, dict):
                items.append(value)
    elif isinstance(data, dict):
        looks_like_offer = any(key in data for key in {"price", "departure_at", "origin", "destination"})
        if looks_like_offer:
            items.append(data)
        else:
            for value in data.values():
                items.extend(_flatten_offer_items(value))
    return items


def _extract_airline_name(item: dict, locale: str) -> str | None:
    translations = item.get("name_translations")
    if isinstance(translations, dict):
        localized = translations.get(locale)
        if isinstance(localized, str) and localized.strip():
            return localized.strip()
        english = translations.get("en")
        if isinstance(english, str) and english.strip():
            return english.strip()

    name = item.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None


def _stored_offer_payload(item: dict, *, store_raw_payload: bool) -> dict:
    if store_raw_payload:
        return item
    keys = (
        "origin",
        "destination",
        "origin_airport",
        "destination_airport",
        "departure_at",
        "return_at",
        "price",
        "airline",
        "flight_number",
        "transfers",
        "return_transfers",
        "duration",
        "link",
        "found_at",
    )
    return {key: item.get(key) for key in keys if key in item}
