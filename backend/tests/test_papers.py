"""Tests for paper submission access control + public visibility filters."""
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from tests.conftest import promote_to_superuser


_PAPER_PAYLOAD = {
    "title": "A test paper",
    "abstract": "An abstract.",
    "domain": "NLP",
}


def _unique_email(prefix: str = "papers") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"


def _unique_openreview_id(prefix: str = "Papers") -> str:
    safe = "".join(c for c in prefix if c.isalnum()) or "Papers"
    return f"~{safe.capitalize()}_{uuid.uuid4().hex[:8]}1"


async def _signup(client: AsyncClient, prefix: str) -> tuple[str, str]:
    """Create a human account, return (token, actor_id)."""
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


async def _register_agent(client: AsyncClient, prefix: str = "agent") -> str:
    """Sign up a human owner, then create an agent under that human."""
    signup_resp = await client.post(
        "/api/v1/auth/signup",
        json={
            "name": "Owner",
            "email": _unique_email(f"owner_{prefix}"),
            "password": "secure_password_123",
            "openreview_ids": [_unique_openreview_id(f"owner_{prefix}")],
        },
    )
    assert signup_resp.status_code == 201, signup_resp.text
    token = signup_resp.json()["access_token"]

    resp = await client.post(
        "/api/v1/auth/agents",
        json={
            "name": f"{prefix}_{uuid.uuid4().hex[:6]}",
            "github_repo": "https://github.com/example/agent",
        },
        headers={"Authorization": f"Bearer {token}"},
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


async def test_submit_paper_rejects_agent(client: AsyncClient):
    """Agents are structurally ineligible (is_superuser lives on HumanAccount only)."""
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


async def _set_paper_status(paper_id: str, status: str) -> None:
    engine = create_async_engine(str(settings.DATABASE_URL), pool_pre_ping=True)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE paper SET status = CAST(:s AS paperstatus) WHERE id = :id"
                ),
                {"s": status, "id": paper_id},
            )
    finally:
        await engine.dispose()


async def test_get_paper_detail_404s_for_failed_review(client: AsyncClient):
    token, actor_id = await _signup(client, "fr_detail")
    await promote_to_superuser(actor_id)
    create = await client.post(
        "/api/v1/papers/",
        json=_PAPER_PAYLOAD,
        headers={"Authorization": f"Bearer {token}"},
    )
    paper_id = create.json()["id"]
    await _set_paper_status(paper_id, "failed_review")

    resp = await client.get(f"/api/v1/papers/{paper_id}")
    assert resp.status_code == 404


async def test_papers_list_excludes_failed_review(client: AsyncClient):
    token, actor_id = await _signup(client, "fr_list")
    await promote_to_superuser(actor_id)
    create = await client.post(
        "/api/v1/papers/",
        json={**_PAPER_PAYLOAD, "title": "Hidden Paper For List"},
        headers={"Authorization": f"Bearer {token}"},
    )
    paper_id = create.json()["id"]
    await _set_paper_status(paper_id, "failed_review")

    resp = await client.get("/api/v1/papers/?limit=200")
    assert resp.status_code == 200
    titles = [p["title"] for p in resp.json()]
    assert "Hidden Paper For List" not in titles


async def test_paper_count_excludes_failed_review(client: AsyncClient):
    token, actor_id = await _signup(client, "fr_count")
    await promote_to_superuser(actor_id)
    before = (await client.get("/api/v1/papers/count")).json()["count"]

    create = await client.post(
        "/api/v1/papers/",
        json=_PAPER_PAYLOAD,
        headers={"Authorization": f"Bearer {token}"},
    )
    paper_id = create.json()["id"]
    after_create = (await client.get("/api/v1/papers/count")).json()["count"]
    assert after_create == before + 1

    await _set_paper_status(paper_id, "failed_review")
    after_fail = (await client.get("/api/v1/papers/count")).json()["count"]
    assert after_fail == before


async def _insert_verdict_directly(paper_id: str, author_id: str, score: float) -> None:
    engine = create_async_engine(str(settings.DATABASE_URL), pool_pre_ping=True)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO verdict (id, paper_id, author_id, content_markdown, "
                    "score, github_file_url, created_at, updated_at) VALUES "
                    "(:id, :pid, :aid, 'v', :s, "
                    "'https://github.com/test/agent/blob/main/v.md', now(), now())"
                ),
                {"id": str(uuid.uuid4()), "pid": paper_id, "aid": author_id, "s": score},
            )
    finally:
        await engine.dispose()


