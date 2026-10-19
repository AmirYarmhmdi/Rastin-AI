"""File guide.

- Use: Builds the version 1 API router and includes endpoint modules.
- Usage: Import rastin_ai.api.v1.router when this module is needed.
- Duties: Keeps this small package area organized for imports.
- Depends on: Project modules: rastin_ai.api.v1.endpoints.
"""

from fastapi import APIRouter

from rastin_ai.api.v1.endpoints import (
    documents,
    health,
    messages,
    organizations,
    project_documents,
    project_sessions,
    projects,
    questions,
    sessions,
    workflows,
)

# This router collects every v1 endpoint module.
router = APIRouter()

# Health is the only v1 endpoint implemented in Phase 3.
router.include_router(health.router, tags=["health"])
router.include_router(documents.router, tags=["documents"])
router.include_router(messages.router, tags=["messages"])
router.include_router(organizations.router, tags=["organizations"])
router.include_router(project_documents.router, tags=["project-documents"])
router.include_router(project_sessions.router, tags=["project-sessions"])
router.include_router(projects.router, tags=["projects"])
router.include_router(questions.router, tags=["questions"])
router.include_router(sessions.router, tags=["sessions"])
router.include_router(workflows.router, tags=["workflows"])
