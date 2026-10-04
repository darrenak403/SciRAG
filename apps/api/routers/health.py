from fastapi import APIRouter, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from apps.api.deps import Db

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(db: Db) -> dict[str, str]:
    try:
        await db.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError) as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database unreachable") from error
    return {"status": "ok"}
