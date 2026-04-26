"""Public actor profile endpoints."""
import uuid
from datetime import UTC, datetime

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings


async def _exec(sql: str, params: dict | None = None):
    engine = create_async_engine(str(settings.DATABASE_URL), pool_pre_ping=True)
    try:
        async with engine.begin() as conn:
            await conn.execute(text(sql), params or {})
    finally:
        await engine.dispose()


async def _make_human() -> str:
    aid = str(uuid.uuid4())
    await _exec(
        "INSERT INTO actor (id, name, actor_type, is_active, created_at, updated_at) "
        "VALUES (:id, :n, 'human', true, now(), now())",
        {"id": aid, "n": f"profile_human_{uuid.uuid4().hex[:6]}"},
    )
    await _exec(
        "INSERT INTO human_account (id, email, hashed_password, is_superuser) "
        "VALUES (:id, :e, 'x', false)",
        {"id": aid, "e": f"profile_{uuid.uuid4().hex[:8]}@test.example"},
    )
    return aid


async def _make_agent(owner_id: str) -> str:
    aid = str(uuid.uuid4())
    await _exec(
        "INSERT INTO actor (id, name, actor_type, is_active, created_at, updated_at) "
        "VALUES (:id, :n, 'agent', true, now(), now())",
        {"id": aid, "n": f"profile_agent_{uuid.uuid4().hex[:6]}"},
    )
    await _exec(
        "INSERT INTO agent (id, owner_id, api_key_hash, api_key_lookup, github_repo) "
        "VALUES (:id, :o, :h, :l, 'https://github.com/x/y')",
        {"id": aid, "o": owner_id, "h": uuid.uuid4().hex, "l": uuid.uuid4().hex[:16]},
    )
    return aid


async def _make_paper(submitter_id: str, *, released: bool) -> str:
    pid = str(uuid.uuid4())
    await _exec(
        "INSERT INTO paper (id, title, abstract, domains, submitter_id, status, "
        "released_at, created_at, updated_at) "
        "VALUES (:id, :t, 'a', ARRAY['d/ProfileTest'], :sub, 'in_review'::paperstatus, "
        ":released_at, now(), now())",
        {
            "id": pid,
            "t": f"profile-paper-{uuid.uuid4().hex[:6]}",
            "sub": submitter_id,
            "released_at": datetime.now(UTC).replace(tzinfo=None) if released else None,
        },
    )
    return pid


async def _make_comment(paper_id: str, author_id: str) -> str:
    cid = str(uuid.uuid4())
    await _exec(
        "INSERT INTO comment (id, paper_id, author_id, content_markdown, github_file_url, "
        "created_at, updated_at) "
        "VALUES (:id, :p, :a, 'profile comment', "
        "'https://github.com/x/y/blob/main/profile.md', now(), now())",
        {"id": cid, "p": paper_id, "a": author_id},
    )
    return cid


async def _make_verdict(paper_id: str, author_id: str) -> str:
    vid = str(uuid.uuid4())
    await _exec(
        "INSERT INTO verdict (id, paper_id, author_id, content_markdown, score, github_file_url, "
        "created_at, updated_at) "
        "VALUES (:id, :p, :a, 'profile verdict', 8.0, "
        "'https://github.com/x/y/blob/main/profile-verdict.md', now(), now())",
        {"id": vid, "p": paper_id, "a": author_id},
    )
    return vid


async def _cleanup(
    *,
    comments: list[str],
    papers: list[str],
    agents: list[str],
    humans: list[str],
    verdicts: list[str] | None = None,
) -> None:
    for vid in verdicts or []:
        await _exec("DELETE FROM verdict WHERE id = :id", {"id": vid})
    for cid in comments:
        await _exec("DELETE FROM comment WHERE id = :id", {"id": cid})
    for pid in papers:
        await _exec("DELETE FROM paper WHERE id = :id", {"id": pid})
    for aid in agents:
        await _exec("DELETE FROM agent WHERE id = :id", {"id": aid})
    for hid in humans:
        await _exec("DELETE FROM human_account WHERE id = :id", {"id": hid})
    for actor_id in agents + humans:
        await _exec("DELETE FROM actor WHERE id = :id", {"id": actor_id})


async def test_public_agent_profile_exposes_owner_link(client: AsyncClient):
    humans: list[str] = []
    agents: list[str] = []
    try:
        human = await _make_human()
        humans.append(human)
        agent = await _make_agent(human)
        agents.append(agent)

        resp = await client.get(f"/api/v1/users/{agent}")
        assert resp.status_code == 200
        body = resp.json()

        assert body["id"] == agent
        assert body["actor_type"] == "agent"
        assert body["owner_id"] == human
        assert body["owner_name"].startswith("profile_human_")
        assert body["github_repo"] == "https://github.com/x/y"
    finally:
        await _cleanup(comments=[], papers=[], agents=agents, humans=humans)


async def test_public_profile_activity_only_includes_released_papers(client: AsyncClient):
    humans: list[str] = []
    agents: list[str] = []
    papers: list[str] = []
    comments: list[str] = []
    verdicts: list[str] = []
    try:
        human = await _make_human()
        humans.append(human)
        agent = await _make_agent(human)
        agents.append(agent)
        released_paper = await _make_paper(human, released=True)
        unreleased_paper = await _make_paper(human, released=False)
        papers.extend([released_paper, unreleased_paper])
        released_comment = await _make_comment(released_paper, agent)
        unreleased_comment = await _make_comment(unreleased_paper, agent)
        comments.extend([released_comment, unreleased_comment])
        released_verdict = await _make_verdict(released_paper, agent)
        unreleased_verdict = await _make_verdict(unreleased_paper, agent)
        verdicts.extend([released_verdict, unreleased_verdict])

        profile_resp = await client.get(f"/api/v1/users/{agent}")
        assert profile_resp.status_code == 200
        agent_profile = profile_resp.json()
        assert agent_profile["stats"]["comments"] == 1
        assert agent_profile["stats"]["verdicts"] == 1
        assert agent_profile["recent_stats"]["comments"] == 1
        assert agent_profile["recent_stats"]["verdicts"] == 1
        assert agent_profile["recent_stats"]["window_hours"] == 3

        human_resp = await client.get(f"/api/v1/users/{human}")
        assert human_resp.status_code == 200
        human_profile = human_resp.json()
        assert human_profile["recent_stats"]["comments"] == 1
        assert human_profile["recent_stats"]["verdicts"] == 1
        assert human_profile["recent_stats"]["papers"] == 1

        comments_resp = await client.get(f"/api/v1/users/{agent}/comments")
        assert comments_resp.status_code == 200
        ids = {row["id"] for row in comments_resp.json()}
        assert released_comment in ids
        assert unreleased_comment not in ids
    finally:
        await _cleanup(comments=comments, papers=papers, agents=agents, humans=humans, verdicts=verdicts)
