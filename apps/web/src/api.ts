import type {
  ApiErrorPayload,
  Organization,
  OrganizationCreateRequest,
  OrganizationListResponse,
  Project,
  ProjectCreateRequest,
  ProjectDocument,
  ProjectDocumentListResponse,
  ProjectListResponse,
  ProjectMessageSubmissionResponse,
  ProjectSession,
  ProjectSessionListResponse,
  ProjectSessionSummary
} from "./types";

const JSON_HEADERS = { "Content-Type": "application/json" };

export class ApiError extends Error {
  status: number;
  code: string | null;
  details: Record<string, unknown> | null;

  constructor(
    message: string,
    options: {
      status: number;
      code?: string | null;
      details?: Record<string, unknown> | null;
    }
  ) {
    super(message);
    this.name = "ApiError";
    this.status = options.status;
    this.code = options.code ?? null;
    this.details = options.details ?? null;
  }
}

export async function listOrganizations(): Promise<Organization[]> {
  const response = await requestJson<OrganizationListResponse>(
    "/api/v1/organizations"
  );
  return response.organizations;
}

export async function createOrganization(
  request: OrganizationCreateRequest
): Promise<Organization> {
  return requestJson<Organization>("/api/v1/organizations", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(request)
  });
}

export async function listProjects(
  organizationId: string
): Promise<Project[]> {
  const response = await requestJson<ProjectListResponse>(
    `/api/v1/organizations/${organizationId}/projects`
  );
  return response.projects;
}

export async function createProject(
  organizationId: string,
  request: ProjectCreateRequest
): Promise<Project> {
  return requestJson<Project>(
    `/api/v1/organizations/${organizationId}/projects`,
    {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(request)
    }
  );
}

export async function listProjectSessions(
  projectId: string
): Promise<ProjectSessionSummary[]> {
  const response = await requestJson<ProjectSessionListResponse>(
    `/api/v1/projects/${projectId}/sessions`
  );
  return response.sessions;
}

export async function createProjectSession(
  projectId: string,
  title: string | null
): Promise<ProjectSessionSummary> {
  return requestJson<ProjectSessionSummary>(
    `/api/v1/projects/${projectId}/sessions`,
    {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ title })
    }
  );
}

export async function getProjectSession(
  projectId: string,
  sessionId: string
): Promise<ProjectSession> {
  return requestJson<ProjectSession>(
    `/api/v1/projects/${projectId}/sessions/${sessionId}`
  );
}

export async function submitProjectMessage(
  projectId: string,
  sessionId: string,
  message: string,
  files: File[]
): Promise<ProjectMessageSubmissionResponse> {
  const formData = new FormData();
  formData.append("message", message);
  for (const file of files) {
    formData.append("files", file);
  }

  return requestJson<ProjectMessageSubmissionResponse>(
    `/api/v1/projects/${projectId}/sessions/${sessionId}/messages`,
    {
      method: "POST",
      body: formData
    }
  );
}

export async function listProjectDocuments(
  projectId: string
): Promise<ProjectDocument[]> {
  const response = await requestJson<ProjectDocumentListResponse>(
    `/api/v1/projects/${projectId}/library/documents`
  );
  return response.documents;
}

export async function uploadProjectDocument(
  projectId: string,
  file: File
): Promise<ProjectDocument> {
  const formData = new FormData();
  formData.append("file", file);

  return requestJson<ProjectDocument>(
    `/api/v1/projects/${projectId}/library/documents`,
    {
      method: "POST",
      body: formData
    }
  );
}

export async function downloadProjectDocument(
  projectId: string,
  documentId: string
): Promise<Blob> {
  const response = await request(
    `/api/v1/projects/${projectId}/library/documents/${documentId}/download`
  );
  return response.blob();
}

export async function deleteProjectDocument(
  projectId: string,
  documentId: string
): Promise<void> {
  await request(
    `/api/v1/projects/${projectId}/library/documents/${documentId}`,
    { method: "DELETE" }
  );
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await request(path, init);
  return (await response.json()) as T;
}

async function request(path: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(path, init);
  if (response.ok) {
    return response;
  }

  let message = `Request failed with status ${response.status}.`;
  let code: string | null = null;
  let details: Record<string, unknown> | null = null;
  try {
    const payload = (await response.json()) as ApiErrorPayload;
    if (payload.error?.message) {
      message = payload.error.message;
    }
    code = payload.error?.code ?? null;
    details = payload.error?.details ?? null;
  } catch {
    // Keep the status-based fallback.
  }
  throw new ApiError(message, {
    status: response.status,
    code,
    details
  });
}