async def _make_agent(client: AsyncClient, owner_token: str, name: str) -> str:
    resp = await client.post(
        "/api/v1/auth/agents",
        json={"name": name, "github_repo": f"https://github.com/x/{name}"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_papers_response_includes_avg_verdict_score(client: AsyncClient):
    token, actor_id = await _signup(client, "avgr_sup")
    await promote_to_superuser(actor_id)
    owner_token, _ = await _signup(client, "avgr_own")
    a1 = await _make_agent(client, owner_token, f"avgr_a1_{uuid.uuid4().hex[:6]}")
    a2 = await _make_agent(client, owner_token, f"avgr_a2_{uuid.uuid4().hex[:6]}")

    create = await client.post(
        "/api/v1/papers/",
        json={**_PAPER_PAYLOAD, "title": f"AvgScored {uuid.uuid4().hex[:6]}"},
        headers={"Authorization": f"Bearer {token}"},
    )
    paper_id = create.json()["id"]
    await _insert_verdict_directly(paper_id, a1, 6.0)
    await _insert_verdict_directly(paper_id, a2, 8.0)
    await _set_paper_status(paper_id, "reviewed")

    body = (await client.get(f"/api/v1/papers/{paper_id}")).json()
    assert body["avg_verdict_score"] == pytest.approx(7.0)


@pytest.mark.parametrize("status", ["in_review", "deliberating"])
async def test_papers_detail_hides_avg_verdict_score_pre_review(client: AsyncClient, status: str):
    """Avg verdict score must NOT leak before a paper reaches `reviewed` —
    otherwise agents reviewing a deliberating paper can anchor on the running mean.
    """
    token, actor_id = await _signup(client, f"hide_d_{status}")
    await promote_to_superuser(actor_id)
    owner_token, _ = await _signup(client, f"hide_d_own_{status}")
    a1 = await _make_agent(client, owner_token, f"hide_d_a1_{uuid.uuid4().hex[:6]}")
    a2 = await _make_agent(client, owner_token, f"hide_d_a2_{uuid.uuid4().hex[:6]}")

    create = await client.post(
        "/api/v1/papers/",
        json={**_PAPER_PAYLOAD, "title": f"HideAvg {status} {uuid.uuid4().hex[:6]}"},
        headers={"Authorization": f"Bearer {token}"},
    )
    paper_id = create.json()["id"]
    await _insert_verdict_directly(paper_id, a1, 6.0)
    await _insert_verdict_directly(paper_id, a2, 8.0)
    await _set_paper_status(paper_id, status)

    body = (await client.get(f"/api/v1/papers/{paper_id}")).json()
    assert body["status"] == status
    assert body["avg_verdict_score"] is None


@pytest.mark.parametrize("status", ["in_review", "deliberating"])
async def test_papers_list_hides_avg_verdict_score_pre_review(client: AsyncClient, status: str):
    """List endpoint must also withhold avg_verdict_score for non-reviewed papers."""
    token, actor_id = await _signup(client, f"hide_l_{status}")
    await promote_to_superuser(actor_id)
    owner_token, _ = await _signup(client, f"hide_l_own_{status}")
    a1 = await _make_agent(client, owner_token, f"hide_l_a1_{uuid.uuid4().hex[:6]}")

    title = f"HideAvgList {status} {uuid.uuid4().hex[:6]}"
    create = await client.post(
        "/api/v1/papers/",
        json={**_PAPER_PAYLOAD, "title": title},
        headers={"Authorization": f"Bearer {token}"},
    )
    paper_id = create.json()["id"]
    await _insert_verdict_directly(paper_id, a1, 5.0)
    await _set_paper_status(paper_id, status)

    body = (await client.get("/api/v1/papers/?limit=200")).json()
    matching = [p for p in body if p["id"] == paper_id]
    assert len(matching) == 1, f"paper {paper_id} not in list response"
    assert matching[0]["avg_verdict_score"] is None


async def test_papers_status_filter_reviewed(client: AsyncClient):
    token, actor_id = await _signup(client, "stf")
    await promote_to_superuser(actor_id)

    in_review_paper = (await client.post(
        "/api/v1/papers/",
        json={**_PAPER_PAYLOAD, "title": f"StatusFilterIR {uuid.uuid4().hex[:6]}"},
        headers={"Authorization": f"Bearer {token}"},
    )).json()["id"]
    reviewed_paper = (await client.post(
        "/api/v1/papers/",
        json={**_PAPER_PAYLOAD, "title": f"StatusFilterR {uuid.uuid4().hex[:6]}"},
        headers={"Authorization": f"Bearer {token}"},
    )).json()["id"]
    await _set_paper_status(reviewed_paper, "reviewed")

    body = (await client.get("/api/v1/papers/?status=reviewed&limit=200")).json()
    ids = {p["id"] for p in body}
    assert reviewed_paper in ids
    assert in_review_paper not in ids


async def test_papers_invalid_status_returns_422(client: AsyncClient):
    resp = await client.get("/api/v1/papers/?status=garbage")
    assert resp.status_code == 422


async def test_papers_sort_by_avg_score_desc(client: AsyncClient):
    token, actor_id = await _signup(client, "savg")
    await promote_to_superuser(actor_id)
    owner_token, _ = await _signup(client, "savg_own")
    a1 = await _make_agent(client, owner_token, f"savg_a1_{uuid.uuid4().hex[:6]}")

    low = (await client.post(
        "/api/v1/papers/",
        json={**_PAPER_PAYLOAD, "title": f"AvgLow {uuid.uuid4().hex[:6]}"},
        headers={"Authorization": f"Bearer {token}"},
    )).json()["id"]
    high = (await client.post(
        "/api/v1/papers/",
        json={**_PAPER_PAYLOAD, "title": f"AvgHigh {uuid.uuid4().hex[:6]}"},
        headers={"Authorization": f"Bearer {token}"},
    )).json()["id"]
    await _insert_verdict_directly(low, a1, 3.0)
    await _insert_verdict_directly(high, a1, 9.0)
    await _set_paper_status(low, "reviewed")
    await _set_paper_status(high, "reviewed")

    body = (await client.get("/api/v1/papers/?status=reviewed&sort=avg_score&limit=200")).json()
    ids_in_order = [p["id"] for p in body]
    high_idx = ids_in_order.index(high)
    low_idx = ids_in_order.index(low)
    assert high_idx < low_idx, f"high-score paper should rank above low-score (got high={high_idx}, low={low_idx})"
