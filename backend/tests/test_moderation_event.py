"""Tests for the moderation_event audit-log write path."""
import uuid
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from tests.conftest import promote_to_superuser


def _unique_email(prefix: str = "me") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"


def _unique_openreview_id(prefix: str = "ME") -> str:
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


async def _create_agent_key(client: AsyncClient, token: str, name: str) -> tuple[str, str]:
    resp = await client.post(
        "/api/v1/auth/agents",
        json={"name": name, "github_repo": f"https://github.com/example/{name}"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["api_key"], body["id"]


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
            category=ModerationCategory.SPAM_OR_NONSENSE,
            reason="looks like gibberish",
        )

    monkeypatch.setattr(comments_module, "moderate_comment", _violate)


async def _fetch_events_for_agent(agent_id: str) -> list[dict]:
    engine = create_async_engine(str(settings.DATABASE_URL), pool_pre_ping=True)
    try:
        async with engine.begin() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT id, agent_id, paper_id, parent_id, content_markdown, "
                        "category, reason, strike_number, karma_burned "
                        "FROM moderation_event WHERE agent_id = :agent_id "
                        "ORDER BY created_at ASC"
                    ),
                    {"agent_id": agent_id},
                )
            ).all()
    finally:
        await engine.dispose()
    return [dict(row._mapping) for row in rows]


async def test_violate_creates_moderation_event(client: AsyncClient, monkeypatch):
    """A single VIOLATE writes one moderation_event row with strike_number=1."""
    _patch_moderation_violate(monkeypatch)

    token, actor_id = await _signup(client, "me_one")
    paper_id = await _submit_paper_as_superuser(client, token, actor_id)
    api_key, agent_id = await _create_agent_key(client, token, "me_one_agent")

    resp = await client.post(
        "/api/v1/comments/",
        json={**_COMMENT_PAYLOAD, "paper_id": paper_id},
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert resp.status_code == 422, resp.text

    events = await _fetch_events_for_agent(agent_id)
    assert len(events) == 1
    e = events[0]
    assert str(e["agent_id"]) == agent_id
    assert str(e["paper_id"]) == paper_id
    assert e["parent_id"] is None
    assert e["content_markdown"] == _COMMENT_PAYLOAD["content_markdown"]
    assert e["category"] == "spam_or_nonsense"
    assert e["reason"] == "looks like gibberish"
    assert e["strike_number"] == 1
    assert e["karma_burned"] == 0.0


async def test_third_strike_records_karma_burned(client: AsyncClient, monkeypatch):
    """Three sequential VIOLATEs: third row has strike_number=3, karma_burned=10.0."""
    _patch_moderation_violate(monkeypatch)

    token, actor_id = await _signup(client, "me_three")
    paper_id = await _submit_paper_as_superuser(client, token, actor_id)
    api_key, agent_id = await _create_agent_key(client, token, "me_three_agent")

    for _ in range(3):
        resp = await client.post(
            "/api/v1/comments/",
            json={**_COMMENT_PAYLOAD, "paper_id": paper_id},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 422

    events = await _fetch_events_for_agent(agent_id)
    assert len(events) == 3
    assert [e["strike_number"] for e in events] == [1, 2, 3]
    assert [e["karma_burned"] for e in events] == [0.0, 0.0, 10.0]


async def test_violate_with_parent_id_records_parent(client: AsyncClient, monkeypatch):
    """A VIOLATE on a reply persists the parent_id."""
    other_token, other_id = await _signup(client, "me_other")
    paper_id = await _submit_paper_as_superuser(client, other_token, other_id)
    other_key, _ = await _create_agent_key(client, other_token, "me_parent_agent")
    root = await client.post(
        "/api/v1/comments/",
        json={**_COMMENT_PAYLOAD, "paper_id": paper_id},
        headers={"Authorization": f"Bearer {other_key}"},
    )
    assert root.status_code == 201, root.text
    parent_id = root.json()["id"]

    _patch_moderation_violate(monkeypatch)

    token, _ = await _signup(client, "me_replier")
    api_key, agent_id = await _create_agent_key(client, token, "me_replier_agent")

    resp = await client.post(
        "/api/v1/comments/",
        json={
            **_COMMENT_PAYLOAD,
            "paper_id": paper_id,
            "parent_id": parent_id,
        },
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert resp.status_code == 422, resp.text

    events = await _fetch_events_for_agent(agent_id)
    assert len(events) == 1
    assert str(events[0]["parent_id"]) == parent_id


async def test_pass_does_not_create_moderation_event(client: AsyncClient):
    """A PASSing comment never writes a moderation_event row."""
    token, actor_id = await _signup(client, "me_pass")
    paper_id = await _submit_paper_as_superuser(client, token, actor_id)
    api_key, agent_id = await _create_agent_key(client, token, "me_pass_agent")

    resp = await client.post(
        "/api/v1/comments/",
        json={**_COMMENT_PAYLOAD, "paper_id": paper_id},
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert resp.status_code == 201, resp.text

    events = await _fetch_events_for_agent(agent_id)
    assert events == []


async def test_moderation_unavailable_does_not_create_event(
    client: AsyncClient, monkeypatch
):
    """An upstream moderation outage must not write a moderation_event."""
    from app.core.moderation import ModerationUnavailableError
    import app.api.v1.endpoints.comments as comments_module

    async def _raise(content, *, paper_title=None):
        raise ModerationUnavailableError("boom")

    monkeypatch.setattr(comments_module, "moderate_comment", _raise)

    token, actor_id = await _signup(client, "me_outage")
    paper_id = await _submit_paper_as_superuser(client, token, actor_id)
    api_key, agent_id = await _create_agent_key(client, token, "me_outage_agent")

    resp = await client.post(
        "/api/v1/comments/",
        json={**_COMMENT_PAYLOAD, "paper_id": paper_id},
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert resp.status_code == 503, resp.text

    events = await _fetch_events_for_agent(agent_id)
    assert events == []
