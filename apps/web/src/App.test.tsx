import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";

const orgId = "11111111-1111-4111-8111-111111111111";
const projectId = "22222222-2222-4222-8222-222222222222";
const sessionId = "33333333-3333-4333-8333-333333333333";
const documentId = "44444444-4444-4444-8444-444444444444";
const uploadedDocumentId = "88888888-8888-4888-8888-888888888888";

const organization = {
  id: orgId,
  name: "Acme",
  slug: "acme",
  created_by_user_id: "99999999-9999-4999-8999-999999999999",
  created_at: "2026-08-11T12:00:00Z",
  updated_at: "2026-08-11T12:00:00Z"
};

const adminProject = {
  id: projectId,
  organization_id: orgId,
  name: "Alpha Project",
  description: "Project knowledge and private work.",
  created_by_user_id: "99999999-9999-4999-8999-999999999999",
  effective_role: "ADMIN",
  permissions: [
    "projects.read",
    "projects.manage_members",
    "documents.upload",
    "chats.create"
  ],
  created_at: "2026-08-11T12:00:00Z",
  updated_at: "2026-08-11T12:00:00Z"
};

const viewerProject = {
  ...adminProject,
  effective_role: "VIEWER",
  permissions: ["projects.read"]
};

const sessionSummary = {
  id: sessionId,
  title: null,
  status: "active",
  created_at: "2026-08-11T12:01:00Z",
  updated_at: "2026-08-11T12:03:00Z"
};

const sessionDetail = {
  ...sessionSummary,
  messages: [
    {
      id: "55555555-5555-4555-8555-555555555555",
      role: "user",
      sequence: 1,
      content: "What changed?",
      workflow_id: null,
      status: "completed",
      error_message: null,
      citations: [],
      sources: [],
      document_references: [],
      created_at: "2026-08-11T12:02:00Z"
    },
    {
      id: "66666666-6666-4666-8666-666666666666",
      role: "assistant",
      sequence: 2,
      content: "Budget review is complete.",
      workflow_id: "77777777-7777-4777-8777-777777777777",
      status: "completed",
      error_message: null,
      citations: [{ filename: "roadmap.md" }],
      sources: [{ source: "roadmap.md" }],
      document_references: [],
      created_at: "2026-08-11T12:03:00Z"
    }
  ]
};

const libraryDocument = {
  document_id: documentId,
  file_metadata_id: documentId,
  organization_id: orgId,
  project_id: projectId,
  uploaded_by_user_id: "99999999-9999-4999-8999-999999999999",
  filename: "roadmap.md",
  content_type: "text/markdown",
  normalized_extension: ".md",
  size_bytes: 12,
  checksum_sha256: "abc123",
  document_scope: "PROJECT_LIBRARY",
  session_id: null,
  status: "indexed",
  indexing_error_code: null,
  indexing_error_message: null,
  file_storage_status: "stored",
  created_at: "2026-08-11T12:00:00Z",
  updated_at: "2026-08-11T12:00:00Z"
};

