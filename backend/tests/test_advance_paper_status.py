"""End-to-end test for the lifecycle-advance cron script.

Creates papers directly via the DB, backdates timestamps, runs
``advance_paper_status.advance()``, and asserts transitions.
"""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from scripts.advance_paper_status import advance


async def _insert_human(name_prefix: str) -> str:
    """Insert a bare actor row (human account) and return its id."""
    engine = create_async_engine(str(settings.DATABASE_URL), pool_pre_ping=True)
    actor_id = str(uuid.uuid4())
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO actor (id, name, actor_type, is_active, created_at, updated_at) "
                    "VALUES (:id, :name, 'human', true, now(), now())"
                ),
                {"id": actor_id, "name": f"{name_prefix}_{uuid.uuid4().hex[:6]}"},
            )
            await conn.execute(
                text(
                    "INSERT INTO human_account (id, email, hashed_password, is_superuser, "
                    "openreview_id) "
                    "VALUES (:id, :email, 'x', false, :oid)"
                ),
                {
                    "id": actor_id,
                    "email": f"{name_prefix}_{uuid.uuid4().hex[:8]}@test.example",
                    "oid": f"~Lifecycle_{uuid.uuid4().hex[:8]}1",
                },
            )
    finally:
        await engine.dispose()
    return actor_id


async def _insert_paper(
    submitter_id: str,
    *,
    status: str,
    created_at: datetime,
    deliberating_at: datetime | None = None,
) -> str:
    engine = create_async_engine(str(settings.DATABASE_URL), pool_pre_ping=True)
    paper_id = str(uuid.uuid4())
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO paper (id, title, abstract, domains, submitter_id, "
                    "status, deliberating_at, created_at, updated_at) "
                    "VALUES (:id, :title, 'abstract', ARRAY['d/NLP'], :sub, "
                    "CAST(:status AS paperstatus), :deliberating_at, :created_at, :created_at)"
                ),
                {
                    "id": paper_id,
                    "title": f"lifecycle-{uuid.uuid4().hex[:6]}",
                    "sub": submitter_id,
                    "status": status,
                    "deliberating_at": deliberating_at,
                    "created_at": created_at,
                },
            )
    finally:
        await engine.dispose()
    return paper_id


async def _insert_agent(name_prefix: str, owner_id: str) -> str:
    """Insert an agent owned by the given human and return its id."""
    engine = create_async_engine(str(settings.DATABASE_URL), pool_pre_ping=True)
    actor_id = str(uuid.uuid4())
    key = secrets.token_hex(16)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO actor (id, name, actor_type, is_active, created_at, updated_at) "
                    "VALUES (:id, :name, 'agent', true, now(), now())"
                ),
                {"id": actor_id, "name": f"{name_prefix}_{uuid.uuid4().hex[:6]}"},
            )
            await conn.execute(
                text(
                    "INSERT INTO agent (id, owner_id, api_key_hash, api_key_lookup, karma) "
                    "VALUES (:id, :owner, :h, :l, 100.0)"
                ),
                {
                    "id": actor_id,
                    "owner": owner_id,
                    "h": hashlib.sha256(key.encode()).hexdigest(),
                    "l": key[:8] + uuid.uuid4().hex[:8],
                },
            )
    finally:
        await engine.dispose()
    return actor_id


async def _insert_comment(paper_id: str, author_id: str) -> str:
    engine = create_async_engine(str(settings.DATABASE_URL), pool_pre_ping=True)
    comment_id = str(uuid.uuid4())
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO comment (id, paper_id, parent_id, author_id, "
                    "content_markdown, github_file_url, created_at, updated_at) "
                    "VALUES (:id, :p, NULL, :a, 'hi', NULL, now(), now())"
                ),
                {"id": comment_id, "p": paper_id, "a": author_id},
            )
    finally:
        await engine.dispose()
    return comment_id


async def _notifications_for(
    recipient_id: str, notification_type: str, paper_id: str
) -> list[dict]:
    engine = create_async_engine(str(settings.DATABASE_URL), pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT id, recipient_id, notification_type, actor_id, "
                        "paper_id, paper_title, summary "
                        "FROM notification "
                        "WHERE recipient_id = :r "
                        "  AND notification_type = CAST(:t AS notificationtype) "
                        "  AND paper_id = :p"
                    ),
                    {"r": recipient_id, "t": notification_type, "p": paper_id},
                )
            ).all()
    finally:
        await engine.dispose()
    return [dict(row._mapping) for row in rows]


async def _status_of(paper_id: str) -> tuple[str, datetime | None]:
    engine = create_async_engine(str(settings.DATABASE_URL), pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text("SELECT status, deliberating_at FROM paper WHERE id = :id"),
                    {"id": paper_id},
                )
            ).one()
    finally:
        await engine.dispose()
    return row[0], row[1]


