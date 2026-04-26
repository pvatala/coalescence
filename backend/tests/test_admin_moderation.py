"""Tests for the GET /admin/moderation listing endpoint."""
import uuid
from httpx import AsyncClient

from tests.conftest import promote_to_superuser


def _unique_email(prefix: str = "am") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"


def _unique_openreview_id(prefix: str = "AM") -> str:
    return f"~{prefix.capitalize()}_{uuid.uuid4().hex[:8]}1"


async def _signup(client: AsyncClient, prefix: str) -> tuple[str, str]:
    resp = await client.post(
        "/api/v1/auth/signup",
        json={
            "name": "Test User",
            "email": _unique_email(prefix),
            "password": "secure_password_123",
            "openreview_ids": [_unique_openreview_id(prefix)],
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["access_token"], body["actor_id"]


async def _make_superuser(client: AsyncClient, prefix: str) -> tuple[str, str]:
    email = _unique_email(prefix)
    resp = await client.post(
        "/api/v1/auth/signup",
        json={
            "name": "Super User",
            "email": email,
            "password": "secure_password_123",
            "openreview_ids": [_unique_openreview_id(prefix)],
        },
    )
    assert resp.status_code == 201, resp.text
    actor_id = resp.json()["actor_id"]
    await promote_to_superuser(actor_id)

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "secure_password_123"},
    )
    assert login.status_code == 200, login.text
    return login.json()["access_token"], actor_id


async def _create_agent_key(client: AsyncClient, token: str, name: str) -> str:
    resp = await client.post(
        "/api/v1/auth/agents",
        json={"name": name, "github_repo": f"https://github.com/example/{name}"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["api_key"]


async def _submit_paper_as_superuser(
    client: AsyncClient, token: str, actor_id: str, title: str | None = None
) -> str:
    await promote_to_superuser(actor_id)
    resp = await client.post(
        "/api/v1/papers/",
        json={
            "title": title or f"Paper {uuid.uuid4().hex[:6]}",
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


def _patch_moderation_violate(monkeypatch) -> None:
    from app.core.moderation import (
        ModerationCategory,
        ModerationResult,
        ModerationVerdict,
    )
    import app.api.v1.endpoints.comments as comments_module

    async def _violate(content, *, paper_title=None):
        return ModerationResult(
            verdict=ModerationVerdict.VIOLATE,
            category=ModerationCategory.LOW_EFFORT,
            reason="low effort comment",
        )

    monkeypatch.setattr(comments_module, "moderate_comment", _violate)


async def _post_violate(
    client: AsyncClient, api_key: str, paper_id: str, content: str
) -> None:
    resp = await client.post(
        "/api/v1/comments/",
        json={
            "content_markdown": content,
            "github_file_url": _COMMENT_PAYLOAD["github_file_url"],
            "paper_id": paper_id,
        },
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert resp.status_code == 422, resp.text


async def test_list_requires_superuser(client: AsyncClient):
    """Non-superuser humans get 403 from /admin/moderation."""
    token, _ = await _signup(client, "am_regular")
    resp = await client.get(
        "/api/v1/admin/moderation",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


async def test_list_requires_auth(client: AsyncClient):
    """Unauthenticated requests get 401."""
    resp = await client.get("/api/v1/admin/moderation")
    assert resp.status_code == 401


async def test_list_returns_events_newest_first(client: AsyncClient, monkeypatch):
    """Events are returned ordered desc by created_at with denormalized names."""
    _patch_moderation_violate(monkeypatch)

    super_token, _ = await _make_superuser(client, "am_list_super")
    owner_token, owner_id = await _signup(client, "am_list_owner")
    paper_id = await _submit_paper_as_superuser(
        client, owner_token, owner_id, title="Listed Paper"
    )
    agent_name = f"am_list_agent_{uuid.uuid4().hex[:6]}"
    api_key = await _create_agent_key(client, owner_token, agent_name)

    await _post_violate(client, api_key, paper_id, "first bad comment")
    await _post_violate(client, api_key, paper_id, "second bad comment")

    resp = await client.get(
        "/api/v1/admin/moderation",
        headers={"Authorization": f"Bearer {super_token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["page"] == 1
    assert body["limit"] == 50
    items = body["items"]
    mine = [it for it in items if it["agent_name"] == agent_name]
    assert len(mine) == 2

    contents = [it["content_markdown"] for it in mine]
    assert contents == ["second bad comment", "first bad comment"]
    sample = mine[0]
    assert sample["paper_title"] == "Listed Paper"
    assert sample["agent_name"] == agent_name
    assert sample["category"] == "low_effort"
    assert sample["reason"] == "low effort comment"
    assert sample["strike_number"] in (1, 2)
    assert sample["karma_burned"] == 0.0
    assert sample["paper_id"] == paper_id


async def test_list_pagination(client: AsyncClient, monkeypatch):
    """limit=2 yields page 1 with 2 rows of this agent's events, page 2 with 1."""
    _patch_moderation_violate(monkeypatch)

    super_token, _ = await _make_superuser(client, "am_pag_super")
    owner_token, owner_id = await _signup(client, "am_pag_owner")
    paper_id = await _submit_paper_as_superuser(
        client, owner_token, owner_id, title="Paginated Paper"
    )
    agent_name = f"am_pag_agent_{uuid.uuid4().hex[:6]}"
    api_key = await _create_agent_key(client, owner_token, agent_name)

    for i in range(3):
        await _post_violate(client, api_key, paper_id, f"bad {i}")

    page_1 = await client.get(
        "/api/v1/admin/moderation?page=1&limit=2",
        headers={"Authorization": f"Bearer {super_token}"},
    )
    assert page_1.status_code == 200
    body_1 = page_1.json()
    assert body_1["page"] == 1
    assert body_1["limit"] == 2
    assert len(body_1["items"]) == 2
    assert body_1["total"] >= 3

    page_2 = await client.get(
        "/api/v1/admin/moderation?page=2&limit=2",
        headers={"Authorization": f"Bearer {super_token}"},
    )
    assert page_2.status_code == 200
    body_2 = page_2.json()
    assert body_2["page"] == 2
    assert body_2["limit"] == 2
    assert len(body_2["items"]) >= 1

    seen_ids_page1 = {it["id"] for it in body_1["items"]}
    seen_ids_page2 = {it["id"] for it in body_2["items"]}
    assert seen_ids_page1.isdisjoint(seen_ids_page2)
