import { ChangeEvent, FormEvent, useEffect, useMemo, useRef, useState } from "react";

import {
  createOrganization,
  createProject,
  createProjectSession,
  deleteProjectDocument,
  downloadProjectDocument,
  getProjectSession,
  listOrganizations,
  listProjectDocuments,
  listProjects,
  listProjectSessions,
  submitProjectMessage,
  uploadProjectDocument
} from "./api";
import type {
  AttachmentMetadata,
  Organization,
  Project,
  ProjectDocument,
  ProjectMessage,
  ProjectMessageSubmissionResponse,
  ProjectSession,
  ProjectSessionSummary,
  WorkflowDetail
} from "./types";

const ORG_SELECTION_KEY = "rastin_ai.selectedOrganizationId";
const PROJECT_SELECTION_KEY = "rastin_ai.selectedProjectId";
const SESSION_SELECTION_KEY = "rastin_ai.selectedSessionId";

function App() {
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [sessions, setSessions] = useState<ProjectSessionSummary[]>([]);
  const [libraryDocuments, setLibraryDocuments] = useState<ProjectDocument[]>([]);
  const [selectedOrganizationId, setSelectedOrganizationId] = useState<string | null>(
    null
  );
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [sessionDetail, setSessionDetail] = useState<ProjectSession | null>(null);
  const [lastSubmission, setLastSubmission] =
    useState<ProjectMessageSubmissionResponse | null>(null);
  const [message, setMessage] = useState("");
  const [messageFiles, setMessageFiles] = useState<File[]>([]);
  const [messageInputKey, setMessageInputKey] = useState(0);
  const [newOrganizationName, setNewOrganizationName] = useState("");
  const [newProjectName, setNewProjectName] = useState("");
  const [newProjectDescription, setNewProjectDescription] = useState("");
  const [isLoadingOrganizations, setIsLoadingOrganizations] = useState(true);
  const [isLoadingProjects, setIsLoadingProjects] = useState(false);
  const [isLoadingSessions, setIsLoadingSessions] = useState(false);
  const [isLoadingSession, setIsLoadingSession] = useState(false);
  const [isLoadingLibrary, setIsLoadingLibrary] = useState(false);
  const [isCreatingOrganization, setIsCreatingOrganization] = useState(false);
  const [isCreatingProject, setIsCreatingProject] = useState(false);
  const [isCreatingSession, setIsCreatingSession] = useState(false);
  const [isSubmittingMessage, setIsSubmittingMessage] = useState(false);
  const [isUploadingLibrary, setIsUploadingLibrary] = useState(false);
  const [appError, setAppError] = useState<string | null>(null);
  const [projectError, setProjectError] = useState<string | null>(null);
  const [chatError, setChatError] = useState<string | null>(null);
  const [libraryError, setLibraryError] = useState<string | null>(null);
  const [isSwitcherOpen, setIsSwitcherOpen] = useState(false);
  const [isNavigationOpen, setIsNavigationOpen] = useState(false);
  const [creationScreen, setCreationScreen] = useState<"organization" | "project" | null>(null);
  const switcherRef = useRef<HTMLDivElement>(null);
  const switcherButtonRef = useRef<HTMLButtonElement>(null);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const messageRef = useRef<HTMLTextAreaElement>(null);

  const selectedOrganization = useMemo(
    () =>
      organizations.find(
        (organization) => organization.id === selectedOrganizationId
      ) ?? null,
    [organizations, selectedOrganizationId]
  );
  const selectedProject = useMemo(
    () => projects.find((project) => project.id === selectedProjectId) ?? null,
    [projects, selectedProjectId]
  );
  const canChat = hasPermission(selectedProject, "chats.create");
  const canUploadDocuments = hasPermission(selectedProject, "documents.upload");
  const canDeleteDocuments = selectedProject?.effective_role === "ADMIN";
  const activeCreationScreen = creationScreen ?? (
    !isLoadingOrganizations && !selectedOrganization && !appError
      ? "organization"
      : selectedOrganization && !isLoadingProjects && !selectedProject && !projectError
        ? "project"
        : null
  );

  useEffect(() => {
    if (activeCreationScreen) {
      document.getElementById(`${activeCreationScreen}-name`)?.focus();
    }
  }, [activeCreationScreen]);

  useEffect(() => {
    const textarea = messageRef.current;
    if (textarea) {
      textarea.style.height = "auto";
      textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`;
    }
  }, [message, activeCreationScreen, canChat]);

  useEffect(() => {
    if (!isSwitcherOpen && !isNavigationOpen) {
      return;
    }
    if (isSwitcherOpen) {
      switcherRef.current?.querySelector<HTMLButtonElement>(".switcherPopover button")?.focus();
    }
    function handlePointer(event: PointerEvent) {
      if (!switcherRef.current?.contains(event.target as Node)) {
        setIsSwitcherOpen(false);
      }
    }
    function handleKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        if (isSwitcherOpen) {
          setIsSwitcherOpen(false);
          switcherButtonRef.current?.focus();
        } else {
          setIsNavigationOpen(false);
          menuButtonRef.current?.focus();
        }
      }
    }
    document.addEventListener("pointerdown", handlePointer);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("pointerdown", handlePointer);
      document.removeEventListener("keydown", handleKey);
    };
  }, [isSwitcherOpen, isNavigationOpen]);

  function closeNavigation() {
    setIsSwitcherOpen(false);
    setIsNavigationOpen(false);
    if (isNavigationOpen) {
      menuButtonRef.current?.focus();
    } else {
      switcherButtonRef.current?.focus();
    }
  }

  useEffect(() => {
    let isCurrent = true;
    async function load() {
      setIsLoadingOrganizations(true);
      setAppError(null);
      try {
        const loaded = await listOrganizations();
        if (!isCurrent) {
          return;
        }
        setOrganizations(loaded);
        setSelectedOrganizationId(validStoredId(ORG_SELECTION_KEY, loaded) ?? loaded[0]?.id ?? null);
      } catch (caught) {
        if (isCurrent) {
          setAppError(errorMessage(caught));
        }
      } finally {
        if (isCurrent) {
          setIsLoadingOrganizations(false);
        }
      }
    }
    void load();
    return () => {
      isCurrent = false;
    };
  }, []);

  useEffect(() => {
    if (selectedOrganizationId) {
      storeSelection(ORG_SELECTION_KEY, selectedOrganizationId);
    }
  }, [selectedOrganizationId]);

  useEffect(() => {
    if (!selectedOrganizationId) {
      setProjects([]);
      setSelectedProjectId(null);
      return;
    }

    const organizationId = selectedOrganizationId;
    let isCurrent = true;
    async function load() {
      setIsLoadingProjects(true);
      setProjectError(null);
      setProjects([]);
      setSelectedProjectId(null);
      setSessions([]);
      setSessionDetail(null);
      setSelectedSessionId(null);
      try {
        const loaded = await listProjects(organizationId);
        if (!isCurrent) {
          return;
        }
        setProjects(loaded);
        setSelectedProjectId(validStoredId(PROJECT_SELECTION_KEY, loaded) ?? loaded[0]?.id ?? null);
      } catch (caught) {
        if (isCurrent) {
          setProjectError(errorMessage(caught));
        }
      } finally {
        if (isCurrent) {
          setIsLoadingProjects(false);
        }
      }
    }
    void load();
    return () => {
      isCurrent = false;
    };
  }, [selectedOrganizationId]);

  useEffect(() => {
    if (selectedProjectId) {
      storeSelection(PROJECT_SELECTION_KEY, selectedProjectId);
    }
  }, [selectedProjectId]);

  useEffect(() => {
    if (!selectedProject) {
      setSessions([]);
      setLibraryDocuments([]);
      setSessionDetail(null);
      setSelectedSessionId(null);
      return;
    }

    const projectId = selectedProject.id;
    void refreshLibrary(projectId);
    if (!canChat) {
      setSessions([]);
      setSessionDetail(null);
      setSelectedSessionId(null);
      return;
    }

    let isCurrent = true;
    async function load() {
      setIsLoadingSessions(true);
      setChatError(null);
      setSessions([]);
      setSessionDetail(null);
      setSelectedSessionId(null);
      try {
        const loaded = await listProjectSessions(projectId);
        if (!isCurrent) {
          return;
        }
        setSessions(loaded);
        setSelectedSessionId(validStoredId(SESSION_SELECTION_KEY, loaded) ?? loaded[0]?.id ?? null);
      } catch (caught) {
        if (isCurrent) {
          setChatError(errorMessage(caught));
        }
      } finally {
        if (isCurrent) {
          setIsLoadingSessions(false);
        }
      }
    }
    void load();
    return () => {
      isCurrent = false;
    };
  }, [selectedProject, canChat]);

  useEffect(() => {
    if (selectedSessionId) {
      storeSelection(SESSION_SELECTION_KEY, selectedSessionId);
    }
  }, [selectedSessionId]);

  useEffect(() => {
    if (!selectedProject || !selectedSessionId || !canChat) {
      setSessionDetail(null);
      return;
    }

    const projectId = selectedProject.id;
    const sessionId = selectedSessionId;
    let isCurrent = true;
    async function load() {
      setIsLoadingSession(true);
      setChatError(null);
      try {
        const detail = await getProjectSession(projectId, sessionId);
        if (isCurrent) {
          setSessionDetail(detail);
        }
      } catch (caught) {
        if (isCurrent) {
          setChatError(errorMessage(caught));
        }
      } finally {
        if (isCurrent) {
          setIsLoadingSession(false);
        }
      }
    }
    void load();
    return () => {
      isCurrent = false;
    };
  }, [selectedProject, selectedSessionId, canChat]);

  async function refreshLibrary(projectId = selectedProject?.id) {
    if (!projectId) {
      return;
    }
    setIsLoadingLibrary(true);
    setLibraryError(null);
    try {
      setLibraryDocuments(await listProjectDocuments(projectId));
    } catch (caught) {
      setLibraryError(errorMessage(caught));
    } finally {
      setIsLoadingLibrary(false);
    }
  }

  async function handleCreateOrganization(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = newOrganizationName.trim();
    if (!name || isCreatingOrganization) {
      return;
    }
    setIsCreatingOrganization(true);
    setCreationScreen("organization");
    setAppError(null);
    try {
      const organization = await createOrganization({ name });
      setOrganizations((current) => [...current, organization]);
      setSelectedOrganizationId(organization.id);
      setNewOrganizationName("");
      setCreationScreen(null);
    } catch (caught) {
      setAppError(errorMessage(caught));
    } finally {
      setIsCreatingOrganization(false);
    }
  }

  async function handleCreateProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedOrganization) {
      return;
    }
    const name = newProjectName.trim();
    if (!name || isCreatingProject) {
      return;
    }
    setIsCreatingProject(true);
    setCreationScreen("project");
    setProjectError(null);
    try {
      const project = await createProject(selectedOrganization.id, {
        name,
        description: newProjectDescription.trim() || null
      });
      setProjects((current) => [...current, project]);
      setSelectedProjectId(project.id);
      setNewProjectName("");
      setNewProjectDescription("");
      setCreationScreen(null);
    } catch (caught) {
      setProjectError(errorMessage(caught));
    } finally {
      setIsCreatingProject(false);
    }
  }

  async function handleCreateSession() {
    if (!selectedProject || isCreatingSession) {
      return;
    }
    setIsCreatingSession(true);
    setChatError(null);
    try {
      const session = await createProjectSession(selectedProject.id, null);
      setSessions((current) => [session, ...current]);
      setSelectedSessionId(session.id);
      setSessionDetail({
        ...session,
        messages: []
      });
      setLastSubmission(null);
    } catch (caught) {
      setChatError(errorMessage(caught));
    } finally {
      setIsCreatingSession(false);
    }
  }

  async function handleSubmitMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProject || !canChat || isSubmittingMessage) {
      return;
    }
    const trimmed = message.trim();
    if (!trimmed) {
      return;
    }

    setIsSubmittingMessage(true);
    setChatError(null);
    try {
      let sessionId = selectedSessionId;
      let createdSession: ProjectSessionSummary | null = null;
      if (!sessionId) {
        createdSession = await createProjectSession(selectedProject.id, null);
        sessionId = createdSession.id;
        setSessions((current) => [createdSession as ProjectSessionSummary, ...current]);
        setSelectedSessionId(sessionId);
      }

      const result = await submitProjectMessage(
        selectedProject.id,
        sessionId,
        trimmed,
        messageFiles
      );
      setLastSubmission(result);
      setSessionDetail((current) => mergeSubmissionIntoSession(current, createdSession, result));
      setMessage("");
      setMessageFiles([]);
      setMessageInputKey((current) => current + 1);
      void reloadSessions(selectedProject.id, result.session_id);
    } catch (caught) {
      setChatError(errorMessage(caught));
    } finally {
      setIsSubmittingMessage(false);
    }
  }

  async function reloadSessions(projectId: string, selectedId: string) {
    try {
      const loaded = await listProjectSessions(projectId);
      setSessions(loaded);
      setSelectedSessionId(selectedId);
    } catch {
      // The submitted answer is already visible; keep the refresh failure non-fatal.
    }
  }

  async function handleLibraryUpload(event: ChangeEvent<HTMLInputElement>) {
    if (!selectedProject) {
      return;
    }
    const files = Array.from(event.target.files ?? []);
    if (!files.length) {
      return;
    }
    setIsUploadingLibrary(true);
    setLibraryError(null);
    try {
      const uploaded: ProjectDocument[] = [];
      for (const file of files) {
        uploaded.push(await uploadProjectDocument(selectedProject.id, file));
      }
      setLibraryDocuments((current) => [...uploaded, ...current]);
    } catch (caught) {
      setLibraryError(errorMessage(caught));
    } finally {
      setIsUploadingLibrary(false);
      event.target.value = "";
    }
  }

  async function handleDownloadDocument(document: ProjectDocument) {
    if (!selectedProject) {
      return;
    }
    setLibraryError(null);
    try {
      const blob = await downloadProjectDocument(
        selectedProject.id,
        document.document_id
      );
      const url = URL.createObjectURL(blob);
      const link = window.document.createElement("a");
      link.href = url;
      link.download = document.filename;
      link.click();
      URL.revokeObjectURL(url);
    } catch (caught) {
      setLibraryError(errorMessage(caught));
    }
  }

  async function handleDeleteDocument(document: ProjectDocument) {
    if (!selectedProject) {
      return;
    }
    setLibraryError(null);
    try {
      await deleteProjectDocument(selectedProject.id, document.document_id);
      setLibraryDocuments((current) =>
        current.filter((item) => item.document_id !== document.document_id)
      );
    } catch (caught) {
      setLibraryError(errorMessage(caught));
    }
  }

  return (
    <main className="appShell">
      <aside id="project-navigation" className={`sidebar${isNavigationOpen ? " navigationOpen" : ""}`} aria-label="Project navigation">
        <header className="brandBlock">
          <img className="brandMark" src="/assets/rastin-lion.png" alt="" width="28" height="31" />
          <h1>Rastin-AI</h1>
        </header>

        <section className="stack grow" aria-label="Private chats">
          <div className="sectionHeader">
            <h2 className="visuallyHidden">Private chats</h2>
            {isLoadingSessions ? <span>Loading</span> : null}
          </div>
          <button
            className="newChatButton"
            aria-label="New chat"
            disabled={!selectedProject || !canChat || isCreatingSession}
            type="button"
            onClick={() => {
              setCreationScreen(null);
              closeNavigation();
              void handleCreateSession();
            }}
          >
            {isCreatingSession ? "Creating..." : "New chat"}
          </button>
          <div className="itemList" aria-live="polite">
            {!selectedProject ? <p className="muted">Select a project.</p> : null}
            {selectedProject && !canChat ? (
              <p className="muted">Private chats are not available for this role.</p>
            ) : null}
            {selectedProject && canChat && !isLoadingSessions && sessions.length === 0 ? (
              <p className="muted">No private chats yet.</p>
            ) : null}
            {sessions.map((session) => (
              <button
                className={
                  session.id === selectedSessionId ? "itemButton selected" : "itemButton"
                }
                key={session.id}
                aria-current={session.id === selectedSessionId ? "page" : undefined}
                type="button"
                onClick={() => {
                  setCreationScreen(null);
                  closeNavigation();
                  setSelectedSessionId(session.id);
                  setLastSubmission(null);
                }}
              >
                <span>{session.title || "Untitled chat"}</span>
                <small>{session.status} · {formatDate(session.updated_at)}</small>
              </button>
            ))}
          </div>
        </section>
        <div className="workspaceSwitcher" ref={switcherRef} onBlur={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
            setIsSwitcherOpen(false);
          }
        }}>
          <button
            className="switcherButton"
            type="button"
            ref={switcherButtonRef}
            aria-label="Switch project or workspace"
            aria-expanded={isSwitcherOpen}
            aria-controls="workspace-switcher"
            onClick={() => setIsSwitcherOpen((current) => !current)}
          >
            <span>
              <strong>{selectedProject?.name || "No project"}</strong>
              <small>{selectedOrganization?.name || "No workspace"}</small>
            </span>
            <span aria-hidden="true">⌃</span>
          </button>
          {isSwitcherOpen ? (
            <div id="workspace-switcher" className="switcherPopover">
              <section aria-label="Project selector">
                <h2>Projects{selectedOrganization ? ` in ${selectedOrganization.name}` : ""}</h2>
                {isLoadingProjects ? <p className="muted" role="status">Loading projects...</p> : null}
                <div role="group" aria-label="Current project">
                  {projects.map((project) => (
                    <button
                      key={project.id}
                      type="button"
                      aria-current={project.id === selectedProjectId ? "true" : undefined}
                      onClick={() => {
                        setSelectedProjectId(project.id);
                        setCreationScreen(null);
                        closeNavigation();
                      }}
                    >
                      {project.name}
                    </button>
                  ))}
                </div>
                <button type="button" disabled={!selectedOrganization} onClick={() => {
                  setCreationScreen("project");
                  closeNavigation();
                }}>New project</button>
              </section>
              <section aria-label="Organization selector">
                <h2>Workspaces</h2>
                {isLoadingOrganizations ? <p className="muted" role="status">Loading workspaces...</p> : null}
                <div role="group" aria-label="Current organization">
                  {organizations.map((organization) => (
                    <button
                      key={organization.id}
                      type="button"
                      aria-current={organization.id === selectedOrganizationId ? "true" : undefined}
                      onClick={() => {
                        setSelectedOrganizationId(organization.id);
                        setCreationScreen(null);
                        closeNavigation();
                      }}
                    >
                      {organization.name}
                    </button>
                  ))}
                </div>
                <button type="button" onClick={() => {
                  setCreationScreen("organization");
                  closeNavigation();
                }}>New workspace</button>
              </section>
            </div>
          ) : null}
        </div>
      </aside>
      {isNavigationOpen ? <button className="navigationScrim" type="button" aria-label="Close navigation" onClick={() => {
        closeNavigation();
        menuButtonRef.current?.focus();
      }} /> : null}

      <section className="workspace" aria-label="Project workspace">
        <header className="workspaceHeader">
          <button className="menuButton" type="button" ref={menuButtonRef} aria-label="Menu" aria-expanded={isNavigationOpen} aria-controls="project-navigation" onClick={() => setIsNavigationOpen((current) => !current)}>☰</button>
          <h2>{selectedProject?.name || "Rastin-AI"}</h2>
          {selectedProject ? (
            <details className="projectContext">
              <summary>{selectedProject.effective_role}</summary>
              <div className="projectContextContent">
                {selectedProject.description ? <p>{selectedProject.description}</p> : null}
                <div className="permissionLine" aria-label="Project permissions">
                  {selectedProject.permissions.map((permission) => (
                    <span key={permission}>{permission}</span>
                  ))}
                </div>
              </div>
            </details>
          ) : null}
        </header>

        <div className="contentGrid">
          <section className={`chatSurface${activeCreationScreen ? " setupSurface" : ""}`} aria-label="Selected private chat">
            <ErrorStack errors={[appError, projectError, chatError]} />
            {activeCreationScreen ? (
              <div className="creationScreen">
                <img className="brandMark" src="/assets/rastin-lion.png" alt="" width="52" height="58" />
                <p className="eyebrow">{activeCreationScreen === "organization" ? "Create an organization" : "Create a project"}</p>
                <h2>{activeCreationScreen === "organization" ? "Name your workspace" : "Name your project"}</h2>
                <p>{activeCreationScreen === "organization" ? "Your team’s home for projects and shared files." : "Each project has its own files and private chats."}</p>
                {activeCreationScreen === "organization" ? (
                  <form className="creationForm" onSubmit={handleCreateOrganization}>
                    <label className="visuallyHidden" htmlFor="organization-name">Organization name</label>
                    <input
                      id="organization-name"
                      value={newOrganizationName}
                      onChange={(event) => setNewOrganizationName(event.target.value)}
                      placeholder="Workspace name"
                      autoComplete="organization"
                      disabled={isCreatingOrganization}
                    />
                    <button className="primaryButton" aria-label="Create org" disabled={!newOrganizationName.trim() || isCreatingOrganization} type="submit">
                      {isCreatingOrganization ? "Creating..." : "Continue"}
                    </button>
                  </form>
                ) : (
                  <form className="creationForm" onSubmit={handleCreateProject}>
                    <label className="visuallyHidden" htmlFor="project-name">Project name</label>
                    <input
                      id="project-name"
                      value={newProjectName}
                      onChange={(event) => setNewProjectName(event.target.value)}
                      placeholder="Project name"
                      disabled={!selectedOrganization || isCreatingProject}
                    />
                    <button className="primaryButton" aria-label="Create project" disabled={!selectedOrganization || !newProjectName.trim() || isCreatingProject} type="submit">
                      {isCreatingProject ? "Creating..." : "Continue"}
                    </button>
                    <details className="creationDetails">
                      <summary>Add a description (optional)</summary>
                      <label htmlFor="project-description">Project description</label>
                      <input
                        id="project-description"
                        value={newProjectDescription}
                        onChange={(event) => setNewProjectDescription(event.target.value)}
                        placeholder="Optional"
                        disabled={!selectedOrganization || isCreatingProject}
                      />
                    </details>
                  </form>
                )}
                {activeCreationScreen === "project" && projects.length === 0 ? (
                  <p>This organization has no projects available to your account.</p>
                ) : null}
                {creationScreen && selectedProject ? (
                  <button className="cancelCreation" type="button" disabled={isCreatingOrganization || isCreatingProject} onClick={() => setCreationScreen(null)}>Cancel</button>
                ) : null}
              </div>
            ) : null}
            {!activeCreationScreen && selectedProject && !canChat ? (
              <EmptyState
                title="Project library access"
                body="Your current project role can read project files, but cannot create or continue private chats."
              />
            ) : null}
            {!activeCreationScreen && selectedProject && canChat ? (
              <ChatThread
                isLoading={isLoadingSession}
                session={sessionDetail}
                lastSubmission={lastSubmission}
              />
            ) : null}
          </section>

          {!activeCreationScreen ? <ProjectLibrary
            canDelete={canDeleteDocuments}
            canUpload={canUploadDocuments}
            documents={libraryDocuments}
            error={libraryError}
            isLoading={isLoadingLibrary}
            isUploading={isUploadingLibrary}
            onDelete={(document) => void handleDeleteDocument(document)}
            onDownload={(document) => void handleDownloadDocument(document)}
            onRefresh={() => void refreshLibrary()}
            onUpload={handleLibraryUpload}
            projectSelected={Boolean(selectedProject)}
          /> : null}
        </div>

        {!activeCreationScreen ? <div className="composerDock">
          <form className="composer" onSubmit={handleSubmitMessage}>
            <label className="visuallyHidden" htmlFor="message">Message</label>
            <div className="pendingFiles" aria-live="polite">
              {messageFiles.map((file) => (
                <span key={`${file.name}-${file.size}`}>
                  {file.name} ({formatBytes(file.size)})
                </span>
              ))}
            </div>
            <label className="fileButton attachButton" title="Attach files">
              <span aria-hidden="true">+</span>
              <input
                key={messageInputKey}
                aria-label="Attach files"
                multiple
                type="file"
                disabled={!selectedProject || !canChat || isSubmittingMessage}
                onChange={(event) =>
                  setMessageFiles(Array.from(event.target.files ?? []))
                }
              />
            </label>
            <textarea
              id="message"
              ref={messageRef}
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              placeholder={canChat ? "Message Rastin-AI" : "Private chat is unavailable for this project role."}
              rows={1}
              disabled={!selectedProject || !canChat || isSubmittingMessage}
            />
            <button
              className="sendButton"
              aria-label="Send"
              title="Send"
              disabled={!selectedProject || !canChat || !message.trim() || isSubmittingMessage}
              type="submit"
            >
              <span aria-hidden="true">{isSubmittingMessage ? "…" : "↑"}</span>
            </button>
            <span className="visuallyHidden" role="status">{isSubmittingMessage ? "Sending..." : ""}</span>
          </form>
        </div> : null}
      </section>
    </main>
  );
}

function SelectField({
  disabled,
  label,
  onChange,
  options,
  value
}: {
  disabled: boolean;
  label: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
  value: string;
}) {
  return (
    <label className="selectField">
      <span>{label}</span>
      <select
        disabled={disabled}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">None</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function ChatThread({
  isLoading,
  lastSubmission,
  session
}: {
  isLoading: boolean;
  lastSubmission: ProjectMessageSubmissionResponse | null;
  session: ProjectSession | null;
}) {
  if (isLoading) {
    return <p className="muted">Loading chat...</p>;
  }

  if (!session) {
    return (
      <EmptyState
        title="Start a private chat"
        body="Create or send a message to start a chat scoped to this project."
      />
    );
  }

  return (
    <article className="thread">
      <header className="threadHeader">
        <div>
          <p className="eyebrow">Private chat</p>
          <h3>{session.title || "Untitled chat"}</h3>
        </div>
        <StatusPill status={lastSubmission?.status ?? session.status} />
      </header>
      <div className="messageList">
        {session.messages.length === 0 ? (
          <p className="muted">No messages in this chat yet.</p>
        ) : null}
        {session.messages.map((item) => (
          <MessageBubble key={item.id} message={item} />
        ))}
      </div>
      {lastSubmission ? (
        <AnswerDetails
          attachments={lastSubmission.attachments}
          citations={lastSubmission.citations}
          sources={lastSubmission.sources}
          workflowDetails={lastSubmission.workflow_details}
          workflowId={lastSubmission.workflow_id}
        />
      ) : null}
    </article>
  );
}

function MessageBubble({ message }: { message: ProjectMessage }) {
  return (
    <section className={`messageBubble ${message.role}`}>
      <header>
        <strong>{message.role === "assistant" ? "Assistant" : "You"}</strong>
        <small>{message.status} · {formatDate(message.created_at)}</small>
      </header>
      <p>{message.content}</p>
      {message.error_message ? (
        <div className="errorBanner" role="alert">
          {message.error_message}
        </div>
      ) : null}
      {message.citations.length || message.sources.length ? (
        <EvidenceList citations={message.citations} sources={message.sources} />
      ) : null}
    </section>
  );
}

function AnswerDetails({
  attachments,
  citations,
  sources,
  workflowDetails,
  workflowId
}: {
  attachments: AttachmentMetadata[];
  citations: Record<string, unknown>[];
  sources: Record<string, unknown>[];
  workflowDetails: WorkflowDetail[];
  workflowId: string | null;
}) {
  return (
    <aside className="answerDetails" aria-label="Latest answer details">
      {workflowId ? <p className="identifier">Workflow {workflowId}</p> : null}
      {attachments.length ? (
        <section>
          <h4>Attachments</h4>
          <ul className="compactList">
            {attachments.map((attachment) => (
              <li key={attachment.document_id}>
                <span>{attachment.filename}</span>
                <small>
                  {attachment.content_type || "unknown type"} ·{" "}
                  {formatBytes(attachment.size_bytes)} · {attachment.status}
                </small>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {citations.length || sources.length ? (
        <EvidenceList citations={citations} sources={sources} />
      ) : null}
      {workflowDetails.length ? (
        <details className="workflowDetails">
          <summary>Workflow details</summary>
          <ol>
            {workflowDetails.map((detail, index) => (
              <li key={`${detail.label}-${index}`}>
                <strong>{detail.label}</strong>
                <span>{detail.status}</span>
                {detail.summary ? <p>{detail.summary}</p> : null}
              </li>
            ))}
          </ol>
        </details>
      ) : null}
    </aside>
  );
}

function EvidenceList({
  citations,
  sources
}: {
  citations: Record<string, unknown>[];
  sources: Record<string, unknown>[];
}) {
  return (
    <section className="evidenceBlock">
      {citations.length ? (
        <>
          <h4>Citations</h4>
          <ul className="compactList">
            {citations.map((citation, index) => (
              <li key={`citation-${index}`}>{evidenceLabel(citation)}</li>
            ))}
          </ul>
        </>
      ) : null}
      {sources.length ? (
        <>
          <h4>Sources</h4>
          <ul className="compactList">
            {sources.map((source, index) => (
              <li key={`source-${index}`}>{evidenceLabel(source)}</li>
            ))}
          </ul>
        </>
      ) : null}
    </section>
  );
}

function ProjectLibrary({
  canDelete,
  canUpload,
  documents,
  error,
  isLoading,
  isUploading,
  onDelete,
  onDownload,
  onRefresh,
  onUpload,
  projectSelected
}: {
  canDelete: boolean;
  canUpload: boolean;
  documents: ProjectDocument[];
  error: string | null;
  isLoading: boolean;
  isUploading: boolean;
  onDelete: (document: ProjectDocument) => void;
  onDownload: (document: ProjectDocument) => void;
  onRefresh: () => void;
  onUpload: (event: ChangeEvent<HTMLInputElement>) => void;
  projectSelected: boolean;
}) {
  return (
    <aside className="libraryPanel" aria-label="Project files">
      <header className="panelHeader">
        <div>
          <p className="eyebrow">Project files</p>
          <h3>Library</h3>
        </div>
        <button
          className="iconButton"
          disabled={!projectSelected || isLoading}
          type="button"
          onClick={onRefresh}
          aria-label="Refresh project files"
          title="Refresh project files"
        >
          Refresh
        </button>
      </header>
      {error ? (
        <div className="errorBanner" role="alert">
          {error}
        </div>
      ) : null}
      <label className="fileButton fullWidth">
        {isUploading ? "Uploading..." : "Upload file"}
        <input
          multiple
          type="file"
          disabled={!projectSelected || !canUpload || isUploading}
          onChange={onUpload}
        />
      </label>
      {!canUpload && projectSelected ? (
        <p className="muted">Upload is not available for this project role.</p>
      ) : null}
      {isLoading ? <p className="muted">Loading project files...</p> : null}
      {!isLoading && documents.length === 0 ? (
        <p className="muted">No project files yet.</p>
      ) : null}
      <ul className="documentList">
        {documents.map((document) => (
          <li key={document.document_id}>
            <div>
              <strong>{document.filename}</strong>
              <small>
                {document.document_scope} · {document.status} ·{" "}
                {formatBytes(document.size_bytes)}
              </small>
              {document.indexing_error_message ? (
                <small className="dangerText">{document.indexing_error_message}</small>
              ) : null}
            </div>
            <div className="documentActions">
              <button type="button" onClick={() => onDownload(document)}>
                Download
              </button>
              <button
                disabled={!canDelete}
                type="button"
                onClick={() => onDelete(document)}
              >
                Delete
              </button>
            </div>
          </li>
        ))}
      </ul>
    </aside>
  );
}

function EmptyState({ body, title }: { body: string; title: string }) {
  return (
    <div className="emptyState">
      <h3>{title}</h3>
      <p>{body}</p>
    </div>
  );
}

function ErrorStack({ errors }: { errors: (string | null)[] }) {
  return (
    <>
      {errors.filter(Boolean).map((error) => (
        <div className="errorBanner" key={error} role="alert">
          {error}
        </div>
      ))}
    </>
  );
}

function StatusPill({ status }: { status: string }) {
  return <span className={`status status-${status}`}>{status}</span>;
}

function mergeSubmissionIntoSession(
  current: ProjectSession | null,
  createdSession: ProjectSessionSummary | null,
  result: ProjectMessageSubmissionResponse
): ProjectSession {
  const base: ProjectSession = current ?? {
    id: result.session_id,
    title: createdSession?.title ?? null,
    status: createdSession?.status ?? result.status,
    created_at: createdSession?.created_at ?? result.user_message.created_at,
    updated_at: result.assistant_message.created_at,
    messages: []
  };
  const previousMessages = base.messages.filter(
    (message) =>
      message.id !== result.user_message.id &&
      message.id !== result.assistant_message.id
  );
  return {
    ...base,
    status: result.status,
    updated_at: result.assistant_message.created_at,
    messages: [
      ...previousMessages,
      result.user_message,
      result.assistant_message
    ].sort((left, right) => left.sequence - right.sequence)
  };
}

function hasPermission(project: Project | null, permission: string): boolean {
  return Boolean(project?.permissions.includes(permission));
}

function validStoredId<T extends { id: string }>(
  key: string,
  records: T[]
): string | null {
  const stored = readSelection(key);
  return stored && records.some((record) => record.id === stored) ? stored : null;
}

function readSelection(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function storeSelection(key: string, value: string) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Browser storage is only a convenience.
  }
}

function evidenceLabel(value: Record<string, unknown>): string {
  for (const key of ["filename", "source", "title", "document_id"]) {
    const candidate = value[key];
    if (typeof candidate === "string" && candidate.trim()) {
      return candidate;
    }
  }
  return JSON.stringify(value);
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}

function formatBytes(value: number): string {
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function errorMessage(caught: unknown): string {
  return caught instanceof Error ? caught.message : "Unexpected request failure.";
}

export default App;
