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
  renameProjectSession,
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
  const [isLibraryOpen, setIsLibraryOpen] = useState(false);
  const libraryRef = useRef<HTMLDialogElement>(null);
  const filesButtonRef = useRef<HTMLButtonElement>(null);

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
    const dialog = libraryRef.current;
    if (isLibraryOpen && dialog) {
      dialog.showModal();
      dialog.querySelector<HTMLButtonElement>('[aria-label="Close project files"]')?.focus();
      return () => dialog.close();
    }
  }, [isLibraryOpen]);

  function closeLibrary() {
    libraryRef.current?.close();
    setIsLibraryOpen(false);
    filesButtonRef.current?.focus();
  }

  useEffect(() => {
    if (isNavigationOpen) {
      document.getElementById("project-navigation")?.querySelector<HTMLButtonElement>("button:not(:disabled)")?.focus();
    }
  }, [isNavigationOpen]);

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
      for (const file of files) {
        const uploaded = await uploadProjectDocument(selectedProject.id, file);
        setLibraryDocuments((current) => [uploaded, ...current]);
      }
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

  async function handleRenameSession(sessionId: string, title: string) {
    if (!selectedProject || !canChat) throw new Error("Choose a project where you can chat.");
    const saved = await renameProjectSession(selectedProject.id, sessionId, title);
    setSessions((current) => current.map((session) => session.id === saved.id ? saved : session));
    setSessionDetail((current) => current?.id === saved.id ? { ...current, ...saved } : current);
  }

  return (
    <main className="appShell">
      <aside id="project-navigation" className={`sidebar${isNavigationOpen ? " navigationOpen" : ""}`} aria-label="Project navigation">
        <header className="brandBlock">
          <img className="brandMark" src="/assets/rastin-lion.png" alt="" width="28" height="30" />
          <h1>Rastin-AI</h1>
        </header>

        <section className="privateChats" aria-label="Private chats">
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
          {selectedProject ? (
            <button className="filesButton" type="button" ref={filesButtonRef} aria-expanded={isLibraryOpen} aria-controls="project-files-drawer" aria-haspopup="dialog" onClick={() => setIsLibraryOpen(true)}>
              Files · {libraryDocuments.length}
            </button>
          ) : null}
        </header>

        <div className="contentGrid">
          <section className={`chatSurface${activeCreationScreen ? " setupSurface" : ""}`} aria-label="Selected private chat">
            <ErrorStack errors={[
              { message: appError, action: creationScreen === "organization" ? "Your workspace name is kept. Try Continue again, or ask your workspace owner for help." : "Reload this page to retry loading your workspaces." },
              { message: projectError, action: creationScreen === "project" ? "Your project details are kept. Try Continue again, or ask your workspace owner if access is denied." : "Choose a workspace again, or reload this page to retry loading its projects." },
              { message: chatError, action: "Try your chat action again. Your unsent text and selected attachments are kept here." }
            ]} />
            {isLoadingOrganizations ? <p className="muted" role="status">Loading workspaces...</p> : null}
            {isLoadingProjects ? <p className="muted" role="status">Loading projects...</p> : null}
            {activeCreationScreen ? (
              <div className="creationScreen">
                <img className="brandMark" src="/assets/rastin-lion.png" alt="" width="52" height="56" />
                <p className="eyebrow visuallyHidden">{activeCreationScreen === "organization" ? "Create an organization" : "Create a project"}</p>
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
                nextStep="Open Files to browse and download this project’s library."
              />
            ) : null}
            {!activeCreationScreen && selectedProject && canChat ? (
              <ChatThread
                isLoading={isLoadingSession || isLoadingSessions}
                session={sessionDetail}
                lastSubmission={lastSubmission}
                onRename={handleRenameSession}
              />
            ) : null}
          </section>

        </div>

        {!activeCreationScreen && selectedProject ? <div className="composerDock">
          {isSubmittingMessage ? <p className="answerPending" role="status">Working on your answer…</p> : null}
          {canChat ? <form className="composer" onSubmit={handleSubmitMessage}>
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
          </form> : <p className="viewOnly">View only. You can browse files but not chat.</p>}
        </div> : null}
      </section>
      {isLibraryOpen && selectedProject ? (
        <dialog id="project-files-drawer" className="filesDrawer" aria-label="Project Library" ref={libraryRef}
          onCancel={(event) => { event.preventDefault(); closeLibrary(); }}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              event.preventDefault();
              event.stopPropagation();
              closeLibrary();
            }
          }}
          onClick={(event) => { if (event.target === event.currentTarget) closeLibrary(); }}
        >
          <ProjectLibrary
            canDelete={canDeleteDocuments}
            canUpload={canUploadDocuments}
            documents={libraryDocuments}
            error={libraryError}
            isLoading={isLoadingLibrary}
            isUploading={isUploadingLibrary}
            onClose={closeLibrary}
            onDelete={(document) => void handleDeleteDocument(document)}
            onDownload={(document) => void handleDownloadDocument(document)}
            onRefresh={() => void refreshLibrary()}
            onUpload={handleLibraryUpload}
            projectSelected={Boolean(selectedProject)}
          />
        </dialog>
      ) : null}
    </main>
  );
}

