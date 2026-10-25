"""Real PostgreSQL/API checks for private chat titles and workflow lookups."""

import asyncio
from uuid import UUID

import pytest
from sqlalchemy import select
from test_real_runtime_workflow import (
    E2ERuntime,
    _create_organization,
    _create_project,
    _create_project_session,
    _user_record,
)
from test_real_runtime_workflow import e2e_runtime as e2e_runtime

from rastin_ai.database.models.conversation_session import ConversationSession

pytestmark = pytest.mark.e2e


def test_rename_is_persisted_and_keeps_project_chat_private(
    e2e_runtime: E2ERuntime,
) -> None:
    runtime = e2e_runtime
    organization = _create_organization(runtime, slug="chat-titles")
    project = _create_project(runtime, organization["id"], name="Title checks")
    chat = _create_project_session(runtime, project_id=project["id"])
    path = f"/api/v1/projects/{project['id']}/sessions/{chat['id']}"
    response = runtime.client.patch(
        path, json={"title": "  CV   · Lingue  "}, headers=runtime.headers()
    )
    assert response.status_code == 200, response.text
    assert response.json()["title"] == "CV · Lingue"
    assert runtime.client.get(path, headers=runtime.headers()).json()["title"] == (
        "CV · Lingue"
    )
    listed = runtime.client.get(
        f"/api/v1/projects/{project['id']}/sessions", headers=runtime.headers()
    ).json()["sessions"]
    assert listed[0]["title"] == "CV · Lingue"
    stored = asyncio.run(
        runtime.scalar(
            select(ConversationSession.title).where(
                ConversationSession.id == UUID(chat["id"])
            )
        )
    )
    assert stored == "CV · Lingue"

    for payload in [
        {"title": "  \n\t"},
        {"title": ""},
        {"title": "x" * 256},
        {"title": None},
        {},
    ]:
        response = runtime.client.patch(path, json=payload, headers=runtime.headers())
        assert response.status_code == 422, response.text
    assert runtime.client.get(path, headers=runtime.headers()).json()["title"] == (
        "CV · Lingue"
    )

    other_project = _create_project(runtime, organization["id"], name="Other")
    response = runtime.client.patch(
        f"/api/v1/projects/{other_project['id']}/sessions/{chat['id']}",
        json={"title": "Wrong project"},
        headers=runtime.headers(),
    )
    assert response.status_code == 404

    runtime.client.get("/api/v1/organizations", headers=runtime.headers("user-b"))
    other_user = _user_record(runtime, "user-b")
    response = runtime.client.post(
        f"/api/v1/organizations/{organization['id']}/members",
        json={"user_id": str(other_user.id), "role": "MEMBER"},
        headers=runtime.headers(),
    )
    assert response.status_code == 201, response.text
    members_path = f"/api/v1/projects/{project['id']}/members"
    for role in ["MEMBER", "ADMIN", "VIEWER"]:
        if role != "MEMBER":
            response = runtime.client.delete(
                f"{members_path}/{other_user.id}", headers=runtime.headers()
            )
            assert response.status_code == 204, response.text
        response = runtime.client.post(
            members_path,
            json={"user_id": str(other_user.id), "role": role},
            headers=runtime.headers(),
        )
        assert response.status_code == 201, response.text
        response = runtime.client.patch(
            path,
            json={"title": "Other person's chat"},
            headers=runtime.headers("user-b"),
        )
        assert response.status_code == (403 if role == "VIEWER" else 404)
        if role == "MEMBER":
            own_chat = _create_project_session(
                runtime, project_id=project["id"], subject="user-b"
            )
        response = runtime.client.patch(
            f"/api/v1/projects/{project['id']}/sessions/{own_chat['id']}",
            json={"title": f"My {role} chat"},
            headers=runtime.headers("user-b"),
        )
        assert response.status_code == (403 if role == "VIEWER" else 200), response.text
    assert (
        runtime.client.get(path, headers=runtime.headers()).json()["title"]
        == "CV · Lingue"
    )


def test_project_workflow_details_read_the_persisted_execution(
    e2e_runtime: E2ERuntime,
) -> None:
    runtime = e2e_runtime
    organization = _create_organization(runtime, slug="workflow-read")
    project = _create_project(runtime, organization["id"], name="Workflow checks")
    chat = _create_project_session(runtime, project_id=project["id"])
    path = f"/api/v1/projects/{project['id']}/sessions/{chat['id']}"
    submission = runtime.client.post(
        f"{path}/messages",
        data={"message": "What evidence is available?"},
        headers=runtime.headers(),
    )
    assert submission.status_code == 200, submission.text
    workflow_id = submission.json()["workflow_id"]
    response = runtime.client.get(
        f"{path}/workflows/{workflow_id}", headers=runtime.headers()
    )
    assert response.status_code == 200, response.text
    assert response.json()["workflow_id"] == workflow_id
    assert response.json()["status"] == "completed"
    assert response.json()["result"]["answer"] == submission.json()["final_answer"]
    other_chat = _create_project_session(runtime, project_id=project["id"])
    response = runtime.client.get(
        f"/api/v1/projects/{project['id']}/sessions/{other_chat['id']}/workflows/{workflow_id}",
        headers=runtime.headers(),
    )
    assert response.status_code == 404
