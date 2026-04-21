import uuid
from httpx import AsyncClient


def _unique_email(prefix: str = "test") -> str:
    """Generate a unique email to avoid conflicts across test runs."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"


async def _signup(client: AsyncClient, prefix: str = "user") -> tuple[str, str]:
    """Sign up a human account, return (access_token, actor_id)."""
    resp = await client.post(
        "/api/v1/auth/signup",
        json={
            "name": "Test User",
            "email": _unique_email(prefix),
            "password": "secure_password_123",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["access_token"], body["actor_id"]


async def test_health(client: AsyncClient):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "coalescence"}


async def test_public_agent_register_endpoint_removed(client: AsyncClient):
    """The old public self-register endpoint is gone. Either 404 (no such
    path) or 405 (path collides with DELETE /auth/agents/{id}) means the
    POST endpoint is unavailable — both count as 'removed'."""
    response = await client.post(
        "/api/v1/auth/agents/register",
        json={
            "name": "ghost_agent",
            "owner_email": _unique_email("gone"),
            "owner_name": "Ghost",
            "owner_password": "test_password_123",
            "github_repo": "https://github.com/example/gone",
        },
    )
    assert response.status_code in (404, 405)


async def test_sovereign_register_endpoint_removed(client: AsyncClient):
    """Sovereign-agent register endpoint is gone."""
    response = await client.post(
        "/api/v1/auth/agents/sovereign/register",
        json={"name": "sov", "public_key": "ed25519:x"},
    )
    assert response.status_code in (404, 405)


async def test_create_agent_requires_auth(client: AsyncClient):
    """POST /auth/agents rejects unauthenticated requests."""
    response = await client.post(
        "/api/v1/auth/agents",
        json={
            "name": "test_agent_noauth",
            "github_repo": "https://github.com/example/noauth",
        },
    )
    assert response.status_code == 401


async def test_create_agent_rejects_agent_auth(client: AsyncClient):
    """Agents cannot create other agents — human-only endpoint."""
    token, _ = await _signup(client, "owner")
    # Create first agent as the human
    first = await client.post(
        "/api/v1/auth/agents",
        json={
            "name": "first_agent",
            "github_repo": "https://github.com/example/first",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert first.status_code == 201, first.text
    agent_api_key = first.json()["api_key"]
    assert agent_api_key.startswith("cs_")

    # Try to create a second agent using the first agent's API key → 403
    second = await client.post(
        "/api/v1/auth/agents",
        json={
            "name": "second_agent",
            "github_repo": "https://github.com/example/second",
        },
        headers={"Authorization": f"Bearer {agent_api_key}"},
    )
    assert second.status_code == 403


async def test_create_agent_succeeds_for_human(client: AsyncClient):
    """Humans can create agents and get a cs_ API key back."""
    token, _ = await _signup(client, "creator")
    resp = await client.post(
        "/api/v1/auth/agents",
        json={
            "name": "my_agent",
            "description": "Test agent",
            "github_repo": "https://github.com/example/my-agent",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert "id" in data
    assert "api_key" in data
    assert data["api_key"].startswith("cs_")


async def test_created_agent_can_authenticate(client: AsyncClient):
    """The API key returned by POST /auth/agents works as a bearer."""
    token, _ = await _signup(client, "auther")
    reg_resp = await client.post(
        "/api/v1/auth/agents",
        json={
            "name": "key_auth_agent",
            "github_repo": "https://github.com/example/key-auth-agent",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert reg_resp.status_code == 201
    api_key = reg_resp.json()["api_key"]

    me_resp = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["name"] == "key_auth_agent"


async def test_list_agents_scoped_to_owner(client: AsyncClient):
    """GET /auth/agents returns only the authenticated human's agents."""
    token_a, _ = await _signup(client, "lister_a")
    token_b, _ = await _signup(client, "lister_b")

    # User A creates two agents, user B creates one
    for name in ("a_agent_1", "a_agent_2"):
        resp = await client.post(
            "/api/v1/auth/agents",
            json={"name": name, "github_repo": f"https://github.com/example/{name}"},
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 201
    resp_b = await client.post(
        "/api/v1/auth/agents",
        json={"name": "b_agent_1", "github_repo": "https://github.com/example/b_agent_1"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp_b.status_code == 201

    list_a = await client.get(
        "/api/v1/auth/agents", headers={"Authorization": f"Bearer {token_a}"}
    )
    assert list_a.status_code == 200
    names_a = {a["name"] for a in list_a.json()}
    assert {"a_agent_1", "a_agent_2"}.issubset(names_a)
    assert "b_agent_1" not in names_a


async def test_list_agents_no_plaintext_key(client: AsyncClient):
    """GET /auth/agents response must not include the plaintext API key."""
    token, _ = await _signup(client, "noplain")
    await client.post(
        "/api/v1/auth/agents",
        json={"name": "noplain_agent", "github_repo": "https://github.com/example/noplain"},
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = await client.get(
        "/api/v1/auth/agents", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    for entry in resp.json():
        assert "api_key" not in entry
        assert "api_key_plain" not in entry
        assert "api_key_preview" not in entry


async def test_delete_agent_owner_only(client: AsyncClient):
    """DELETE /auth/agents/{id} only works for the owning human."""
    token_a, _ = await _signup(client, "del_owner")
    token_b, _ = await _signup(client, "del_other")

    resp = await client.post(
        "/api/v1/auth/agents",
        json={"name": "del_agent", "github_repo": "https://github.com/example/del"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 201
    agent_id = resp.json()["id"]

    # User B (not the owner) → 404 (filtered out by owner scoping)
    other_resp = await client.delete(
        f"/api/v1/auth/agents/{agent_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert other_resp.status_code == 404

    # Owner can delete
    owner_resp = await client.delete(
        f"/api/v1/auth/agents/{agent_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert owner_resp.status_code == 200


async def test_signup_and_login(client: AsyncClient):
    """Signup creates a human account, login returns JWT."""
    email = _unique_email("signup")

    signup_resp = await client.post(
        "/api/v1/auth/signup",
        json={
            "name": "Auth Test User",
            "email": email,
            "password": "secure_password_123",
        },
    )
    assert signup_resp.status_code == 201
    assert "access_token" in signup_resp.json()

    login_resp = await client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": "secure_password_123",
        },
    )
    assert login_resp.status_code == 200
    data = login_resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


async def test_login_wrong_password(client: AsyncClient):
    """Login with wrong password returns 401."""
    email = _unique_email("wrongpass")

    await client.post(
        "/api/v1/auth/signup",
        json={
            "name": "Wrong Pass User",
            "email": email,
            "password": "correct_password",
        },
    )

    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": "wrong_password",
        },
    )
    assert response.status_code == 401
