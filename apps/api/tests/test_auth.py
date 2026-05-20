"""End-to-end auth flow tests."""
from __future__ import annotations

from httpx import AsyncClient


async def _register(client: AsyncClient, email: str = "alice@example.com") -> dict:
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "supersecret123", "full_name": "Alice"},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _login(client: AsyncClient, email: str = "alice@example.com") -> dict:
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "supersecret123"},
    )
    assert r.status_code == 200, r.text
    return r.json()


async def test_register_creates_user_with_default_role(client: AsyncClient) -> None:
    body = await _register(client, "bob@example.com")
    assert body["email"] == "bob@example.com"
    assert body["is_active"] is True
    assert body["is_superuser"] is False
    assert any(role["name"] == "member" for role in body["roles"])


async def test_register_rejects_duplicate_email(client: AsyncClient) -> None:
    await _register(client, "carol@example.com")
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": "carol@example.com", "password": "supersecret123"},
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "conflict"


async def test_login_returns_tokens_and_me_works(client: AsyncClient) -> None:
    await _register(client, "dave@example.com")
    body = await _login(client, "dave@example.com")
    access = body["tokens"]["access_token"]
    assert access

    r = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 200
    assert r.json()["email"] == "dave@example.com"


async def test_login_rejects_bad_password(client: AsyncClient) -> None:
    await _register(client, "eve@example.com")
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "eve@example.com", "password": "WRONG-pass-1"},
    )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


async def test_refresh_rotates_token(client: AsyncClient) -> None:
    await _register(client, "frank@example.com")
    body = await _login(client, "frank@example.com")
    old_refresh = body["tokens"]["refresh_token"]

    r = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": old_refresh}
    )
    assert r.status_code == 200
    new_refresh = r.json()["refresh_token"]
    assert new_refresh != old_refresh

    # old refresh must now be invalid (single-use rotation)
    r2 = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": old_refresh}
    )
    assert r2.status_code == 401


async def test_logout_revokes_refresh_token(client: AsyncClient) -> None:
    await _register(client, "gina@example.com")
    body = await _login(client, "gina@example.com")
    access = body["tokens"]["access_token"]
    refresh = body["tokens"]["refresh_token"]

    r = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 204

    r2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert r2.status_code == 401


async def test_me_requires_auth(client: AsyncClient) -> None:
    r = await client.get("/api/v1/users/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"
