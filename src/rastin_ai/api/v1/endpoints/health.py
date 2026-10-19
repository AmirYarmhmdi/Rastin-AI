"""File guide.

- Use: Serves the health-check endpoint for the API.
- Usage: Import health_check from rastin_ai.api.v1.endpoints.health.
- Duties: Defines health_check and related helper logic.
- Depends on: Project modules: rastin_ai.core.config, and
  rastin_ai.schemas.health.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from rastin_ai.core.config import get_settings
from rastin_ai.database.session import get_async_session
from rastin_ai.schemas.health import HealthResponse

# This router holds the health endpoint routes.
router = APIRouter()


# This endpoint lets callers check that the backend is running.
@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    # Read settings so the response uses the configured app identity.
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
    )


@router.get("/ready", status_code=status.HTTP_200_OK)
async def readiness_check(
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> dict[str, str]:
    try:
        await session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable.",
        ) from exc

    return {"status": "ready"}
