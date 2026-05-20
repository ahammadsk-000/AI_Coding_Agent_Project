"""Integration tests for the /repositories API.

We avoid spinning up Celery here; instead the test monkeypatches
`ingest_repository.delay` so create/list/get/delete + the enqueue endpoint
can be verified without a worker process.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from httpx import AsyncClient


async def _register_and_login(client: AsyncClient, email: str) -> str:
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "supersecret123", "full_name": "Repo Tester"},
    )
    assert r.status_code == 201, r.text
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "supersecret123"},
    )
    assert r.status_code == 200, r.text
    return r.json()["tokens"]["access_token"]


@pytest.fixture(autouse=True)
def _stub_celery_dispatch(monkeypatch):
    """Replace Celery's .delay with a no-op returning a fake AsyncResult."""
    from app.tasks import ingest as ingest_mod

    monkeypatch.setattr(
        ingest_mod.ingest_repository,
        "delay",
        lambda *a, **kw: SimpleNamespace(id="stub-task-id"),
    )
    yield


async def test_create_list_delete_repository(client: AsyncClient) -> None:
    token = await _register_and_login(client, "repo1@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.post(
        "/api/v1/repositories",
        headers=headers,
        json={"name": "fastapi", "url": "https://github.com/tiangolo/fastapi"},
    )
    assert r.status_code == 201, r.text
    repo = r.json()
    assert repo["status"] == "new"
    assert repo["qdrant_collection"] is None

    r = await client.get("/api/v1/repositories", headers=headers)
    assert r.status_code == 200
    assert any(x["id"] == repo["id"] for x in r.json())

    r = await client.get(f"/api/v1/repositories/{repo['id']}", headers=headers)
    assert r.status_code == 200
    assert r.json()["id"] == repo["id"]

    r = await client.delete(f"/api/v1/repositories/{repo['id']}", headers=headers)
    assert r.status_code == 204


async def test_duplicate_repository_url_rejected(client: AsyncClient) -> None:
    token = await _register_and_login(client, "repo2@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    body = {"name": "dup", "url": "https://github.com/example/dup"}
    r1 = await client.post("/api/v1/repositories", headers=headers, json=body)
    assert r1.status_code == 201
    r2 = await client.post("/api/v1/repositories", headers=headers, json=body)
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "conflict"


async def test_enqueue_ingest_returns_job_with_task_id(client: AsyncClient) -> None:
    token = await _register_and_login(client, "repo3@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    r = await client.post(
        "/api/v1/repositories",
        headers=headers,
        json={"name": "demo", "url": "https://github.com/example/demo"},
    )
    repo_id = r.json()["id"]

    r = await client.post(f"/api/v1/repositories/{repo_id}/ingest", headers=headers)
    assert r.status_code == 202, r.text
    job = r.json()
    assert job["status"] in {"queued", "running"}
    assert job["celery_task_id"] == "stub-task-id"

    r = await client.get(f"/api/v1/repositories/{repo_id}/jobs", headers=headers)
    assert r.status_code == 200
    assert len(r.json()) >= 1


async def test_repository_endpoints_require_auth(client: AsyncClient) -> None:
    r = await client.get("/api/v1/repositories")
    assert r.status_code == 401


async def test_other_user_cannot_access_my_repository(client: AsyncClient) -> None:
    token_a = await _register_and_login(client, "owner@example.com")
    token_b = await _register_and_login(client, "stranger@example.com")
    r = await client.post(
        "/api/v1/repositories",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"name": "private", "url": "https://github.com/example/private"},
    )
    repo_id = r.json()["id"]

    r = await client.get(
        f"/api/v1/repositories/{repo_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r.status_code == 404
