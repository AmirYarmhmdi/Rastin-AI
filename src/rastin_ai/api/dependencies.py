"""File guide.

- Use: Provides FastAPI dependency factories for API services.
- Usage: Import dependency callables from rastin_ai.api.dependencies in routes.
- Duties: Wires repositories, storage, RAG, and service facades without putting
  construction logic in endpoint modules.
- Depends on: External packages: fastapi and sqlalchemy. Project modules:
  rastin_ai.core, database, rag, repositories, services, and storage.
"""

from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import Depends, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from rastin_ai.agent.graph import create_agent_graph
from rastin_ai.agent.response_generator import OpenAIResponseGenerator
from rastin_ai.core.config import (
    ConfigurationError,
    ConfigurationIssue,
    Settings,
    get_settings,
)
from rastin_ai.core.exceptions import AppException
from rastin_ai.database.session import get_async_session
from rastin_ai.rag.chunking.recursive import RecursiveTextChunker
from rastin_ai.rag.context.builder import ContextBuilder
from rastin_ai.rag.embeddings.openai import OpenAIEmbeddingProvider
from rastin_ai.rag.exceptions import VectorStoreError
from rastin_ai.rag.indexing import DocumentIndexer
from rastin_ai.rag.loaders.base import DocumentLoader
from rastin_ai.rag.retrieval.retriever import Retriever
from rastin_ai.rag.vectorstores.qdrant import QdrantVectorStore
from rastin_ai.repositories.conversations import (
    ConversationRepository,
    SQLAlchemyConversationRepository,
)
from rastin_ai.repositories.documents import (
    DocumentRepository,
    SQLAlchemyDocumentRepository,
)
from rastin_ai.repositories.file_metadata import (
    FileMetadataRepository,
    SQLAlchemyFileMetadataRepository,
)
from rastin_ai.repositories.organizations import (
    OrganizationRepository,
    SQLAlchemyOrganizationRepository,
)
from rastin_ai.repositories.project_documents import (
    ProjectDocumentRepository,
    SQLAlchemyProjectDocumentRepository,
)
from rastin_ai.repositories.projects import (
    ProjectRepository,
    SQLAlchemyProjectRepository,
)
from rastin_ai.repositories.users import SQLAlchemyUserRepository, UserRepository
from rastin_ai.repositories.workflow_execution import (
    SQLAlchemyWorkflowExecutionRepository,
    WorkflowExecutionRepository,
)
from rastin_ai.security.auth import (
    AuthenticatedPrincipal,
    ExternalIdentity,
    validate_bearer_token,
)
from rastin_ai.services.authorization import (
    AuthorizationService,
    OrganizationAccessContext,
    ProjectAccessContext,
)
from rastin_ai.services.conversations import (
    ConversationHistoryBuilder,
    ConversationService,
    ProjectConversationHistoryBuilder,
    ProjectConversationService,
    RepositoryConversationService,
    RepositoryProjectConversationService,
)
from rastin_ai.services.document_ingestion import (
    DocumentIngestionService,
    SynchronousDocumentIngestionService,
)
from rastin_ai.services.documents import DocumentService, StoredDocumentService
from rastin_ai.services.messages import MessageSubmissionService
from rastin_ai.services.orchestration import (
    AgentGraphInvoker,
    RoutedQuestionAnsweringService,
)
from rastin_ai.services.organizations import (
    OrganizationService,
    RepositoryOrganizationService,
)
from rastin_ai.services.project_documents import (
    ProjectDocumentService,
    StoredProjectDocumentService,
)
from rastin_ai.services.project_messages import ProjectMessageSubmissionService
from rastin_ai.services.project_workflows import ProjectWorkflowStatusService
from rastin_ai.services.projects import ProjectService, RepositoryProjectService
from rastin_ai.services.questions import (
    QuestionAnsweringService,
    QuestionAnsweringUnavailableError,
    RAGQuestionAnsweringService,
)
from rastin_ai.services.upload import UploadService
from rastin_ai.services.workflows import (
    RepositoryWorkflowStatusService,
    WorkflowStatusService,
)
from rastin_ai.skills.document_processing import DocumentProcessingSkill
from rastin_ai.storage.azure_blob import AzureBlobStorageProvider
from rastin_ai.storage.base import StorageProvider
from rastin_ai.storage.local import LocalStorageProvider
from rastin_ai.tools.registry import get_runtime_skill_registry, register_skill


