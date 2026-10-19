"""File guide.

- Use: Defines public API schemas for question-answering endpoints.
- Usage: Import question request and response models from
  rastin_ai.schemas.questions.
- Duties: Keeps API question schemas separate from service internals.
- Depends on: External packages only: pydantic, typing, and uuid.
"""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class QuestionRequest(BaseModel):
    """Request for asking a question over indexed documents."""

    question: str = Field(min_length=1)
    document_ids: list[UUID] = Field(default_factory=list)

    @field_validator("question")
    @classmethod
    def strip_question(cls, question: str) -> str:
        stripped = question.strip()
        if not stripped:
            msg = "Question must not be empty."
            raise ValueError(msg)

        return stripped


class QuestionResponse(BaseModel):
    """Answer and supported execution metadata."""

    answer: str
    workflow_id: UUID | None = None
    status: str = "answered"
    message: str | None = None
    sources: tuple[dict[str, Any], ...] = ()
    citations: tuple[dict[str, Any], ...] = ()
