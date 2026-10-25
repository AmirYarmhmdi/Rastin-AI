# Web App

This folder contains the React 19, TypeScript, and Vite project workspace for
Rastin-AI. Bun manages dependencies and scripts.

## What Is In This Folder

| Part | Duty | Input | Outcome |
| --- | --- | --- | --- |
| `src/App.tsx` | Workspace selection, setup screens, chats, composer, and Project Library drawer. | User input, backend permissions, selections, loading/error state. | Project-scoped workspace UI using React state and effects. |
| `src/api.ts` | Client wrapper for backend HTTP requests. | Organization/project/session IDs, request payloads, uploaded files. | Typed responses from organization/project-scoped `/api/v1` endpoints. |
| `src/types.ts` | Shared TypeScript types for frontend data structures. | Backend response shapes and UI state needs. | Safer component and API code. |
| `src/main.tsx` | React entry point. | Browser DOM root and the main app component. | Mounted web application. |
| `src/styles.css` | Design tokens and application styling. | System theme and reduced-motion preferences, component markup. | Light/dark themes, responsive layout, and visible keyboard focus. |
| `public/assets/` | Locally hosted brand assets. | Figtree WOFF2, its OFL license, and the transparent lion PNG. | Local font/image requests; a light lion mark in dark mode. |
| `src/App.test.tsx` and `src/test/` | Frontend test coverage and setup. | Component behavior, mocked fetch responses, and a jsdom dialog shim. | UI, permission, selection, attachment, and scoped-endpoint regression checks. |
| `index.html` | Vite HTML shell. | Built JavaScript/CSS assets and the local font preload. | Browser document that hosts the React app. |
| `vite.config.ts` | Vite and test configuration. | Dev/build/test commands. | Local dev server, production bundle behavior, and test environment. |
| `package.json` and `bun.lock` | Frontend dependency and script definitions. | Bun install/run commands. | Reproducible frontend dependencies and scripts. |

## General Role

The web app is a thin client for the Rastin-AI backend. `App.tsx` contains the
components, local React state, and event handlers; `api.ts` owns HTTP
requests. The backend remains responsible for authorization, persistence,
retrieval, agent execution, and answer generation.

Use the single switcher at the bottom of the sidebar to choose a project or
workspace (an organization in the API), or create one. Setup uses a name field
and Continue; project descriptions are available through a disclosure. Project
creation requires workspace-owner authorization from the backend.

The sidebar lists the current project's private chats. **New chat** immediately
creates a server session. The composer accepts multiple attachments, grows with
the message, and preserves the draft and selected files after a failed send.
Enter inserts a newline; use **Send** to submit. Sources, citations, and workflow
details appear when returned by the backend.

**Files · N** opens the shared Project Library in a right-side modal drawer.
Chat attachments remain separate from the shared library. Escape closes the
drawer and returns focus to Files; Tab stays within the open modal.

| Effective project access | Private chats | Library upload | Library download | Library delete |
| --- | --- | --- | --- | --- |
| ADMIN, including workspace OWNER | Yes | Yes | Yes | Yes |
| MEMBER | Yes | Yes | Yes | No |
| VIEWER | No; View only | No | Yes | No |

The frontend uses the backend's effective role and permissions. It does not
call legacy global data endpoints or select a hidden default project. Valid
organization, project, and session selections retain the existing localStorage
keys: `rastin_ai.selectedOrganizationId`, `rastin_ai.selectedProjectId`, and
`rastin_ai.selectedSessionId`.

Themes follow `prefers-color-scheme`; animations respect `prefers-reduced-motion`.
Figtree is self-hosted under `public/assets/`, alongside its OFL license and the
lion mark extracted from `docs/images/rastin-ai-logo.png`. The visual mockup in
`docs/design/rastin-ai-v2.html` is a read-only reference and is not bundled.

## Inputs And Outcomes

| Input | Handled By | Outcome |
| --- | --- | --- |
| Workspace/project selection | React UI, localStorage, and `src/api.ts` | Accessible projects, project library, and private chat list. |
| User message and multiple attachments | React UI and `src/api.ts` | Multipart request to the selected project's chat session. |
| Chat history and message responses | React UI | Messages, statuses, returned citations/sources, and latest workflow details. |
| Project library files | React UI and `src/api.ts` | Upload, metadata, refresh, download, and permission-dependent delete. |
| Build/test commands | Vite, TypeScript, Vitest | Static frontend bundle or test report. |

## Useful Commands

Start the backend on `http://127.0.0.1:8000`, then run these commands from
`apps/web`. Vite proxies `/api` to that backend.

```bash
bun install
bun run dev
bun run test
bun run build
```

`bun run test` uses Vitest, Testing Library, and jsdom with mocked API responses.
It includes a guard against legacy global data endpoints. The dialog shim supports
component tests; native focus containment and rendering need browser checks.
`bun run build` runs TypeScript checks before producing `dist/`. There is no
separate frontend lint script.

## Manual Smoke-Test

- Switch between light/dark system themes; check the local font, lion mark,
  readable states, visible focus, and reduced-motion preference.
- Create and switch workspaces/projects, include an optional description, and
  reload to verify valid selections are restored.
- Check ADMIN/OWNER, MEMBER, and VIEWER access against the permissions table.
- Create a chat, reopen history, and send a message with multiple attachments.
  Check returned citations, sources, and workflow details; verify a failed send
  keeps the draft and selected files.
- Open Files; upload, refresh, inspect metadata, download, and delete where
  permitted. Check the file count and loading/error/empty states.
- Use Tab within the drawer, then Escape; focus should return to Files. Check
  switcher/menu focus and Escape behavior too.
- At narrow mobile widths, check navigation, the role-details disclosure, the
  drawer, and the growing composer for clipping or horizontal overflow.