function ChatThread({
  isLoading,
  lastSubmission,
  session,
  onRename
}: {
  isLoading: boolean;
  lastSubmission: ProjectMessageSubmissionResponse | null;
  session: ProjectSession | null;
  onRename: (sessionId: string, title: string) => Promise<void>;
}) {
  if (isLoading) {
    return <p className="muted" role="status">Loading chat...</p>;
  }

  if (!session) {
    return (
      <EmptyState
        title="What are we working on?"
        body="Send a message to start a private chat in this project."
        nextStep="Use Files to browse the project library, or attach files to your question."
      />
    );
  }

  return (
    <article className="thread">
      <header className="threadHeader">
        <div>
          <p className="eyebrow">Private chat</p>
          <ChatTitle key={session.id} session={session} onRename={onRename} />
        </div>
        <StatusPill status={lastSubmission?.status ?? session.status} />
      </header>
      <div className="messageList">
        {session.messages.length === 0 ? (
          <EmptyState title="What are we working on?" body="No messages in this chat yet." nextStep="Send a message or attach files to begin." />
        ) : null}
        {session.messages.map((item) => (
          <MessageBubble key={item.id} message={item} submission={
            lastSubmission?.session_id === session.id && lastSubmission.assistant_message.id === item.id
              ? lastSubmission
              : undefined
          } />
        ))}
      </div>
    </article>
  );
}

function ChatTitle({ session, onRename }: {
  session: ProjectSession;
  onRename: (sessionId: string, title: string) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const renameRef = useRef<HTMLButtonElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const wasEditing = useRef(false);
  useEffect(() => {
    if (editing) inputRef.current?.focus();
    else if (wasEditing.current) renameRef.current?.focus();
    wasEditing.current = editing;
  }, [editing]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving || !title.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await onRename(session.id, title.trim());
      setEditing(false);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setSaving(false);
    }
  }

  return <>
    <div className="chatTitleRow">
      <h3>{session.title || "Untitled chat"}</h3>
      {!editing ? <button className="renameChat" type="button" aria-label="Rename chat" ref={renameRef} onClick={() => {
        setTitle(session.title ?? "");
        setError(null);
        setEditing(true);
      }}>Rename</button> : null}
    </div>
    {editing ? <form className="renameForm" onSubmit={save} onKeyDown={(event) => {
      if (event.key === "Escape" && !saving) {
        event.preventDefault();
        event.stopPropagation();
        setEditing(false);
      }
    }}>
      <label className="visuallyHidden" htmlFor="chat-title">Chat title</label>
      <input id="chat-title" ref={inputRef} value={title} maxLength={255} disabled={saving} onChange={(event) => setTitle(event.target.value)} />
      <button type="submit" disabled={saving || !title.trim()}>{saving ? "Saving..." : "Save title"}</button>
      <button type="button" disabled={saving} onClick={() => setEditing(false)}>Cancel rename</button>
      {error ? <div className="errorBanner" role="alert">{error} The saved title could not be confirmed. Your edit is kept; retry Save title or reload to check.</div> : null}
    </form> : null}
  </>;
}

