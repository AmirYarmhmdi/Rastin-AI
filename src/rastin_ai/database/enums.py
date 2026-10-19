"""File guide.

- Use: Defines database status values shared by SQLAlchemy models.
- Usage: Import ConversationSessionStatus, DocumentStatus, FileStorageStatus, and
  WorkflowExecutionStatus from rastin_ai.database.enums.
- Duties: Defines ConversationSessionStatus, DocumentStatus, FileStorageStatus, and
  WorkflowExecutionStatus and related helper logic.
- Depends on: External packages only: enum.
"""

from enum import StrEnum


class ConversationSessionStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class ConversationMessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class ConversationMessageStatus(StrEnum):
    SUBMITTED = "submitted"
    ANSWERED = "answered"
    FAILED = "failed"


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    INDEXED = "indexed"
    FAILED = "failed"


class DocumentScope(StrEnum):
    LEGACY = "LEGACY"
    PROJECT_LIBRARY = "PROJECT_LIBRARY"
    CHAT_ATTACHMENT = "CHAT_ATTACHMENT"


class FileStorageStatus(StrEnum):
    STORED = "stored"
    FAILED = "failed"


class WorkflowExecutionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class OrganizationMemberRole(StrEnum):
    OWNER = "OWNER"
    MEMBER = "MEMBER"


class ProjectMemberRole(StrEnum):
    ADMIN = "ADMIN"
    MEMBER = "MEMBER"
    VIEWER = "VIEWER"
