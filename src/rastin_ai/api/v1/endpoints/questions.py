"""File guide.

- Use: Serves question-answering API endpoints.
- Usage: Included by rastin_ai.api.v1.router.
- Duties: Validates question requests, delegates retrieval/orchestration to
  services, and returns stable answer schemas.
- Depends on: External packages: fastapi. Project modules:
  rastin_ai.api.dependencies, rastin_ai.schemas.questions, and
  rastin_ai.services.questions.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from rastin_ai.api.dependencies import get_question_answering_service
from rastin_ai.schemas.questions import QuestionRequest, QuestionResponse
from rastin_ai.services.questions import QuestionAnsweringService, QuestionInput

router = APIRouter(prefix="/questions")


@router.post(
    "",
    response_model=QuestionResponse,
    summary="Ask question",
)
async def ask_question(
    request: QuestionRequest,
    question_service: Annotated[
        QuestionAnsweringService,
        Depends(get_question_answering_service),
    ],
) -> QuestionResponse:
    answer = await question_service.answer(
        QuestionInput(
            question=request.question,
            document_ids=request.document_ids,
        )
    )
    return QuestionResponse(
        answer=answer.answer,
        workflow_id=answer.workflow_id,
        status=answer.status,
        message=answer.message,
        sources=answer.sources,
        citations=answer.citations,
    )
