# Web App

This folder contains the React and Vite frontend for Rastin-AI.

## What Is In This Folder

| Part | Duty | Input | Outcome |
| --- | --- | --- | --- |
| `src/App.tsx` | Main application UI and workflow screens. | User text, selected files, workflow data, loading/error state. | Rendered interface for submitting messages and viewing workflow runs. |
| `src/api.ts` | Client wrapper for backend HTTP requests. | API base URL, request payloads, uploaded files. | Typed responses from `/api/v1` backend endpoints. |
| `src/types.ts` | Shared TypeScript types for frontend data structures. | Backend response shapes and UI state needs. | Safer component and API code. |
| `src/main.tsx` | React entry point. | Browser DOM root and the main app component. | Mounted web application. |
| `src/styles.css` | Application styling. | HTML structure and class names from React components. | Visual layout, spacing, colors, and responsive behavior. |
| `src/App.test.tsx` and `src/test/` | Frontend test coverage and setup. | Component behavior and mocked browser/test APIs. | Vitest test results for UI behavior. |
| `index.html` | Vite HTML shell. | Built JavaScript and CSS assets. | Browser document that hosts the React app. |
| `vite.config.ts` | Vite and test configuration. | Dev/build/test commands. | Local dev server, production bundle behavior, and test environment. |
| `package.json` and `bun.lock` | Frontend dependency and script definitions. | Bun install/run commands. | Reproducible frontend dependencies and scripts. |

## General Role

The web app is a thin client for the Rastin-AI backend. It gathers user input,
sends messages and attachments to the API, displays workflow status, and renders
recent run details. The backend remains responsible for persistence, retrieval,
agent execution, and answer generation.

## Inputs And Outcomes

| Input | Handled By | Outcome |
| --- | --- | --- |
| User message text | React UI and `src/api.ts` | Multipart or JSON request to the backend. |
| File attachments | React UI and `src/api.ts` | Uploaded file metadata and workflow context. |
| Workflow list/detail responses | React UI | Visible run history, statuses, and details. |
| Build/test commands | Vite, TypeScript, Vitest | Static frontend bundle or test report. |

## Useful Commands

```bash
bun install
bun run dev
bun run test
bun run build
```
