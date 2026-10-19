"""File guide.

- Use: Defines the API response shape for health checks.
- Usage: Import HealthResponse from rastin_ai.schemas.health.
- Duties: Defines HealthResponse and related helper logic.
- Depends on: External packages only: pydantic.
"""

from pydantic import BaseModel


# This is the documented response model for the health endpoint.
class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str
