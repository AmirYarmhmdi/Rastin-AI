"""File guide.

- Use: Serves read-only conversation session API endpoints.
- Usage: Included by rastin_ai.api.v1.router.
- Duties: Lists reusable sessions and returns ordered persisted messages.
- Depends on: External packages: fastapi. Project modules:
  rastin_ai.api.dependencies, schemas.conversations, and services.conversations.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from rastin_ai.api.dependencies import get_conversation_service
from rastin_ai.schemas.conversations import (
    ConversationDocumentReferenceResponse,
    ConversationMessageResponse,
    ConversationSessionListResponse,
    ConversationSessionResponse,
    ConversationSessionSummaryResponse,
)
from rastin_ai.services.conversations import ConversationService

router = APIRouter(prefix="/sessions")


@router.get(
    "",
    response_model=ConversationSessionListResponse,
    summary="List conversation sessions",
)
async def list_sessions(
    conversation_service: Annotated[
        ConversationService,
        Depends(get_conversation_service),
    ],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ConversationSessionListResponse:
    sessions = await conversation_service.list_sessions(limit=limit)
    return ConversationSessionListResponse(
        sessions=tuple(
            ConversationSessionSummaryResponse(
                id=session.id,
                title=session.title,
                status=session.status,
                created_at=session.created_at,
                updated_at=session.updated_at,
            )
            for session in sessions
        )
    )


@router.get(
    "/{session_id}",
    response_model=ConversationSessionResponse,
    summary="Get conversation session",
)
async def get_session(
    session_id: UUID,
    conversation_service: Annotated[
        ConversationService,
        Depends(get_conversation_service),
    ],
) -> ConversationSessionResponse:
    session = await conversation_service.get_session(session_id)
    return ConversationSessionResponse(
        id=session.id,
        title=session.title,
        status=session.status,
        created_at=session.created_at,
        updated_at=session.updated_at,
        messages=tuple(
            ConversationMessageResponse(
                id=message.id,
                role=message.role,
                sequence=message.sequence,
                content=message.content,
                workflow_id=message.workflow_id,
                status=message.status,
                error_message=message.error_message,
                citations=message.citations,
                sources=message.sources,
                document_references=tuple(
                    ConversationDocumentReferenceResponse(**reference)
                    for reference in message.document_references
                ),
                created_at=message.created_at,
            )
            for message in session.messages
        ),
    )
