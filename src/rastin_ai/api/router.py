"""File guide.

- Use: Builds the top-level API router and includes versioned routers.
- Usage: Import rastin_ai.api.router when this module is needed.
- Duties: Keeps this small package area organized for imports.
- Depends on: Project modules: rastin_ai.api.v1.router, and
  rastin_ai.core.config.
"""

from fastapi import APIRouter

from rastin_ai.api.v1.router import router as v1_router
from rastin_ai.core.config import get_settings

# Load settings so the API prefix can come from one central place.
settings = get_settings()

# This is the top-level API router for the whole backend.
router = APIRouter()

# This mounts version 1 routes under the configured API prefix.
router.include_router(v1_router, prefix=settings.API_V1_PREFIX)
