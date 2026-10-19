"""File guide.

- Use: Serves document upload and listing API endpoints.
- Usage: Included by rastin_ai.api.v1.router.
- Duties: Validates API requests, delegates to document services, and returns
  stable response schemas.
- Depends on: External packages: fastapi. Project modules:
  rastin_ai.api.dependencies, rastin_ai.schemas, and
  rastin_ai.services.documents.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile, status

from rastin_ai.api.dependencies import get_document_service
from rastin_ai.schemas.documents import (
    DocumentListItem,
    DocumentListResponse,
    DocumentUploadResponse,
)
from rastin_ai.services.documents import (
    DocumentService,
    DocumentUpload,
    InvalidDocumentUploadError,
)

router = APIRouter(prefix="/documents")


@router.post(
    "",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload document",
)
async def upload_document(
    file: Annotated[UploadFile, File(description="Document file to upload.")],
    document_service: Annotated[DocumentService, Depends(get_document_service)],
) -> DocumentUploadResponse:
    if not file.filename:
        raise InvalidDocumentUploadError("Uploaded document filename is required.")

    document = await document_service.upload_document(
        DocumentUpload(
            filename=file.filename,
            content=await file.read(),
            content_type=file.content_type,
        )
    )
    return DocumentUploadResponse(
        document_id=document.document_id,
        filename=document.filename,
        content_type=document.content_type,
        status=document.status,
        workflow_id=document.workflow_id,
        file_metadata_id=document.file_metadata_id,
        normalized_extension=document.normalized_extension,
        size_bytes=document.size_bytes,
        checksum_sha256=document.checksum_sha256,
        file_storage_status=document.file_storage_status,
        indexing_error_code=document.indexing_error_code,
        indexing_error_message=document.indexing_error_message,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List documents",
)
async def list_documents(
    document_service: Annotated[DocumentService, Depends(get_document_service)],
) -> DocumentListResponse:
    documents = await document_service.list_documents()
    return DocumentListResponse(
        documents=[
            DocumentListItem(
                id=document.document_id,
                filename=document.filename,
                content_type=document.content_type,
                status=document.status,
                created_at=document.created_at,
                file_metadata_id=document.file_metadata_id,
                normalized_extension=document.normalized_extension,
                size_bytes=document.size_bytes,
                checksum_sha256=document.checksum_sha256,
                file_storage_status=document.file_storage_status,
                indexing_error_code=document.indexing_error_code,
                indexing_error_message=document.indexing_error_message,
                updated_at=document.updated_at,
            )
            for document in documents
        ]
    )