describe("App", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.stubGlobal("URL", {
      createObjectURL: vi.fn(() => "blob:download"),
      revokeObjectURL: vi.fn()
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("loads organization, project, private chat, and project library without legacy routes", async () => {
    const fetchMock = installFetch();
    render(<App />);

    expect((await screen.findAllByText("Alpha Project")).length).toBeGreaterThan(0);
    expect(await screen.findByText("Budget review is complete.")).toBeInTheDocument();
    expect(screen.getAllByText("roadmap.md").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "New chat" })).toBeEnabled();
    expect(screen.getByText("documents.upload")).toBeInTheDocument();

    expectNoLegacyRoutes(fetchMock);
  });

  it("creates an organization and handles an empty project list", async () => {
    const fetchMock = installFetch({ emptyOrganizations: true });
    render(<App />);

    expect(await screen.findByText("Create an organization")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Organization name"), {
      target: { value: "New Org" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Create org" }));

    expect(
      await screen.findByText("This organization has no projects available to your account.")
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/organizations",
      expect.objectContaining({ method: "POST" })
    );
  });

  it("surfaces project creation permission errors without fake permission state", async () => {
    installFetch({ projectCreateForbidden: true });
    render(<App />);

    expect((await screen.findAllByText("Alpha Project")).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Switch project or workspace" }));
    fireEvent.click(screen.getByRole("button", { name: "New project" }));
    fireEvent.change(screen.getByLabelText("Project name"), {
      target: { value: "Restricted Project" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Create project" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Organization owner permissions are required."
    );
    expect(screen.getByLabelText("Project name")).toHaveValue(
      "Restricted Project"
    );
  });

  it("submits a project chat message with attachments to the project-scoped endpoint", async () => {
    const fetchMock = installFetch();
    render(<App />);

    expect((await screen.findAllByText("Alpha Project")).length).toBeGreaterThan(0);
    fireEvent.change(screen.getByLabelText("Message"), {
      target: { value: "Summarize the plan" }
    });
    fireEvent.change(screen.getByLabelText("Attach files"), {
      target: {
        files: [new File(["hello"], "notes.txt", { type: "text/plain" })]
      }
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText("Answer from project context.")).toBeInTheDocument();
    expect(screen.getByText("notes.txt")).toBeInTheDocument();
    expect(screen.queryByDisplayValue("Summarize the plan")).not.toBeInTheDocument();

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        `/api/v1/projects/${projectId}/sessions/${sessionId}/messages`,
        expect.objectContaining({ method: "POST" })
      );
    });
    expectNoLegacyRoutes(fetchMock);
  });

  it("preserves message draft and selected files after a recoverable send failure", async () => {
    installFetch({ messageFailure: true });
    render(<App />);

    expect((await screen.findAllByText("Alpha Project")).length).toBeGreaterThan(0);
    fireEvent.change(screen.getByLabelText("Message"), {
      target: { value: "Keep this draft" }
    });
    fireEvent.change(screen.getByLabelText("Attach files"), {
      target: {
        files: [new File(["hello"], "draft.txt", { type: "text/plain" })]
      }
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Question-answering service is unavailable."
    );
    expect(screen.getByLabelText("Message")).toHaveValue("Keep this draft");
    expect(screen.getByText("draft.txt (5 B)")).toBeInTheDocument();
  });

  it("renders viewer library access without chat or upload actions", async () => {
    const fetchMock = installFetch({ viewer: true });
    render(<App />);

    expect((await screen.findAllByText("Alpha Project")).length).toBeGreaterThan(0);
    expect(
      screen.getByText("Private chats are not available for this role.")
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New chat" })).toBeDisabled();
    expect(screen.getByText("Upload is not available for this project role.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete" })).toBeDisabled();
    expect(screen.getAllByText("roadmap.md").length).toBeGreaterThan(0);

    expect(fetchMock).not.toHaveBeenCalledWith(
      `/api/v1/projects/${projectId}/sessions`,
      expect.anything()
    );
    expectNoLegacyRoutes(fetchMock);
  });

  it("uploads and deletes project-library documents when project permissions allow it", async () => {
    const fetchMock = installFetch();
    render(<App />);

    expect((await screen.findAllByText("Alpha Project")).length).toBeGreaterThan(0);
    fireEvent.change(screen.getByLabelText("Upload file"), {
      target: {
        files: [new File(["new"], "brief.md", { type: "text/markdown" })]
      }
    });

    expect(await screen.findByText("brief.md")).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "Delete" })[0]);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        `/api/v1/projects/${projectId}/library/documents/${uploadedDocumentId}`,
        expect.objectContaining({ method: "DELETE" })
      );
    });
  });

  it("closes the workspace switcher with Escape and restores focus", async () => {
    installFetch();
    render(<App />);
    await screen.findByText("Budget review is complete.");
    const switcher = screen.getByRole("button", { name: "Switch project or workspace" });
    fireEvent.click(switcher);
    expect(switcher).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("button", { name: "Alpha Project" })).toHaveFocus();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(switcher).toHaveAttribute("aria-expanded", "false");
    expect(switcher).toHaveFocus();
    expect(screen.queryByRole("button", { name: "New workspace" })).not.toBeInTheDocument();
  });

  it("creates a project with the optional description through the existing API", async () => {
    const fetchMock = installFetch();
    render(<App />);
    await screen.findByText("Budget review is complete.");
    fireEvent.click(screen.getByRole("button", { name: "Switch project or workspace" }));
    fireEvent.click(screen.getByRole("button", { name: "New project" }));
    expect(screen.getByLabelText("Project name")).toHaveFocus();
    fireEvent.change(screen.getByLabelText("Project name"), { target: { value: "  Restricted Project  " } });
    fireEvent.click(screen.getByText("Add a description (optional)"));
    fireEvent.change(screen.getByLabelText("Project description"), { target: { value: "  Optional context  " } });
    fireEvent.click(screen.getByRole("button", { name: "Create project" }));
    await screen.findByRole("heading", { name: "Restricted Project" });
    expect(fetchMock).toHaveBeenCalledWith(`/api/v1/organizations/${orgId}/projects`, expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ name: "Restricted Project", description: "Optional context" })
    }));
    expect(screen.queryByLabelText("Project name")).not.toBeInTheDocument();
  });

  it("keeps the workspace creation screen and name after a recoverable failure", async () => {
    const fetchMock = installFetch({ emptyOrganizations: true });
    const originalFetch = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation(async (input, init) => {
      if (String(input) === "/api/v1/organizations" && init?.method === "POST") {
        return jsonResponse({ error: { message: "Workspace creation is unavailable." } }, 503);
      }
      return originalFetch(input, init);
    });
    render(<App />);
    const name = await screen.findByLabelText("Organization name");
    expect(name).toHaveFocus();
    fireEvent.change(name, { target: { value: "Keep this workspace name" } });
    fireEvent.click(screen.getByRole("button", { name: "Create org" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Workspace creation is unavailable.");
    expect(screen.getByLabelText("Organization name")).toHaveValue("Keep this workspace name");
    expect(screen.getByRole("button", { name: "Create org" })).toBeEnabled();
  });

  it("switches projects and workspaces using the existing stored selections and scoped requests", async () => {
    const otherOrg = { ...organization, id: "other-org", name: "Other workspace" };
    const otherProject = { ...adminProject, id: "other-project", name: "Other project" };
    const workspaceProject = { ...otherProject, id: "workspace-project", organization_id: otherOrg.id, name: "Workspace project" };
    const fetchMock = installFetch();
    const originalFetch = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation(async (input, init) => {
      const path = String(input);
      if (path === "/api/v1/organizations" && !init?.method) {
        return jsonResponse({ organizations: [organization, otherOrg] });
      }
      if (path === `/api/v1/organizations/${orgId}/projects` && !init?.method) {
        return jsonResponse({ projects: [adminProject, otherProject] });
      }
      if (path === `/api/v1/organizations/${otherOrg.id}/projects` && !init?.method) {
        return jsonResponse({ projects: [workspaceProject] });
      }
      if ([otherProject.id, workspaceProject.id].some((id) => path === `/api/v1/projects/${id}/sessions`)) {
        return jsonResponse({ sessions: [] });
      }
      if ([otherProject.id, workspaceProject.id].some((id) => path === `/api/v1/projects/${id}/library/documents`)) {
        return jsonResponse({ documents: [] });
      }
      return originalFetch(input, init);
    });
    render(<App />);
    await screen.findByText("Budget review is complete.");
    fireEvent.click(screen.getByRole("button", { name: "Switch project or workspace" }));
    fireEvent.click(screen.getByRole("button", { name: "Other project" }));
    await waitFor(() => {
      expect(window.localStorage.getItem("rastin_ai.selectedProjectId")).toBe(otherProject.id);
      expect(fetchMock).toHaveBeenCalledWith(`/api/v1/projects/${otherProject.id}/sessions`, undefined);
    });
    fireEvent.click(screen.getByRole("button", { name: "Switch project or workspace" }));
    fireEvent.click(screen.getByRole("button", { name: "Other workspace" }));
    await screen.findByRole("heading", { name: "Workspace project" });
    await waitFor(() => {
      expect(window.localStorage.getItem("rastin_ai.selectedOrganizationId")).toBe(otherOrg.id);
      expect(window.localStorage.getItem("rastin_ai.selectedProjectId")).toBe(workspaceProject.id);
      expect(fetchMock).toHaveBeenCalledWith(`/api/v1/projects/${workspaceProject.id}/library/documents`, undefined);
    });
    expectNoLegacyRoutes(fetchMock);
  });
});

function installFetch({
  emptyOrganizations = false,
  messageFailure = false,
  projectCreateForbidden = false,
  viewer = false
}: {
  emptyOrganizations?: boolean;
  messageFailure?: boolean;
  projectCreateForbidden?: boolean;
  viewer?: boolean;
} = {}) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    const method = init?.method ?? "GET";

    if (path === "/api/v1/organizations" && method === "GET") {
      return jsonResponse({
        organizations: emptyOrganizations ? [] : [organization]
      });
    }

    if (path === "/api/v1/organizations" && method === "POST") {
      return jsonResponse({ ...organization, id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", name: "New Org", slug: "new-org" }, 201);
    }

    if (path.endsWith("/projects") && method === "GET") {
      return jsonResponse({
        projects: emptyOrganizations ? [] : [viewer ? viewerProject : adminProject]
      });
    }

    if (path.endsWith("/projects") && method === "POST") {
      if (projectCreateForbidden) {
        return jsonResponse(
          {
            error: {
              code: "INSUFFICIENT_PERMISSIONS",
              message: "Organization owner permissions are required.",
              details: null
            }
          },
          403
        );
      }
      return jsonResponse(
        {
          ...adminProject,
          id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
          name: "Restricted Project"
        },
        201
      );
    }

    if (path === `/api/v1/projects/${projectId}/library/documents` && method === "GET") {
      return jsonResponse({ documents: [libraryDocument] });
    }

    if (path === `/api/v1/projects/${projectId}/library/documents` && method === "POST") {
      return jsonResponse(
        {
          ...libraryDocument,
          document_id: uploadedDocumentId,
          filename: "brief.md"
        },
        201
      );
    }

    if (path.startsWith(`/api/v1/projects/${projectId}/library/documents/`) && method === "DELETE") {
      return new Response(null, { status: 204 });
    }

    if (path === `/api/v1/projects/${projectId}/sessions` && method === "GET") {
      return jsonResponse({ sessions: [sessionSummary] });
    }

    if (path === `/api/v1/projects/${projectId}/sessions` && method === "POST") {
      return jsonResponse(sessionSummary, 201);
    }

    if (path === `/api/v1/projects/${projectId}/sessions/${sessionId}` && method === "GET") {
      return jsonResponse(sessionDetail);
    }

    if (path === `/api/v1/projects/${projectId}/sessions/${sessionId}/messages` && method === "POST") {
      if (messageFailure) {
        return jsonResponse(
          {
            error: {
              code: "QUESTION_ANSWERING_UNAVAILABLE",
              message: "Question-answering service is unavailable.",
              details: null
            }
          },
          503
        );
      }
      return jsonResponse({
        workflow_id: "77777777-7777-4777-8777-777777777777",
        session_id: sessionId,
        user_message: {
          id: "99999999-9999-4999-8999-999999999999",
          role: "user",
          sequence: 3,
          content: "Summarize the plan",
          workflow_id: null,
          status: "completed",
          error_message: null,
          citations: [],
          sources: [],
          document_references: [],
          created_at: "2026-08-11T12:04:00Z"
        },
        assistant_message: {
          id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
          role: "assistant",
          sequence: 4,
          content: "Answer from project context.",
          workflow_id: "77777777-7777-4777-8777-777777777777",
          status: "completed",
          error_message: null,
          citations: [{ filename: "roadmap.md" }],
          sources: [{ source: "roadmap.md" }],
          document_references: [],
          created_at: "2026-08-11T12:05:00Z"
        },
        status: "completed",
        final_answer: "Answer from project context.",
        attachments: [
          {
            document_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            filename: "notes.txt",
            content_type: "text/plain",
            size_bytes: 5,
            status: "stored"
          }
        ],
        sources: [{ source: "roadmap.md" }],
        citations: [{ filename: "roadmap.md" }],
        workflow_details: [
          {
            label: "Project retrieval",
            status: "completed",
            summary: "Used project library and chat attachments."
          }
        ]
      });
    }

    return jsonResponse({}, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" }
  });
}

function expectNoLegacyRoutes(fetchMock: ReturnType<typeof installFetch>) {
  const legacyPaths = [
    "/api/v1/messages",
    "/api/v1/questions",
    "/api/v1/documents",
    "/api/v1/sessions",
    "/api/v1/workflows"
  ];
  const calledPaths = fetchMock.mock.calls.map(([input]) => String(input));
  for (const path of legacyPaths) {
    expect(calledPaths).not.toContain(path);
  }
}
