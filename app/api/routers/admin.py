from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Header, status

from app.api.deps import get_container
from app.domain.enums import CheckTrigger
from app.repositories.checks import CheckRepository
from app.repositories.notifications import NotificationRepository
from app.repositories.offers import OfferRepository
from app.repositories.subscriptions import SubscriptionRepository

router = APIRouter(prefix="/admin", tags=["admin"])


def _assert_token(container, x_admin_token: str | None) -> None:
    if x_admin_token != container.settings.admin_api_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin token")


@router.get("/subscriptions")
async def list_subscriptions(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    container=Depends(get_container),
) -> list[dict]:
    _assert_token(container, x_admin_token)
    repo = SubscriptionRepository()
    async with container.session_factory() as session:
        items = await repo.list_all(session, limit=500)
        await session.commit()
    return [
        {
            "id": item.id,
            "name": item.name,
            "origin_iata": item.origin_iata,
            "destination_iata": item.destination_iata,
            "enabled": item.enabled,
            "check_interval_minutes": item.check_interval_minutes,
            "next_check_at": item.next_check_at,
        }
        for item in items
    ]


@router.post("/subscriptions/{subscription_id}/check")
async def run_subscription_check(
    subscription_id: str,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    container=Depends(get_container),
) -> dict:
    _assert_token(container, x_admin_token)
    result = await container.alert_service.run_subscription_check(subscription_id=subscription_id, trigger=CheckTrigger.API)
    return result.model_dump()


@router.get("/subscriptions/{subscription_id}/offers")
async def list_subscription_offers(
    subscription_id: str,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    container=Depends(get_container),
) -> list[dict]:
    _assert_token(container, x_admin_token)
    repo = OfferRepository()
    async with container.session_factory() as session:
        items = await repo.list_recent_for_subscription(session, subscription_id, limit=20)
        await session.commit()
    return [
        {
            "offer_id": offer.id,
            "origin_iata": offer.origin_iata,
            "destination_iata": offer.destination_iata,
            "departure_at": offer.departure_at,
            "return_at": offer.return_at,
            "airline_iata": offer.airline_iata,
            "price_amount": price.price_amount,
            "currency": price.currency,
            "observed_at": price.observed_at,
        }
        for offer, price in items
    ]


@router.get("/checks")
async def list_checks(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    container=Depends(get_container),
) -> list[dict]:
    _assert_token(container, x_admin_token)
    repo = CheckRepository()
    async with container.session_factory() as session:
        items = await repo.list_recent(session)
        await session.commit()
    return [
        {
            "id": item.id,
            "subscription_id": item.subscription_id,
            "status": item.status.value,
            "trigger_type": item.trigger_type.value,
            "started_at": item.started_at,
            "finished_at": item.finished_at,
            "offers_found": item.offers_found,
            "error_message": item.error_message,
        }
        for item in items
    ]


@router.get("/notifications")
async def list_notifications(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    container=Depends(get_container),
) -> list[dict]:
    _assert_token(container, x_admin_token)
    repo = NotificationRepository()
    async with container.session_factory() as session:
        items = await repo.list_recent(session, limit=50)
        await session.commit()
    return [
        {
            "id": item.id,
            "subscription_id": item.subscription_id,
            "offer_id": item.offer_id,
            "status": item.status.value,
            "reason": item.reason.value,
            "created_at": item.created_at,
            "sent_at": item.sent_at,
            "error_message": item.error_message,
        }
        for item in items
    ]
