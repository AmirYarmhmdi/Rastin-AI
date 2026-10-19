export interface ApiErrorPayload {
  error?: {
    code?: string;
    message?: string;
    details?: Record<string, unknown> | null;
  };
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  created_by_user_id: string;
  created_at: string;
  updated_at: string;
}

export interface OrganizationListResponse {
  organizations: Organization[];
}

export interface OrganizationCreateRequest {
  name: string;
  slug?: string | null;
}

export interface Project {
  id: string;
  organization_id: string;
  name: string;
  description: string | null;
  created_by_user_id: string;
  effective_role: string;
  permissions: string[];
  created_at: string;
  updated_at: string;
}

export interface ProjectListResponse {
  projects: Project[];
}

export interface ProjectCreateRequest {
  name: string;
  description?: string | null;
}

export interface ProjectSessionSummary {
  id: string;
  title: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface ProjectSessionListResponse {
  sessions: ProjectSessionSummary[];
}

export interface ProjectMessage {
  id: string;
  role: string;
  sequence: number;
  content: string;
  workflow_id: string | null;
  status: string;
  error_message: string | null;
  citations: Record<string, unknown>[];
  sources: Record<string, unknown>[];
  document_references: Record<string, unknown>[];
  created_at: string;
}

export interface ProjectSession {
  id: string;
  title: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  messages: ProjectMessage[];
}

export interface AttachmentMetadata {
  document_id: string;
  filename: string;
  content_type: string | null;
  size_bytes: number;
  status: string;
}

export interface WorkflowDetail {
  label: string;
  status: string;
  summary: string | null;
}

export interface ProjectMessageSubmissionResponse {
  workflow_id: string | null;
  session_id: string;
  user_message: ProjectMessage;
  assistant_message: ProjectMessage;
  status: string;
  final_answer: string;
  attachments: AttachmentMetadata[];
  sources: Record<string, unknown>[];
  citations: Record<string, unknown>[];
  workflow_details: WorkflowDetail[];
}

export interface ProjectWorkflowStatusResponse {
  workflow_id: string;
  session_id: string;
  status: string;
  result: Record<string, unknown> | null;
  error: string | null;
  trace_id: string | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface ProjectDocument {
  document_id: string;
  file_metadata_id: string;
  organization_id: string;
  project_id: string;
  uploaded_by_user_id: string | null;
  filename: string;
  content_type: string | null;
  normalized_extension: string;
  size_bytes: number;
  checksum_sha256: string;
  document_scope: string;
  session_id: string | null;
  status: string;
  indexing_error_code: string | null;
  indexing_error_message: string | null;
  file_storage_status: string;
  created_at: string;
  updated_at: string;
}

export interface ProjectDocumentListResponse {
  documents: ProjectDocument[];
}