def get_storage_provider(
    settings: Annotated[Settings, Depends(get_settings)],
) -> StorageProvider:
    if settings.STORAGE_BACKEND == "local":
        return _get_local_storage_provider(settings.LOCAL_STORAGE_ROOT)

    if settings.STORAGE_BACKEND == "azure_blob":
        account_name = _require_azure_storage_config(
            settings.AZURE_STORAGE_ACCOUNT_NAME,
            "AZURE_STORAGE_ACCOUNT_NAME",
        )
        container_name = _require_azure_storage_config(
            settings.AZURE_STORAGE_CONTAINER_NAME,
            "AZURE_STORAGE_CONTAINER_NAME",
        )
        return _get_azure_blob_storage_provider(
            account_name,
            container_name,
            settings.AZURE_STORAGE_MANAGED_IDENTITY_CLIENT_ID,
        )

    raise ConfigurationError(
        [
            ConfigurationIssue(
                "STORAGE_BACKEND",
                "must be one of: azure_blob, local.",
            )
        ]
    )


async def close_storage_providers() -> None:
    for provider in tuple(_azure_blob_storage_providers):
        await provider.aclose()
        _azure_blob_storage_providers.remove(provider)

    _get_local_storage_provider.cache_clear()
    _get_azure_blob_storage_provider.cache_clear()


@lru_cache
def _get_local_storage_provider(storage_root: str) -> LocalStorageProvider:
    return LocalStorageProvider(storage_root)


@lru_cache
def _get_azure_blob_storage_provider(
    account_name: str,
    container_name: str,
    managed_identity_client_id: str | None,
) -> AzureBlobStorageProvider:
    provider = AzureBlobStorageProvider(
        account_name=account_name,
        container_name=container_name,
        managed_identity_client_id=managed_identity_client_id,
    )
    _azure_blob_storage_providers.add(provider)
    return provider


def _require_azure_storage_config(value: str | None, name: str) -> str:
    if value is None or not value.strip():
        raise ConfigurationError(
            [
                ConfigurationIssue(
                    name,
                    "is required when STORAGE_BACKEND=azure_blob.",
                )
            ]
        )
    return value.strip()


_azure_blob_storage_providers: set[AzureBlobStorageProvider] = set()
_bearer_scheme = HTTPBearer(auto_error=False)


def get_external_identity(
    settings: Annotated[Settings, Depends(get_settings)],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(_bearer_scheme),
    ],
) -> ExternalIdentity:
    return validate_bearer_token(
        token=credentials.credentials if credentials is not None else None,
        settings=settings,
    )


