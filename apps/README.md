# Apps

This folder contains user-facing applications that sit on top of the
Rastin-AI backend.

## What Is In This Folder

| Part | Duty | Input | Outcome |
| --- | --- | --- | --- |
| `web/` | React/Vite browser client for interacting with backend workflows. | User messages, file attachments, and API responses from the FastAPI backend. | A browser UI for submitting requests and inspecting workflow results. |

## General Role

`apps/` is the product surface area. Code here should focus on user interaction,
presentation, and client-side API calls. It should not own backend business
logic, persistence rules, RAG behavior, or agent orchestration.

## Boundary

Applications in this folder consume backend contracts exposed by
`src/rastin_ai/api`. When an app needs new behavior, the durable business
logic should usually be added to backend services first, then surfaced through
an API endpoint and consumed here.
