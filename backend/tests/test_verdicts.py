"""Tests for verdict prerequisite checks.

An agent must have posted at least one comment on the paper before
submitting a verdict. No other prerequisite (voting used to be required
too but was removed).
"""
import uuid
import pytest
from httpx import AsyncClient

from tests.conftest import promote_to_superuser, set_paper_status


def _unique_email(prefix: str = "v") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"


def _unique_openreview_id(prefix: str = "V") -> str:
    safe = "".join(c for c in prefix if c.isalnum()) or "V"
    return f"~{safe.capitalize()}_{uuid.uuid4().hex[:8]}1"


async def _register_agent(client: AsyncClient, prefix: str = "agent") -> str:
    """Sign up a human owner, then create an agent under that human. Returns the agent's API key."""
    signup_resp = await client.post(
        "/api/v1/auth/signup",
        json={
            "name": "Test Owner",
            "email": _unique_email(prefix),
            "password": "secure_password_123",
            "openreview_id": _unique_openreview_id(prefix),
        },
    )
    assert signup_resp.status_code == 201, signup_resp.text
    token = signup_resp.json()["access_token"]

    resp = await client.post(
        "/api/v1/auth/agents",
        json={
            "name": f"{prefix}_{uuid.uuid4().hex[:6]}",
            "github_repo": f"https://github.com/example/{prefix}",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["api_key"]


async def _submit_paper(client: AsyncClient, token: str) -> str:
    resp = await client.post(
        "/api/v1/papers/",
        json={
            "title": f"Paper {uuid.uuid4().hex[:8]}",
            "abstract": "An abstract.",
            "domain": "NLP",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _signup_and_token(client: AsyncClient, prefix: str = "user") -> str:
    """Create a superuser human account and return its JWT.

    Paper submission requires superuser, so tests that submit papers need one.
    """
    email = _unique_email(prefix)
    resp = await client.post(
        "/api/v1/auth/signup",
        json={
            "name": "Test User",
            "email": email,
            "password": "secure_password_123",
            "openreview_id": _unique_openreview_id(prefix),
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    await promote_to_superuser(body["actor_id"])
    return body["access_token"]


async def _post_comment(client: AsyncClient, api_key: str, paper_id: str) -> str:
    resp = await client.post(
        "/api/v1/comments/",
        json={
            "paper_id": paper_id,
            "content_markdown": "A comment.",
            "github_file_url": "https://github.com/example/agent/blob/main/logs/c.md",
        },
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


_VERDICT_PAYLOAD = {
    "content_markdown": "Great paper.",
    "score": 7.5,
    "github_file_url": "https://github.com/example/agent/blob/main/logs/verdict.md",
}


@pytest.fixture
async def paper_id(client: AsyncClient) -> str:
    token = await _signup_and_token(client, "submitter")
    return await _submit_paper(client, token)


async def test_verdict_blocked_without_comment(client: AsyncClient, paper_id: str):
    """An agent that has not commented on the paper cannot submit a verdict."""
    api_key = await _register_agent(client, "nocomment")
    await set_paper_status(paper_id, "deliberating")

    resp = await client.post(
        "/api/v1/verdicts/",
        json={**_VERDICT_PAYLOAD, "paper_id": paper_id},
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert resp.status_code == 403
    assert "comment" in resp.json()["detail"].lower()


async def test_verdict_succeeds_after_comment(client: AsyncClient, paper_id: str):
    """Posting a comment on the paper unlocks the verdict — no vote required."""
    api_key = await _register_agent(client, "verdicter")
    await _post_comment(client, api_key, paper_id)
    await set_paper_status(paper_id, "deliberating")

    resp = await client.post(
        "/api/v1/verdicts/",
        json={**_VERDICT_PAYLOAD, "paper_id": paper_id},
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["score"] == 7.5
    assert data["paper_id"] == paper_id


async def test_verdict_duplicate_blocked(client: AsyncClient, paper_id: str):
    """Submitting a second verdict on the same paper returns 409."""
    api_key = await _register_agent(client, "dupverdict")
    await _post_comment(client, api_key, paper_id)
    await set_paper_status(paper_id, "deliberating")

    payload = {**_VERDICT_PAYLOAD, "paper_id": paper_id}
    resp1 = await client.post(
        "/api/v1/verdicts/", json=payload, headers={"Authorization": f"Bearer {api_key}"}
    )
    assert resp1.status_code == 201

    resp2 = await client.post(
        "/api/v1/verdicts/", json=payload, headers={"Authorization": f"Bearer {api_key}"}
    )
    assert resp2.status_code == 409


async def test_verdict_blocked_when_paper_in_review(client: AsyncClient, paper_id: str):
    """A paper still in the in_review phase rejects verdict posts with 409."""
    api_key = await _register_agent(client, "tooearly")

    resp = await client.post(
        "/api/v1/verdicts/",
        json={**_VERDICT_PAYLOAD, "paper_id": paper_id},
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert resp.status_code == 409
    detail = resp.json()["detail"].lower()
    assert "in_review" in detail
