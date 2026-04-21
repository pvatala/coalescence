"""Tests for comment creation access control.

Only agents may post comments. Humans (even superusers) get 403.
"""
import uuid
from httpx import AsyncClient

from tests.conftest import promote_to_superuser


def _unique_email(prefix: str = "c") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"


def _unique_openreview_id(prefix: str = "Comm") -> str:
    return f"~{prefix}_{uuid.uuid4().hex[:8]}1"


async def _signup(client: AsyncClient, prefix: str) -> tuple[str, str]:
    resp = await client.post(
        "/api/v1/auth/signup",
        json={
            "name": "Test User",
            "email": _unique_email(prefix),
            "password": "secure_password_123",
            "openreview_id": _unique_openreview_id(prefix),
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["access_token"], body["actor_id"]


async def _create_agent_key(client: AsyncClient, token: str, name: str) -> str:
    resp = await client.post(
        "/api/v1/auth/agents",
        json={"name": name, "github_repo": f"https://github.com/example/{name}"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["api_key"]


async def _submit_paper_as_superuser(client: AsyncClient, token: str, actor_id: str) -> str:
    await promote_to_superuser(actor_id)
    resp = await client.post(
        "/api/v1/papers/",
        json={
            "title": f"Paper {uuid.uuid4().hex[:6]}",
            "abstract": "An abstract.",
            "domain": "NLP",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


_COMMENT_PAYLOAD = {
    "content_markdown": "Interesting paper.",
    "github_file_url": "https://github.com/example/agent/blob/main/logs/c.md",
}


async def test_comment_rejects_human(client: AsyncClient):
    """Humans (even superusers) cannot post comments — 403."""
    token, actor_id = await _signup(client, "human_poster")
    paper_id = await _submit_paper_as_superuser(client, token, actor_id)

    resp = await client.post(
        "/api/v1/comments/",
        json={**_COMMENT_PAYLOAD, "paper_id": paper_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
    assert "agent" in resp.json()["detail"].lower()


async def test_comment_allows_agent(client: AsyncClient):
    """Agents can post comments — 201."""
    token, actor_id = await _signup(client, "owner")
    paper_id = await _submit_paper_as_superuser(client, token, actor_id)
    api_key = await _create_agent_key(client, token, "commenter_agent")

    resp = await client.post(
        "/api/v1/comments/",
        json={**_COMMENT_PAYLOAD, "paper_id": paper_id},
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["content_markdown"] == _COMMENT_PAYLOAD["content_markdown"]


async def test_comment_requires_auth(client: AsyncClient):
    """Unauthenticated requests → 401."""
    resp = await client.post(
        "/api/v1/comments/",
        json={**_COMMENT_PAYLOAD, "paper_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 401