function MessageBubble({ message, submission }: { message: ProjectMessage; submission?: ProjectMessageSubmissionResponse }) {
  return (
    <section className={`messageBubble ${message.role}`}>
      <header>
        <strong>{message.role === "assistant" ? "Assistant" : "You"}</strong>
        <small>{message.status} · {formatDate(message.created_at)}</small>
      </header>
      <AnswerText content={message.content} animate={message.role === "assistant" && Boolean(submission)} />
      {message.error_message ? (
        <div className="errorBanner" role="alert">
          <p>{message.error_message}</p>
          <p className="errorHint">Try sending your question again. If it keeps failing, contact your workspace owner.</p>
        </div>
      ) : null}
      {message.role === "assistant" ? (
        <AnswerDetails
          attachments={submission?.attachments ?? []}
          citations={[...message.citations, ...(submission?.citations ?? [])]}
          sources={[...message.sources, ...(submission?.sources ?? [])]}
          workflowDetails={submission?.workflow_details ?? []}
          workflowId={message.workflow_id ?? submission?.workflow_id ?? null}
        />
      ) : null}
    </section>
  );
}

function AnswerText({ content, animate }: { content: string; animate: boolean }) {
  const textRef = useRef<HTMLParagraphElement>(null);
  const revealButtonRef = useRef<HTMLButtonElement>(null);
  const characters = useMemo(() => Array.from(content), [content]);
  const [visibleCount, setVisibleCount] = useState(
    () => animate && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === false ? 0 : characters.length
  );
  const [skipped, setSkipped] = useState(false);

  useEffect(() => {
    const preference = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    function finishReveal() {
      if (document.activeElement === revealButtonRef.current) textRef.current?.focus();
      setVisibleCount(characters.length);
    }
    if (!animate || skipped || !preference || preference.matches) {
      finishReveal();
      return;
    }
    let count = 0;
    setVisibleCount(0);
    const timer = window.setInterval(() => {
      count = Math.min(characters.length, count + Math.max(1, Math.ceil(characters.length / 75)));
      if (count === characters.length) {
        window.clearInterval(timer);
        finishReveal();
      } else {
        setVisibleCount(count);
      }
    }, 24);
    function respectReducedMotion(event: MediaQueryListEvent) {
      if (event.matches) {
        window.clearInterval(timer);
        finishReveal();
      }
    }
    preference.addEventListener("change", respectReducedMotion);
    return () => {
      window.clearInterval(timer);
      preference.removeEventListener("change", respectReducedMotion);
    };
  }, [animate, characters, skipped]);

  const revealing = visibleCount < characters.length;
  return (
    <div className="answerText">
      <p ref={textRef} tabIndex={animate ? -1 : undefined}>
        {revealing ? <span className="visuallyHidden">{content}</span> : null}
        <span aria-hidden={revealing || undefined}>{characters.slice(0, visibleCount).join("")}</span>
      </p>
      {revealing ? <button className="revealControl" ref={revealButtonRef} type="button" onClick={() => {
        setSkipped(true);
        textRef.current?.focus();
      }}>Show full answer</button> : null}
    </div>
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
    <details className="answerDetails">
      <summary>More details</summary>
      <div className="answerDetailsContent">
        <EvidenceList citations={citations} sources={sources} />
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
      </div>
    </details>
  );
}

