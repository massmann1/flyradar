from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.clients.travelpayouts_rest import TravelpayoutsRestClient
from app.core.config import Settings
from app.domain.enums import CheckStatus, CheckTrigger
from app.domain.schemas import CheckResult, NotificationDTO
from app.repositories.cache import ApiCacheRepository
from app.repositories.checks import CheckRepository
from app.repositories.notifications import NotificationRepository
from app.repositories.offers import OfferRepository
from app.repositories.subscriptions import SubscriptionRepository
from app.services.dedupe import build_notification_dedupe_key, choose_notification_reason, notification_cooldown_boundary
from app.services.notifications import NotificationService, format_offer_message
from app.services.price_history import PriceHistoryService

logger = logging.getLogger(__name__)


class AlertService:
    def __init__(
        self,
        session_factory: async_sessionmaker,
        settings: Settings,
        travelpayouts_client: TravelpayoutsRestClient,
        price_history_service: PriceHistoryService,
        notification_service: NotificationService,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._travelpayouts_client = travelpayouts_client
        self._price_history_service = price_history_service
        self._notification_service = notification_service
        self._subscriptions = SubscriptionRepository()
        self._offers = OfferRepository()
        self._notifications = NotificationRepository()
        self._checks = CheckRepository()
        self._cache = ApiCacheRepository()

    async def run_due_subscriptions(self) -> list[CheckResult]:
        async with self._session_factory() as session:
            due = await self._subscriptions.list_due(
                session,
                now=datetime.now(timezone.utc),
                limit=self._settings.max_concurrent_checks,
            )
            subscription_ids = [item.id for item in due]
            await session.commit()

        results: list[CheckResult] = []
        for subscription_id in subscription_ids:
            results.append(await self.run_subscription_check(subscription_id=subscription_id, trigger=CheckTrigger.SCHEDULED))
        return results

    async def run_subscription_check(self, *, subscription_id: str, trigger: CheckTrigger) -> CheckResult:
        started_at = datetime.now(timezone.utc)
        check_id: int | None = None
        async with self._session_factory() as session:
            subscription = await self._subscriptions.get_by_id(session, subscription_id)
            if subscription is None:
                await session.commit()
                return CheckResult(subscription_id=subscription_id, status=CheckStatus.FAILED, error_message="Subscription not found")
            check = await self._checks.create(session, subscription_id=subscription.id, trigger_type=trigger)
            check_id = check.id
            await session.commit()

        try:
            async with self._session_factory() as session:
                subscription = await self._subscriptions.get_by_id(session, subscription_id)
                check = await self._checks.get_by_id(session, check_id) if check_id is not None else None
                if subscription is None:
                    await session.commit()
                    return CheckResult(subscription_id=subscription_id, status=CheckStatus.FAILED, error_message="Subscription missing")

                offers, endpoint, request_hash, payload = await self._get_cached_or_fetch(session, subscription)
                pending_notification_ids: list[int] = []
                filtered_offers = sorted(
                    [offer for offer in offers if self._offer_matches_subscription(subscription, offer)],
                    key=lambda item: item.price_amount,
                )

                if not filtered_offers:
                    finished_at = datetime.now(timezone.utc)
                    if check is not None:
                        check.status = CheckStatus.NO_RESULTS
                        check.endpoint_used = endpoint
                        check.offers_found = 0
                        check.finished_at = finished_at
                        check.duration_ms = int((check.finished_at - started_at).total_seconds() * 1000)
                    subscription.last_checked_at = finished_at
                    subscription.next_check_at = finished_at + timedelta(minutes=subscription.check_interval_minutes)
                    await session.commit()
                    return CheckResult(subscription_id=subscription_id, status=CheckStatus.NO_RESULTS, endpoint_used=endpoint)

                stored_offers = filtered_offers[: self._settings.stored_offers_per_check]
                for dto in stored_offers:
                    offer = await self._offers.upsert_offer(session, dto)
                    await self._offers.add_price_observation(
                        session,
                        offer_id=offer.id,
                        subscription_id=subscription.id,
                        price_amount=dto.price_amount,
                        currency=dto.currency,
                        provider_found_at=dto.provider_found_at,
                        api_cache_key=request_hash,
                    )
                    last_sent = await self._notifications.get_last_sent_for_offer(
                        session,
                        subscription_id=subscription.id,
                        offer_id=offer.id,
                    )
                    reason = choose_notification_reason(
                        subscription=subscription,
                        last_sent_event=last_sent,
                        current_price=dto.price_amount,
                        is_new_offer=last_sent is None,
                        settings=self._settings,
                    )
                    if reason is None:
                        continue

                    dedupe_key = build_notification_dedupe_key(subscription, offer, dto.price_amount)
                    recently_sent = await self._notifications.was_recently_sent(
                        session,
                        subscription_id=subscription.id,
                        dedupe_key=dedupe_key,
                        sent_after=notification_cooldown_boundary(self._settings),
                    )
                    if recently_sent:
                        continue

                    history_context = await self._price_history_service.build_context_for_session(
                        session,
                        subscription_id=subscription.id,
                        offer_id=offer.id,
                        current_price=dto.price_amount,
                    )
                    message_text = format_offer_message(
                        subscription=subscription,
                        offer=offer,
                        price_amount=dto.price_amount,
                        currency=dto.currency,
                        reason=reason,
                        previous_price=last_sent.price_amount if last_sent else None,
                        airline_name=await self._travelpayouts_client.get_airline_name(dto.airline_iata),
                        history_context=history_context,
                        provider_found_at=dto.provider_found_at,
                    )
                    event = await self._notifications.create(
                        session,
                        NotificationDTO(
                            subscription_id=subscription.id,
                            offer_id=offer.id,
                            dedupe_key=dedupe_key,
                            reason=reason,
                            price_amount=dto.price_amount,
                            currency=dto.currency,
                            chat_id=subscription.user.telegram_user_id,
                            message_text=message_text,
                        ),
                    )
                    pending_notification_ids.append(event.id)

                finished_at = datetime.now(timezone.utc)
                if check is not None:
                    check.status = CheckStatus.SUCCESS
                    check.endpoint_used = endpoint
                    check.request_hash = request_hash
                    check.offers_found = len(stored_offers)
                    check.finished_at = finished_at
                    check.duration_ms = int((finished_at - started_at).total_seconds() * 1000)
                subscription.last_checked_at = finished_at
                subscription.next_check_at = finished_at + timedelta(minutes=subscription.check_interval_minutes)
                if filtered_offers:
                    subscription.last_match_price = filtered_offers[0].price_amount
                await session.commit()
                notifications_sent = 0
                for event_id in pending_notification_ids:
                    notifications_sent += int(await self._notification_service.send_event(event_id))
                return CheckResult(
                    subscription_id=subscription_id,
                    status=CheckStatus.SUCCESS,
                    endpoint_used=endpoint,
                    offers_found=len(stored_offers),
                    notifications_sent=notifications_sent,
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("subscription_check_failed", extra={"subscription_id": subscription_id})
            async with self._session_factory() as session:
                subscription = await self._subscriptions.get_by_id(session, subscription_id)
                if check_id is not None:
                    check = await self._checks.get_by_id(session, check_id)
                else:
                    check = None
                if check is not None:
                    check.status = CheckStatus.FAILED
                    check.finished_at = datetime.now(timezone.utc)
                    check.error_message = str(exc)
                    check.duration_ms = int((check.finished_at - started_at).total_seconds() * 1000)
                if subscription is not None:
                    subscription.last_checked_at = datetime.now(timezone.utc)
                    subscription.next_check_at = datetime.now(timezone.utc) + timedelta(minutes=max(5, subscription.check_interval_minutes))
                await session.commit()
            return CheckResult(subscription_id=subscription_id, status=CheckStatus.FAILED, error_message=str(exc))

    async def retry_pending_notifications(self) -> int:
        return await self._notification_service.retry_pending()

    async def cleanup_old_data(self) -> dict[str, int]:
        price_history_stats = await self._price_history_service.aggregate_old_detail_history()
        now = datetime.now(timezone.utc)
        cache_cutoff = now - timedelta(days=self._settings.api_cache_retention_days)
        checks_cutoff = now - timedelta(days=self._settings.subscription_checks_retention_days)
        notifications_cutoff = now - timedelta(days=self._settings.notification_events_retention_days)
        raw_payload_cutoff = now - timedelta(days=self._settings.offer_price_detail_retention_days)

        async with self._session_factory() as session:
            deleted_cache = await self._cache.delete_expired_before(session, older_than=cache_cutoff)
            deleted_checks = await self._checks.delete_finished_before(session, older_than=checks_cutoff)
            deleted_notifications = await self._notifications.delete_created_before(session, older_than=notifications_cutoff)
            cleared_raw_payload = 0
            if not self._settings.store_raw_payload:
                cleared_raw_payload = await self._offers.clear_raw_payload_before(session, older_than=raw_payload_cutoff)
            await session.commit()

        result = {
            "deleted_cache": deleted_cache,
            "deleted_checks": deleted_checks,
            "deleted_notifications": deleted_notifications,
            "cleared_raw_payload": cleared_raw_payload,
            **price_history_stats,
        }
        logger.info("cleanup_old_data_completed", extra=result)
        return result

    async def _get_cached_or_fetch(self, session, subscription):
        offers_endpoint, params = self._travelpayouts_client._build_request(subscription)  # noqa: SLF001
        request_hash = self._travelpayouts_client.make_cache_key(offers_endpoint, params)
        now = datetime.now(timezone.utc)
        cached = await self._cache.get_valid(session, cache_key=request_hash, now=now)
        if cached is not None:
            offers = self._travelpayouts_client._normalize_offers(payload=cached.response_json, endpoint=offers_endpoint)  # noqa: SLF001
            return offers, offers_endpoint, request_hash, cached.response_json

        offers, endpoint, cache_key, payload = await self._travelpayouts_client.search_subscription(subscription)
        await self._cache.upsert(
            session,
            cache_key=cache_key,
            endpoint=endpoint,
            normalized_params=params,
            response_json=payload,
            fetched_at=now,
            expires_at=now + timedelta(seconds=self._settings.search_cache_ttl_seconds),
            http_status=200,
        )
        return offers, endpoint, cache_key, payload

    @staticmethod
    def _offer_matches_subscription(subscription, offer) -> bool:
        if subscription.preferred_airlines:
            if not offer.airline_iata:
                return False
            if offer.airline_iata.upper() not in subscription.preferred_airlines:
                return False
        return True
