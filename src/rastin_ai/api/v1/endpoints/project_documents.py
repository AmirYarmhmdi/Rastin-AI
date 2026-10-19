"""Project-library document endpoints."""

from pathlib import PurePosixPath, PureWindowsPath
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Response, UploadFile, status

from rastin_ai.api.dependencies import (
    get_project_access_context,
    get_project_document_service,
)
from rastin_ai.schemas.project_documents import (
    ProjectDocumentListResponse,
    ProjectDocumentResponse,
)
from rastin_ai.services.authorization import ProjectAccessContext
from rastin_ai.services.project_documents import (
    InvalidProjectDocumentUploadError,
    ProjectDocumentRecord,
    ProjectDocumentService,
    ProjectDocumentUpload,
)

router = APIRouter(prefix="/projects/{project_id}/library/documents")


@router.post(
    "",
    response_model=ProjectDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload project-library document",
)
async def upload_project_library_document(
    file: Annotated[UploadFile, File(description="Project-library file to upload.")],
    context: Annotated[ProjectAccessContext, Depends(get_project_access_context)],
    project_document_service: Annotated[
        ProjectDocumentService,
        Depends(get_project_document_service),
    ],
) -> ProjectDocumentResponse:
    if not file.filename:
        raise InvalidProjectDocumentUploadError(
            "Uploaded project document filename is required."
        )

    document = await project_document_service.upload_project_library_document(
        context,
        ProjectDocumentUpload(
            filename=file.filename,
            content=await file.read(),
            content_type=file.content_type,
        ),
    )
    return _project_document_response(document)


@router.get(
    "",
    response_model=ProjectDocumentListResponse,
    summary="List project-library documents",
)
async def list_project_library_documents(
    context: Annotated[ProjectAccessContext, Depends(get_project_access_context)],
    project_document_service: Annotated[
        ProjectDocumentService,
        Depends(get_project_document_service),
    ],
) -> ProjectDocumentListResponse:
    documents = await project_document_service.list_project_library_documents(context)
    return ProjectDocumentListResponse(
        documents=[_project_document_response(document) for document in documents]
    )


@router.get(
    "/{document_id}",
    response_model=ProjectDocumentResponse,
    summary="Get project-library document metadata",
)
async def get_project_library_document(
    document_id: UUID,
    context: Annotated[ProjectAccessContext, Depends(get_project_access_context)],
    project_document_service: Annotated[
        ProjectDocumentService,
        Depends(get_project_document_service),
    ],
) -> ProjectDocumentResponse:
    document = await project_document_service.get_project_library_document(
        context,
        document_id,
    )
    return _project_document_response(document)


@router.get(
    "/{document_id}/download",
    summary="Download project-library document",
)
async def download_project_library_document(
    document_id: UUID,
    context: Annotated[ProjectAccessContext, Depends(get_project_access_context)],
    project_document_service: Annotated[
        ProjectDocumentService,
        Depends(get_project_document_service),
    ],
) -> Response:
    document, content = await project_document_service.read_project_library_document(
        context,
        document_id,
    )
    filename = _download_filename(document.filename)
    return Response(
        content=content,
        media_type=document.content_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete project-library document",
)
async def delete_project_library_document(
    document_id: UUID,
    context: Annotated[ProjectAccessContext, Depends(get_project_access_context)],
    project_document_service: Annotated[
        ProjectDocumentService,
        Depends(get_project_document_service),
    ],
) -> Response:
    await project_document_service.delete_project_library_document(context, document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _project_document_response(
    document: ProjectDocumentRecord,
) -> ProjectDocumentResponse:
    return ProjectDocumentResponse.model_validate(document)


def _download_filename(filename: str) -> str:
    windows_name = PureWindowsPath(filename).name
    safe_name = PurePosixPath(windows_name).name
    return safe_name.replace('"', "") or "document"