def get_file_metadata_repository(
    _identity: Annotated[ExternalIdentity, Depends(get_external_identity)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> FileMetadataRepository:
    return SQLAlchemyFileMetadataRepository(session)


def get_document_repository(
    _identity: Annotated[ExternalIdentity, Depends(get_external_identity)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> DocumentRepository:
    return SQLAlchemyDocumentRepository(session)


def get_conversation_repository(
    _identity: Annotated[ExternalIdentity, Depends(get_external_identity)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ConversationRepository:
    return SQLAlchemyConversationRepository(session)


def get_workflow_execution_repository(
    _identity: Annotated[ExternalIdentity, Depends(get_external_identity)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> WorkflowExecutionRepository:
    return SQLAlchemyWorkflowExecutionRepository(session)


def get_organization_repository(
    _identity: Annotated[ExternalIdentity, Depends(get_external_identity)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> OrganizationRepository:
    return SQLAlchemyOrganizationRepository(session)


def get_project_repository(
    _identity: Annotated[ExternalIdentity, Depends(get_external_identity)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ProjectRepository:
    return SQLAlchemyProjectRepository(session)


def get_project_document_repository(
    _identity: Annotated[ExternalIdentity, Depends(get_external_identity)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ProjectDocumentRepository:
    return SQLAlchemyProjectDocumentRepository(session)


def get_user_repository(
    _identity: Annotated[ExternalIdentity, Depends(get_external_identity)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> UserRepository:
    return SQLAlchemyUserRepository(session)


async def get_current_principal(
    identity: Annotated[ExternalIdentity, Depends(get_external_identity)],
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
) -> AuthenticatedPrincipal:
    user = await user_repository.resolve_external_identity(identity)
    if not user.is_active:
        raise AppException(
            "User is inactive.",
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="USER_INACTIVE",
        )
    return AuthenticatedPrincipal(
        user_id=user.id,
        issuer=identity.issuer,
        subject=identity.subject,
        email=user.email,
        display_name=user.display_name,
    )


def get_authorization_service(
    organization_repository: Annotated[
        OrganizationRepository,
        Depends(get_organization_repository),
    ],
    project_repository: Annotated[
        ProjectRepository,
        Depends(get_project_repository),
    ],
) -> AuthorizationService:
    return AuthorizationService(
        organization_repository=organization_repository,
        project_repository=project_repository,
    )


async def get_organization_access_context(
    organization_id: UUID,
    authorization_service: Annotated[
        AuthorizationService,
        Depends(get_authorization_service),
    ],
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
) -> OrganizationAccessContext:
    return await authorization_service.organization_context(
        organization_id,
        principal=principal,
    )


async def get_project_access_context(
    project_id: UUID,
    authorization_service: Annotated[
        AuthorizationService,
        Depends(get_authorization_service),
    ],
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
) -> ProjectAccessContext:
    return await authorization_service.project_context(
        project_id,
        principal=principal,
    )


def get_organization_service(
    organization_repository: Annotated[
        OrganizationRepository,
        Depends(get_organization_repository),
    ],
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
    authorization_service: Annotated[
        AuthorizationService,
        Depends(get_authorization_service),
    ],
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
) -> OrganizationService:
    return RepositoryOrganizationService(
        organization_repository=organization_repository,
        user_repository=user_repository,
        authorization_service=authorization_service,
        principal=principal,
    )


def get_project_service(
    project_repository: Annotated[
        ProjectRepository,
        Depends(get_project_repository),
    ],
    organization_repository: Annotated[
        OrganizationRepository,
        Depends(get_organization_repository),
    ],
    authorization_service: Annotated[
        AuthorizationService,
        Depends(get_authorization_service),
    ],
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
) -> ProjectService:
    return RepositoryProjectService(
        project_repository=project_repository,
        organization_repository=organization_repository,
        authorization_service=authorization_service,
        principal=principal,
    )


def get_project_document_service(
    settings: Annotated[Settings, Depends(get_settings)],
    storage_provider: Annotated[StorageProvider, Depends(get_storage_provider)],
    project_document_repository: Annotated[
        ProjectDocumentRepository,
        Depends(get_project_document_repository),
    ],
    authorization_service: Annotated[
        AuthorizationService,
        Depends(get_authorization_service),
    ],
) -> ProjectDocumentService:
    return StoredProjectDocumentService(
        storage_provider=storage_provider,
        project_document_repository=project_document_repository,
        authorization_service=authorization_service,
        vector_store_factory=lambda: _build_project_document_vector_store(settings),
        indexer_factory=lambda loader: _build_document_indexer(settings, loader),
        storage_backend=settings.STORAGE_BACKEND,
        max_upload_bytes=settings.MAX_UPLOAD_BYTES,
    )


def get_upload_service(
    settings: Annotated[Settings, Depends(get_settings)],
    storage_provider: Annotated[StorageProvider, Depends(get_storage_provider)],
    document_repository: Annotated[
        DocumentRepository,
        Depends(get_document_repository),
    ],
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
) -> UploadService:
    return UploadService(
        storage_provider=storage_provider,
        document_repository=document_repository,
        user_id=principal.user_id,
        storage_backend=settings.STORAGE_BACKEND,
        max_upload_bytes=settings.MAX_UPLOAD_BYTES,
    )


def get_document_ingestion_service(
    settings: Annotated[Settings, Depends(get_settings)],
    storage_provider: Annotated[StorageProvider, Depends(get_storage_provider)],
    document_repository: Annotated[
        DocumentRepository,
        Depends(get_document_repository),
    ],
) -> DocumentIngestionService:
    return SynchronousDocumentIngestionService(
        storage_provider=storage_provider,
        document_repository=document_repository,
        indexer_factory=lambda loader: _build_document_indexer(settings, loader),
    )


def get_document_service(
    upload_service: Annotated[UploadService, Depends(get_upload_service)],
    document_repository: Annotated[
        DocumentRepository,
        Depends(get_document_repository),
    ],
    ingestion_service: Annotated[
        DocumentIngestionService,
        Depends(get_document_ingestion_service),
    ],
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
) -> DocumentService:
    return StoredDocumentService(
        upload_service=upload_service,
        document_repository=document_repository,
        ingestion_service=ingestion_service,
        user_id=principal.user_id,
    )


def get_workflow_status_service(
    workflow_repository: Annotated[
        WorkflowExecutionRepository,
        Depends(get_workflow_execution_repository),
    ],
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
) -> WorkflowStatusService:
    return RepositoryWorkflowStatusService(
        workflow_repository,
        user_id=principal.user_id,
    )


def get_conversation_history_builder(
    settings: Annotated[Settings, Depends(get_settings)],
    conversation_repository: Annotated[
        ConversationRepository,
        Depends(get_conversation_repository),
    ],
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
) -> ConversationHistoryBuilder:
    return ConversationHistoryBuilder(
        conversation_repository,
        user_id=principal.user_id,
        max_turns=settings.CONVERSATION_HISTORY_MAX_TURNS,
        max_chars=settings.CONVERSATION_HISTORY_MAX_CHARS,
    )


def get_project_conversation_history_builder(
    settings: Annotated[Settings, Depends(get_settings)],
    conversation_repository: Annotated[
        ConversationRepository,
        Depends(get_conversation_repository),
    ],
) -> ProjectConversationHistoryBuilder:
    return ProjectConversationHistoryBuilder(
        conversation_repository,
        max_turns=settings.CONVERSATION_HISTORY_MAX_TURNS,
        max_chars=settings.CONVERSATION_HISTORY_MAX_CHARS,
    )


def get_conversation_service(
    conversation_repository: Annotated[
        ConversationRepository,
        Depends(get_conversation_repository),
    ],
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
) -> ConversationService:
    return RepositoryConversationService(
        conversation_repository,
        user_id=principal.user_id,
    )


def get_project_conversation_service(
    settings: Annotated[Settings, Depends(get_settings)],
    conversation_repository: Annotated[
        ConversationRepository,
        Depends(get_conversation_repository),
    ],
    authorization_service: Annotated[
        AuthorizationService,
        Depends(get_authorization_service),
    ],
) -> ProjectConversationService:
    return RepositoryProjectConversationService(
        conversation_repository,
        authorization_service=authorization_service,
        max_messages=settings.CONVERSATION_HISTORY_MAX_TURNS * 2,
    )


def ensure_core_document_capabilities_registered() -> None:
    skill = DocumentProcessingSkill()
    registry = get_runtime_skill_registry()
    if registry.get(skill.name) is not None:
        return

    register_skill(skill)


def get_agent_graph(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AgentGraphInvoker:
    ensure_core_document_capabilities_registered()
    return create_agent_graph(settings=settings)


def get_question_answering_service(
    settings: Annotated[Settings, Depends(get_settings)],
    document_service: Annotated[DocumentService, Depends(get_document_service)],
    workflow_repository: Annotated[
        WorkflowExecutionRepository,
        Depends(get_workflow_execution_repository),
    ],
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
) -> QuestionAnsweringService:
    embedding_provider = OpenAIEmbeddingProvider(settings=settings)
    retriever = Retriever(
        embedding_provider=embedding_provider,
        vector_store=_get_qdrant_vector_store(settings, embedding_provider.dimension),
    )
    return RAGQuestionAnsweringService(
        retriever=retriever,
        context_builder=ContextBuilder(max_chars=settings.RAG_CONTEXT_MAX_CHARS),
        response_generator=OpenAIResponseGenerator(settings=settings),
        document_service=document_service,
        workflow_repository=workflow_repository,
        user_id=principal.user_id,
        top_k=settings.RAG_RETRIEVAL_TOP_K,
    )


def get_routed_question_answering_service(
    document_service: Annotated[DocumentService, Depends(get_document_service)],
    workflow_repository: Annotated[
        WorkflowExecutionRepository,
        Depends(get_workflow_execution_repository),
    ],
    direct_question_service: Annotated[
        QuestionAnsweringService,
        Depends(get_question_answering_service),
    ],
    agent_graph: Annotated[AgentGraphInvoker, Depends(get_agent_graph)],
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
) -> QuestionAnsweringService:
    return RoutedQuestionAnsweringService(
        direct_question_service=direct_question_service,
        workflow_repository=workflow_repository,
        document_service=document_service,
        agent_graph=agent_graph,
        user_id=principal.user_id,
    )


def get_message_submission_service(
    document_service: Annotated[DocumentService, Depends(get_document_service)],
    question_service: Annotated[
        QuestionAnsweringService,
        Depends(get_routed_question_answering_service),
    ],
    conversation_repository: Annotated[
        ConversationRepository,
        Depends(get_conversation_repository),
    ],
    history_builder: Annotated[
        ConversationHistoryBuilder,
        Depends(get_conversation_history_builder),
    ],
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
) -> MessageSubmissionService:
    return MessageSubmissionService(
        document_service=document_service,
        question_service=question_service,
        conversation_repository=conversation_repository,
        history_builder=history_builder,
        user_id=principal.user_id,
    )


def get_project_message_submission_service(
    conversation_repository: Annotated[
        ConversationRepository,
        Depends(get_conversation_repository),
    ],
    history_builder: Annotated[
        ProjectConversationHistoryBuilder,
        Depends(get_project_conversation_history_builder),
    ],
    project_document_service: Annotated[
        ProjectDocumentService,
        Depends(get_project_document_service),
    ],
    question_service: Annotated[
        QuestionAnsweringService,
        Depends(get_routed_question_answering_service),
    ],
    authorization_service: Annotated[
        AuthorizationService,
        Depends(get_authorization_service),
    ],
) -> ProjectMessageSubmissionService:
    return ProjectMessageSubmissionService(
        conversation_repository=conversation_repository,
        history_builder=history_builder,
        project_document_service=project_document_service,
        question_service=question_service,
        authorization_service=authorization_service,
    )


def get_project_workflow_status_service(
    workflow_repository: Annotated[
        WorkflowExecutionRepository,
        Depends(get_workflow_execution_repository),
    ],
    authorization_service: Annotated[
        AuthorizationService,
        Depends(get_authorization_service),
    ],
) -> ProjectWorkflowStatusService:
    return ProjectWorkflowStatusService(
        workflow_repository,
        authorization_service=authorization_service,
    )


def _get_qdrant_vector_store(
    settings: Settings,
    dimension: int,
) -> QdrantVectorStore:
    try:
        return QdrantVectorStore(settings=settings, dimension=dimension)
    except VectorStoreError as exc:
        if settings.QDRANT_URL is None or not settings.QDRANT_URL.strip():
            message = (
                "Question-answering service is unavailable because Qdrant is not "
                "configured. Set QDRANT_URL before retrying."
            )
        else:
            message = (
                "Question-answering service is unavailable because Qdrant is "
                "unavailable or misconfigured. Check Qdrant configuration before "
                "retrying."
            )
        raise QuestionAnsweringUnavailableError(message) from exc


def _build_document_indexer(
    settings: Settings,
    loader: DocumentLoader,
) -> DocumentIndexer:
    embedding_provider = OpenAIEmbeddingProvider(settings=settings)
    return DocumentIndexer(
        loader=loader,
        chunker=RecursiveTextChunker(
            chunk_size=settings.RAG_CHUNK_SIZE,
            chunk_overlap=settings.RAG_CHUNK_OVERLAP,
        ),
        embedding_provider=embedding_provider,
        vector_store=QdrantVectorStore(
            settings=settings,
            dimension=embedding_provider.dimension,
            wait=True,
        ),
    )


def _build_project_document_vector_store(settings: Settings) -> QdrantVectorStore:
    return QdrantVectorStore(
        settings=settings,
        dimension=settings.RAG_EMBEDDING_DIMENSION,
    )
