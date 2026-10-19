"""File guide.

- Use: Exports repository interfaces and implementations.
- Usage: Import from rastin_ai.repositories.__init__ to use the package API.
- Duties: Keeps package imports short and stable for other modules.
- Depends on: Project modules: rastin_ai.repositories.conversations,
  rastin_ai.repositories.documents, and rastin_ai.repositories.file_metadata.
"""

from rastin_ai.repositories.conversations import (
    ConversationDocumentReferenceCreate,
    ConversationDocumentReferenceRecord,
    ConversationMessageCreate,
    ConversationMessageRecord,
    ConversationRepository,
    ConversationSessionRecord,
    SQLAlchemyConversationRepository,
)
from rastin_ai.repositories.documents import (
    DocumentRepository,
    SQLAlchemyDocumentRepository,
    UploadedDocumentCreate,
    UploadedDocumentRecord,
)
from rastin_ai.repositories.file_metadata import (
    FileMetadataCreate,
    FileMetadataRecord,
    FileMetadataRepository,
    SQLAlchemyFileMetadataRepository,
)
from rastin_ai.repositories.organizations import (
    OrganizationCreate,
    OrganizationMemberRecord,
    OrganizationRecord,
    OrganizationRepository,
    RepositoryConflictError,
    SQLAlchemyOrganizationRepository,
)
from rastin_ai.repositories.project_documents import (
    ChatAttachmentCreate,
    ProjectDocumentCreate,
    ProjectDocumentRecord,
    ProjectDocumentRepository,
    SQLAlchemyProjectDocumentRepository,
)
from rastin_ai.repositories.projects import (
    ProjectAccessRecord,
    ProjectCreate,
    ProjectMemberRecord,
    ProjectRecord,
    ProjectRepository,
    SQLAlchemyProjectRepository,
)
from rastin_ai.repositories.users import (
    SQLAlchemyUserRepository,
    UserRecord,
    UserRepository,
)

__all__ = [
    "ConversationDocumentReferenceCreate",
    "ConversationDocumentReferenceRecord",
    "ConversationMessageCreate",
    "ConversationMessageRecord",
    "ConversationRepository",
    "ConversationSessionRecord",
    "DocumentRepository",
    "FileMetadataCreate",
    "FileMetadataRecord",
    "FileMetadataRepository",
    "OrganizationCreate",
    "OrganizationMemberRecord",
    "OrganizationRecord",
    "OrganizationRepository",
    "ProjectAccessRecord",
    "ProjectCreate",
    "ProjectDocumentCreate",
    "ProjectDocumentRecord",
    "ProjectDocumentRepository",
    "ProjectMemberRecord",
    "ProjectRecord",
    "ProjectRepository",
    "RepositoryConflictError",
    "SQLAlchemyProjectDocumentRepository",
    "SQLAlchemyDocumentRepository",
    "SQLAlchemyFileMetadataRepository",
    "SQLAlchemyOrganizationRepository",
    "SQLAlchemyProjectRepository",
    "SQLAlchemyConversationRepository",
    "SQLAlchemyUserRepository",
    "UserRecord",
    "UserRepository",
    "UploadedDocumentCreate",
    "UploadedDocumentRecord",
    "ChatAttachmentCreate",
]