function EvidenceList({
  citations,
  sources
}: {
  citations: Record<string, unknown>[];
  sources: Record<string, unknown>[];
}) {
  const documents = new Map<string, { label: string; locations: Set<string> }>();
  for (const evidence of [...citations, ...sources]) {
    const label = evidenceLabel(evidence);
    const key = typeof evidence.document_id === "string" && evidence.document_id.trim()
      ? `id:${evidence.document_id}`
      : `label:${label}`;
    const document = documents.get(key) ?? { label, locations: new Set<string>() };
    const location = evidenceLocation(evidence);
    if (location) document.locations.add(location);
    documents.set(key, document);
  }
  const uniqueDocuments = [...documents.entries()];
  return (
    <section className="evidenceBlock">
      <h4>Documents used</h4>
      {uniqueDocuments.length ? <ol className="evidenceDocuments">
        {uniqueDocuments.map(([key, document], index) => (
          <li key={key}><span className="referenceNumber">[{index + 1}]</span> {document.label}</li>
        ))}
      </ol> : <p>No document references were returned for this answer.</p>}
      {uniqueDocuments.length ? <>
        <h4>References</h4>
        <p>Retrieved passages supplied with this answer:</p>
        <ul className="evidenceReferences">
          {uniqueDocuments.flatMap(([key, document], index) => (
            [...(document.locations.size ? document.locations : ["Page and line details were not returned."])].map((location) => (
              <li key={`${key}-${location}`}><span className="referenceNumber">[{index + 1}]</span> {location}</li>
            ))
          ))}
        </ul>
      </> : null}
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
  onClose,
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
  onClose: () => void;
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
          <h3>Project files</h3>
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
        <button className="closeFilesButton" type="button" aria-label="Close project files" onClick={onClose}>×</button>
      </header>
      {error ? (
        <div className="errorBanner" role="alert">
          <p>{error}</p>
          <p className="errorHint">Refresh project files to check the latest state before trying again.</p>
        </div>
      ) : null}
      {!canUpload && projectSelected ? (
        <p className="muted">Upload is not available for this project role.</p>
      ) : null}
      {isLoading ? <p className="muted" role="status">Loading project files...</p> : null}
      {!isLoading && !error && documents.length === 0 ? (
        <div className="muted">
          <p>No project files yet.</p>
          <p>{canUpload ? "Upload a file to share it with this project." : "Ask a project member or admin to upload files, then choose Refresh."}</p>
        </div>
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
      <label className="fileButton fullWidth">
        {isUploading ? "Uploading..." : "Upload file"}
        <input
          aria-label="Upload file"
          multiple
          type="file"
          disabled={!projectSelected || !canUpload || isUploading}
          onChange={onUpload}
        />
      </label>
    </aside>
  );
}

function EmptyState({ body, title, nextStep }: { body: string; title: string; nextStep?: string }) {
  return (
    <div className="emptyState">
      <img className="brandMark" src="/assets/rastin-lion.png" alt="" width="56" height="60" />
      <h3>{title}</h3>
      <p>{body}</p>
      {nextStep ? <p>{nextStep}</p> : null}
    </div>
  );
}

function ErrorStack({ errors }: { errors: { message: string | null; action: string }[] }) {
  return (
    <>
      {errors.map(({ message, action }, index) => message ? (
        <div className="errorBanner" key={`${index}-${message}`} role="alert">
          <p>{message}</p>
          <p className="errorHint">{action}</p>
        </div>
      ) : null)}
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
  return "Document";
}

function evidenceLocation(value: Record<string, unknown>): string | null {
  const parts: string[] = [];
  function addRange(label: string, start: unknown, end?: unknown) {
    if (typeof start !== "number" || !Number.isFinite(start) || start < 0) return;
    const range = typeof end === "number" && Number.isFinite(end) && end > start;
    parts.push(`${label}${range ? "s" : ""} ${start}${range ? `–${end}` : ""}`);
  }
  if (typeof value.sheet_name === "string" && value.sheet_name.trim()) parts.push(`Sheet ${value.sheet_name}`);
  addRange("Page", value.page_number);
  addRange("Line", value.line_start, value.line_end);
  addRange("Paragraph", value.paragraph_index);
  addRange("Table", value.table_index);
  addRange("Row", value.row_start, value.row_end);
  if (typeof value.json_path === "string" && value.json_path.trim()) parts.push(`JSON ${value.json_path}`);
  if (parts.length) return parts.join(" · ");
  return typeof value.source_location === "string" && value.source_location.trim()
    ? value.source_location
    : null;
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
