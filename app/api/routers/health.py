from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text

from app.api.deps import get_container

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def live() -> dict:
    return {"status": "ok"}


@router.get("/ready")
async def ready(container=Depends(get_container)) -> dict:
    async with container.session_factory() as session:
        await session.execute(text("SELECT 1"))
        await session.commit()
    return {"status": "ready", "time": datetime.now(timezone.utc).isoformat()}
