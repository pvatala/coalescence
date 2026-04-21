"""Tests for paper submission access control.

Paper submission is gated on the submitter being a human account with
is_superuser=true. Delegated agents cannot submit.
"""
import uuid
from httpx import AsyncClient

from tests.conftest import promote_to_superuser


_PAPER_PAYLOAD = {
    "title": "A test paper",
    "abstract": "An abstract.",
    "domain": "NLP",
}


def _unique_email(prefix: str = "papers") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"


async def _signup(client: AsyncClient, prefix: str) -> tuple[str, str]:
    """Create a human account, return (token, actor_id)."""
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


async def _register_agent(client: AsyncClient, prefix: str = "agent") -> str:
    resp = await client.post(
        "/api/v1/auth/agents/register",
        json={
            "name": f"{prefix}_{uuid.uuid4().hex[:6]}",
            "owner_email": _unique_email(f"owner_{prefix}"),
            "owner_name": "Owner",
            "owner_password": "secure_password_123",
            "github_repo": "https://github.com/example/agent",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["api_key"]


async def test_submit_paper_requires_auth(client: AsyncClient):
    resp = await client.post("/api/v1/papers/", json=_PAPER_PAYLOAD)
    assert resp.status_code == 401


async def test_submit_paper_rejects_non_superuser_human(client: AsyncClient):
    """A signed-up human without is_superuser gets 403."""
    token, _ = await _signup(client, "regular")
    resp = await client.post(
        "/api/v1/papers/",
        json=_PAPER_PAYLOAD,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
    assert "superuser" in resp.json()["detail"].lower()


async def test_submit_paper_rejects_delegated_agent(client: AsyncClient):
    """Delegated agents are structurally ineligible (is_superuser lives on HumanAccount only)."""
    api_key = await _register_agent(client, "submitter")
    resp = await client.post(
        "/api/v1/papers/",
        json=_PAPER_PAYLOAD,
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert resp.status_code == 403
    assert "superuser" in resp.json()["detail"].lower()


async def test_submit_paper_allows_superuser(client: AsyncClient):
    """A human promoted to superuser can submit."""
    token, actor_id = await _signup(client, "super")
    await promote_to_superuser(actor_id)

    resp = await client.post(
        "/api/v1/papers/",
        json=_PAPER_PAYLOAD,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["title"] == _PAPER_PAYLOAD["title"]
    assert "id" in body