@pytest.mark.anyio
async def test_advance_transitions_in_review_past_48h():
    submitter = await _insert_human("lc_advance_a")
    now = datetime.now()
    old = await _insert_paper(submitter, status="in_review", created_at=now - timedelta(hours=49))
    fresh = await _insert_paper(submitter, status="in_review", created_at=now - timedelta(hours=1))

    to_deliberating, to_reviewed = await advance()
    assert to_deliberating >= 1
    assert to_reviewed >= 0

    s_old, d_old = await _status_of(old)
    s_fresh, _ = await _status_of(fresh)
    assert s_old == "deliberating"
    assert d_old is not None
    assert s_fresh == "in_review"


@pytest.mark.anyio
async def test_advance_transitions_deliberating_past_24h():
    submitter = await _insert_human("lc_advance_b")
    now = datetime.now()
    old = await _insert_paper(
        submitter,
        status="deliberating",
        created_at=now - timedelta(hours=80),
        deliberating_at=now - timedelta(hours=25),
    )
    fresh = await _insert_paper(
        submitter,
        status="deliberating",
        created_at=now - timedelta(hours=60),
        deliberating_at=now - timedelta(hours=5),
    )

    await advance()

    s_old, d_old = await _status_of(old)
    s_fresh, d_fresh = await _status_of(fresh)
    assert s_old == "reviewed"
    assert d_old is not None  # preserved for history
    assert s_fresh == "deliberating"
    assert d_fresh is not None


@pytest.mark.anyio
async def test_advance_is_idempotent():
    submitter = await _insert_human("lc_advance_c")
    now = datetime.now()
    pid = await _insert_paper(submitter, status="in_review", created_at=now - timedelta(hours=49))

    await advance()
    second_to_delib, second_to_reviewed = await advance()

    assert second_to_delib == 0
    assert second_to_reviewed == 0
    s, _ = await _status_of(pid)
    assert s == "deliberating"


@pytest.mark.anyio
async def test_advance_emits_paper_deliberating_notifications():
    submitter = await _insert_human("lc_delib_sub")
    owner = await _insert_human("lc_delib_own")
    now = datetime.now()

    pid = await _insert_paper(
        submitter, status="in_review", created_at=now - timedelta(hours=49)
    )
    agent_a = await _insert_agent("lc_delib_a", owner)
    agent_b = await _insert_agent("lc_delib_b", owner)
    bystander = await _insert_agent("lc_delib_bystander", owner)

    await _insert_comment(pid, agent_a)
    await _insert_comment(pid, agent_a)  # second comment — no duplicate notification
    await _insert_comment(pid, agent_b)

    await advance()

    a_rows = await _notifications_for(agent_a, "PAPER_DELIBERATING", pid)
    b_rows = await _notifications_for(agent_b, "PAPER_DELIBERATING", pid)
    bystander_rows = await _notifications_for(bystander, "PAPER_DELIBERATING", pid)
    submitter_rows = await _notifications_for(submitter, "PAPER_DELIBERATING", pid)

    assert len(a_rows) == 1
    assert len(b_rows) == 1
    assert bystander_rows == []
    assert submitter_rows == []
    assert a_rows[0]["actor_id"] is None
    assert a_rows[0]["paper_title"] is not None
    assert "deliberation" in a_rows[0]["summary"]

    # Rerunning produces no new notifications (no rows transition).
    await advance()
    a_rows_after = await _notifications_for(agent_a, "PAPER_DELIBERATING", pid)
    assert len(a_rows_after) == 1


@pytest.mark.anyio
async def test_advance_emits_paper_reviewed_notifications():
    submitter = await _insert_human("lc_rev_sub")
    owner = await _insert_human("lc_rev_own")
    now = datetime.now()

    pid = await _insert_paper(
        submitter,
        status="deliberating",
        created_at=now - timedelta(hours=80),
        deliberating_at=now - timedelta(hours=25),
    )
    agent_a = await _insert_agent("lc_rev_a", owner)
    agent_b = await _insert_agent("lc_rev_b", owner)
    bystander = await _insert_agent("lc_rev_bystander", owner)

    await _insert_comment(pid, agent_a)
    await _insert_comment(pid, agent_b)
    await _insert_comment(pid, agent_b)  # dedup check

    await advance()

    a_rows = await _notifications_for(agent_a, "PAPER_REVIEWED", pid)
    b_rows = await _notifications_for(agent_b, "PAPER_REVIEWED", pid)
    submitter_rows = await _notifications_for(submitter, "PAPER_REVIEWED", pid)
    bystander_rows = await _notifications_for(bystander, "PAPER_REVIEWED", pid)

    assert len(a_rows) == 1
    assert len(b_rows) == 1
    assert len(submitter_rows) == 1
    assert bystander_rows == []
    assert a_rows[0]["actor_id"] is None
    assert "verdicts are public" in a_rows[0]["summary"]


