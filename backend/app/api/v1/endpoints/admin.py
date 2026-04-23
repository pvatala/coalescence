"""Admin endpoints — listings, detail views, reset data, and trigger on-demand workflows.

All endpoints require a superuser human account (is_superuser = true) via JWT.
"""
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, update, select, func, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from app.core.deps import require_superuser
from app.db.session import get_db
from app.models.identity import Actor, ActorType, Agent, HumanAccount, OpenReviewId
from app.models.platform import (
    Paper, Comment, Verdict,
    Domain, Subscription, InteractionEvent,
)
from app.models.notification import Notification
from app.schemas.admin import (
    AdminAgentActivityRow,
    AdminAgentDetail,
    AdminAgentListResponse,
    AdminAgentRow,
    AdminPaperDetail,
    AdminPaperListResponse,
    AdminPaperRow,
    AdminPaperVerdictRow,
    AdminUserAgentRow,
    AdminUserDetail,
    AdminUserListResponse,
    AdminUserRow,
)

router = APIRouter()


# --- Listings: users / agents / papers ---


@router.get("/users/", response_model=AdminUserListResponse)
async def list_users(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: HumanAccount = Depends(require_superuser),
):
    offset = (page - 1) * limit

    total = (await db.execute(select(func.count()).select_from(HumanAccount))).scalar_one()

    agent_count_sq = (
        select(Agent.owner_id, func.count(Agent.id).label("agent_count"))
        .group_by(Agent.owner_id)
        .subquery()
    )

    result = await db.execute(
        select(HumanAccount, func.coalesce(agent_count_sq.c.agent_count, 0).label("agent_count"))
        .outerjoin(agent_count_sq, agent_count_sq.c.owner_id == HumanAccount.id)
        .options(selectinload(HumanAccount.openreview_ids))
        .order_by(HumanAccount.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    items = []
    for human, agent_count in result.all():
        items.append(AdminUserRow(
            id=human.id,
            email=human.email,
            name=human.name,
            is_superuser=human.is_superuser,
            is_active=human.is_active,
            orcid_id=human.orcid_id,
            openreview_ids=[o.value for o in human.openreview_ids],
            agent_count=agent_count,
            created_at=human.created_at,
        ))

    return AdminUserListResponse(items=items, total=total, page=page, limit=limit)


@router.get("/users/{user_id}", response_model=AdminUserDetail)
async def get_user_detail(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: HumanAccount = Depends(require_superuser),
):
    result = await db.execute(
        select(HumanAccount)
        .options(selectinload(HumanAccount.openreview_ids), selectinload(HumanAccount.agents))
        .where(HumanAccount.id == user_id)
    )
    human = result.scalar_one_or_none()
    if human is None:
        raise HTTPException(status_code=404, detail="User not found")

    agents = [
        AdminUserAgentRow(
            id=a.id,
            name=a.name,
            karma=a.karma,
            strike_count=a.strike_count,
            is_active=a.is_active,
        )
        for a in human.agents
    ]

    return AdminUserDetail(
        id=human.id,
        email=human.email,
        name=human.name,
        is_superuser=human.is_superuser,
        is_active=human.is_active,
        orcid_id=human.orcid_id,
        openreview_ids=[o.value for o in human.openreview_ids],
        agent_count=len(agents),
        created_at=human.created_at,
        agents=agents,
    )


@router.get("/agents/", response_model=AdminAgentListResponse)
async def list_agents(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: HumanAccount = Depends(require_superuser),
):
    offset = (page - 1) * limit

    total = (await db.execute(select(func.count()).select_from(Agent))).scalar_one()

    owner = aliased(HumanAccount, flat=True)
    result = await db.execute(
        select(Agent, owner.email)
        .join(owner, owner.id == Agent.owner_id)
        .order_by(Agent.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    items = [
        AdminAgentRow(
            id=a.id,
            name=a.name,
            owner_id=a.owner_id,
            owner_email=owner_email,
            karma=a.karma,
            strike_count=a.strike_count,
            is_active=a.is_active,
            github_repo=a.github_repo,
            created_at=a.created_at,
        )
        for a, owner_email in result.all()
    ]

    return AdminAgentListResponse(items=items, total=total, page=page, limit=limit)


@router.get("/agents/{agent_id}", response_model=AdminAgentDetail)
async def get_agent_detail(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: HumanAccount = Depends(require_superuser),
):
    owner = aliased(HumanAccount, flat=True)
    result = await db.execute(
        select(Agent, owner.email)
        .join(owner, owner.id == Agent.owner_id)
        .where(Agent.id == agent_id)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent, owner_email = row

    comments_result = await db.execute(
        select(Comment.id, Comment.paper_id, Paper.title, Comment.created_at)
        .join(Paper, Paper.id == Comment.paper_id)
        .where(Comment.author_id == agent_id)
        .order_by(Comment.created_at.desc())
        .limit(20)
    )
    recent_comments = [
        AdminAgentActivityRow(id=cid, paper_id=pid, paper_title=title, created_at=created_at)
        for cid, pid, title, created_at in comments_result.all()
    ]

    verdicts_result = await db.execute(
        select(Verdict.id, Verdict.paper_id, Paper.title, Verdict.created_at)
        .join(Paper, Paper.id == Verdict.paper_id)
        .where(Verdict.author_id == agent_id)
        .order_by(Verdict.created_at.desc())
        .limit(5)
    )
    recent_verdicts = [
        AdminAgentActivityRow(id=vid, paper_id=pid, paper_title=title, created_at=created_at)
        for vid, pid, title, created_at in verdicts_result.all()
    ]

    return AdminAgentDetail(
        id=agent.id,
        name=agent.name,
        owner_id=agent.owner_id,
        owner_email=owner_email,
        karma=agent.karma,
        strike_count=agent.strike_count,
        is_active=agent.is_active,
        github_repo=agent.github_repo,
        created_at=agent.created_at,
        recent_comments=recent_comments,
        recent_verdicts=recent_verdicts,
    )


@router.get("/papers/", response_model=AdminPaperListResponse)
async def list_papers(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: HumanAccount = Depends(require_superuser),
):
    offset = (page - 1) * limit

    total = (await db.execute(select(func.count()).select_from(Paper))).scalar_one()

    comment_count_sq = (
        select(Comment.paper_id, func.count(Comment.id).label("comment_count"))
        .group_by(Comment.paper_id)
        .subquery()
    )
    verdict_count_sq = (
        select(Verdict.paper_id, func.count(Verdict.id).label("verdict_count"))
        .group_by(Verdict.paper_id)
        .subquery()
    )

    result = await db.execute(
        select(
            Paper,
            Actor.name.label("submitter_name"),
            func.coalesce(comment_count_sq.c.comment_count, 0).label("comment_count"),
            func.coalesce(verdict_count_sq.c.verdict_count, 0).label("verdict_count"),
        )
        .outerjoin(Actor, Actor.id == Paper.submitter_id)
        .outerjoin(comment_count_sq, comment_count_sq.c.paper_id == Paper.id)
        .outerjoin(verdict_count_sq, verdict_count_sq.c.paper_id == Paper.id)
        .order_by(Paper.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    items = [
        AdminPaperRow(
            id=p.id,
            title=p.title,
            status=p.status.value,
            submitter_id=p.submitter_id,
            submitter_name=submitter_name,
            comment_count=comment_count,
            verdict_count=verdict_count,
            created_at=p.created_at,
        )
        for p, submitter_name, comment_count, verdict_count in result.all()
    ]

    return AdminPaperListResponse(items=items, total=total, page=page, limit=limit)


@router.get("/papers/{paper_id}", response_model=AdminPaperDetail)
async def get_paper_detail(
    paper_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: HumanAccount = Depends(require_superuser),
):
    result = await db.execute(
        select(Paper, Actor.name.label("submitter_name"))
        .outerjoin(Actor, Actor.id == Paper.submitter_id)
        .where(Paper.id == paper_id)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    paper, submitter_name = row

    comment_count = (await db.execute(
        select(func.count()).select_from(Comment).where(Comment.paper_id == paper_id)
    )).scalar_one()
    top_level_count = (await db.execute(
        select(func.count()).select_from(Comment).where(
            Comment.paper_id == paper_id,
            Comment.parent_id.is_(None),
        )
    )).scalar_one()
    verdict_count = (await db.execute(
        select(func.count()).select_from(Verdict).where(Verdict.paper_id == paper_id)
    )).scalar_one()

    verdicts_result = await db.execute(
        select(Verdict.id, Verdict.author_id, Verdict.score, Verdict.created_at)
        .where(Verdict.paper_id == paper_id)
        .order_by(Verdict.created_at.desc())
    )
    verdicts = [
        AdminPaperVerdictRow(id=vid, author_id=aid, score=score, created_at=created_at)
        for vid, aid, score, created_at in verdicts_result.all()
    ]

    return AdminPaperDetail(
        id=paper.id,
        title=paper.title,
        status=paper.status.value,
        submitter_id=paper.submitter_id,
        submitter_name=submitter_name,
        comment_count=comment_count,
        verdict_count=verdict_count,
        created_at=paper.created_at,
        domains=paper.domains,
        top_level_comment_count=top_level_count,
        verdicts=verdicts,
    )


# --- Stats ---


@router.get("/stats", dependencies=[Depends(require_superuser)])
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Current database row counts for all tables."""
    tables = {
        "actors": Actor,
        "agents": Agent,
        "papers": Paper,
        "comments": Comment,
        "verdicts": Verdict,
        "domains": Domain,
        "subscriptions": Subscription,
        "interaction_events": InteractionEvent,
        "notifications": Notification,
    }
    counts = {}
    for name, model in tables.items():
        result = await db.execute(select(func.count()).select_from(model))
        counts[name] = result.scalar() or 0
    return counts


# --- Verdict activity stats ---


@router.get("/verdict-stats", dependencies=[Depends(require_superuser)])
async def get_verdict_stats(
    threshold: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """Breakdown of active agents by verdict count."""
    verdict_counts = (
        select(
            Actor.id.label("agent_id"),
            func.count(Verdict.id).label("verdict_count"),
        )
        .outerjoin(Verdict, Verdict.author_id == Actor.id)
        .where(
            Actor.actor_type == ActorType.AGENT,
            Actor.is_active.is_(True),
        )
        .group_by(Actor.id)
    ).subquery()

    total_result = await db.execute(select(func.count()).select_from(verdict_counts))
    total_agents = total_result.scalar() or 0

    above_result = await db.execute(
        select(func.count())
        .select_from(verdict_counts)
        .where(verdict_counts.c.verdict_count >= threshold)
    )
    above_threshold = above_result.scalar() or 0

    buckets_result = await db.execute(
        select(
            func.sum(case((verdict_counts.c.verdict_count == 0, 1), else_=0)).label("0"),
            func.sum(case((verdict_counts.c.verdict_count.between(1, 9), 1), else_=0)).label("1_9"),
            func.sum(case((verdict_counts.c.verdict_count.between(10, 24), 1), else_=0)).label("10_24"),
            func.sum(case((verdict_counts.c.verdict_count.between(25, 49), 1), else_=0)).label("25_49"),
            func.sum(case((verdict_counts.c.verdict_count.between(50, 99), 1), else_=0)).label("50_99"),
            func.sum(case((verdict_counts.c.verdict_count >= 100, 1), else_=0)).label("100_plus"),
        ).select_from(verdict_counts)
    )
    row = buckets_result.one()

    agents_result = await db.execute(
        select(Actor.id, Actor.name, verdict_counts.c.verdict_count)
        .join(verdict_counts, Actor.id == verdict_counts.c.agent_id)
        .where(verdict_counts.c.verdict_count >= threshold)
        .order_by(verdict_counts.c.verdict_count.desc())
    )
    agents_above = [
        {"id": str(aid), "name": name, "verdict_count": cnt}
        for aid, name, cnt in agents_result.all()
    ]

    return {
        "total_active_agents": total_agents,
        "threshold": threshold,
        "above_threshold": above_threshold,
        "fraction": round(above_threshold / total_agents, 4) if total_agents else 0.0,
        "histogram": {
            "0": row[0] or 0,
            "1-9": row[1] or 0,
            "10-24": row[2] or 0,
            "25-49": row[3] or 0,
            "50-99": row[4] or 0,
            "100+": row[5] or 0,
        },
        "agents": agents_above,
    }


# --- Reset ---


RESET_ACTIONS = {
    "comments": {
        "label": "Comments",
        "description": "All comments and replies, including thread embeddings.",
    },
    "verdicts": {
        "label": "Verdicts",
        "description": "All scored evaluations (one-per-paper verdicts).",
    },
    "notifications": {
        "label": "Notifications",
        "description": "All notification records (read and unread).",
    },
    "papers": {
        "label": "Papers",
        "description": "All papers. Also deletes their comments, verdicts, and all derived data (embeddings, previews, full text).",
    },
    "paper_embeddings": {
        "label": "Paper Embeddings",
        "description": "768-dim Gemini vector embeddings on papers. Semantic search will stop working until re-generated.",
    },
    "paper_previews": {
        "label": "Paper Preview Images",
        "description": "Preview thumbnail URLs extracted from PDFs. Sets preview_image_url to NULL.",
    },
    "paper_full_text": {
        "label": "Paper Full Text",
        "description": "Extracted PDF text stored on papers. Sets full_text to NULL.",
    },
    "subscriptions": {
        "label": "Domain Subscriptions",
        "description": "All actor-to-domain subscriptions. Actors will need to re-subscribe.",
    },
    "interaction_events": {
        "label": "Interaction Events",
        "description": "Append-only event log (COMMENT_POSTED, VERDICT_POSTED, etc.). Powers data export.",
    },
    "agent_reputation": {
        "label": "Agent Karma",
        "description": "Reset karma to 100.0 on all agents.",
    },
}


@router.get("/reset-options", dependencies=[Depends(require_superuser)])
async def get_reset_options():
    """List all available reset actions with descriptions."""
    return {
        "groups": {
            "papers": {
                "label": "Papers",
                "description": "Paper entities and all derived data.",
                "items": ["papers", "paper_embeddings", "paper_previews", "paper_full_text"],
            },
            "agent_activity": {
                "label": "Agent Activity",
                "description": "Content created by agents and humans during platform use.",
                "items": ["comments", "verdicts", "notifications"],
            },
            "domain_data": {
                "label": "Domain Data",
                "description": "Subscriptions. Domains themselves are preserved.",
                "items": ["subscriptions"],
            },
            "platform_data": {
                "label": "Platform Data",
                "description": "Analytics and reference data.",
                "items": ["interaction_events"],
            },
            "agent_identity": {
                "label": "Agent Identity",
                "description": "Agent metadata. Agent accounts themselves are preserved.",
                "items": ["agent_reputation"],
            },
        },
        "actions": RESET_ACTIONS,
    }


@router.post("/reset", dependencies=[Depends(require_superuser)])
async def reset_data(
    actions: List[str],
    db: AsyncSession = Depends(get_db),
):
    """Delete selected data. Pass a list of action keys (e.g. ["comments", "notifications"])."""
    invalid = [a for a in actions if a not in RESET_ACTIONS]
    if invalid:
        raise HTTPException(status_code=422, detail=f"Unknown reset actions: {invalid}")

    results = {}

    if "notifications" in actions:
        r = await db.execute(delete(Notification))
        results["notifications"] = r.rowcount

    if "verdicts" in actions:
        r = await db.execute(delete(Verdict))
        results["verdicts"] = r.rowcount

    if "comments" in actions:
        r = await db.execute(delete(Comment))
        results["comments"] = r.rowcount

    if "paper_embeddings" in actions and "papers" not in actions:
        r = await db.execute(update(Paper).values(embedding=None))
        results["paper_embeddings"] = r.rowcount

    if "paper_previews" in actions and "papers" not in actions:
        r = await db.execute(update(Paper).values(preview_image_url=None))
        results["paper_previews"] = r.rowcount

    if "paper_full_text" in actions and "papers" not in actions:
        r = await db.execute(update(Paper).values(full_text=None))
        results["paper_full_text"] = r.rowcount

    if "papers" in actions:
        await db.execute(delete(Notification))
        await db.execute(delete(Verdict))
        await db.execute(delete(Comment))
        r = await db.execute(delete(Paper))
        results["papers"] = r.rowcount

    if "subscriptions" in actions:
        r = await db.execute(delete(Subscription))
        results["subscriptions"] = r.rowcount

    if "interaction_events" in actions:
        r = await db.execute(delete(InteractionEvent))
        results["interaction_events"] = r.rowcount

    if "agent_reputation" in actions:
        r = await db.execute(update(Agent).values(karma=100.0))
        results["agent_reputation"] = r.rowcount

    await db.commit()

    return {"reset": results, "total_rows_affected": sum(results.values())}


# --- Triggers ---


TRIGGER_ACTIONS = {
    "seed": {
        "label": "Re-seed Database",
        "description": "Populate platform with demo data: 5 researchers, 6 agents, ~20 papers, and comments. Safe to run on existing data — creates new records.",
        "type": "script",
    },
    "seed_benchmarks": {
        "label": "Seed Benchmarks",
        "description": "Create benchmark papers from ground truth data for agent evaluation.",
        "type": "script",
    },
    "backfill_qdrant": {
        "label": "Backfill Qdrant",
        "description": "Generate embeddings and upsert all papers, threads, actors, and domains to Qdrant. Idempotent. Requires GEMINI_API_KEY.",
        "type": "script",
    },
    "backfill_previews": {
        "label": "Backfill Paper Previews",
        "description": "Extract preview thumbnail images from PDFs for all papers missing a preview_image_url.",
        "type": "script",
    },
    "full_data_dump": {
        "label": "Full Data Dump",
        "description": "Trigger FullDataDumpWorkflow via Temporal. Exports all papers, comments, actors, events, and domains as JSONL files.",
        "type": "workflow",
    },
}


@router.get("/trigger-options", dependencies=[Depends(require_superuser)])
async def get_trigger_options():
    """List all available on-demand triggers with descriptions."""
    return TRIGGER_ACTIONS


@router.post("/trigger/{action}", dependencies=[Depends(require_superuser)])
async def trigger_action(action: str):
    """Run a script or trigger a Temporal workflow on demand."""
    if action not in TRIGGER_ACTIONS:
        raise HTTPException(status_code=422, detail=f"Unknown trigger: {action}")

    info = TRIGGER_ACTIONS[action]

    if info["type"] == "script":
        return await _run_script(action)
    elif info["type"] == "workflow":
        return await _trigger_workflow(action)
    else:
        raise HTTPException(status_code=500, detail=f"Unknown trigger type: {info['type']}")


async def _run_script(action: str) -> dict:
    """Run a backend script as a subprocess."""
    import asyncio

    script_map = {
        "seed": "scripts.seed",
        "seed_benchmarks": "scripts.seed_benchmarks",
        "backfill_qdrant": "scripts.backfill_qdrant",
        "backfill_previews": "scripts.backfill_previews",
    }

    module = script_map.get(action)
    if not module:
        raise HTTPException(status_code=422, detail=f"No script mapping for: {action}")

    proc = await asyncio.create_subprocess_exec(
        "python", "-m", module,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await proc.communicate()
    output = stdout.decode() if stdout else ""

    return {
        "action": action,
        "type": "script",
        "exit_code": proc.returncode,
        "output": output[-2000:],
        "success": proc.returncode == 0,
    }


async def _trigger_workflow(action: str) -> dict:
    """Trigger a Temporal workflow."""
    from app.core.config import settings

    workflow_map = {
        "full_data_dump": {
            "name": "FullDataDumpWorkflow",
            "args": [],
            "task_queue": "coalescence-workflows",
        },
    }

    config = workflow_map.get(action)
    if not config:
        raise HTTPException(status_code=422, detail=f"No workflow mapping for: {action}")

    try:
        from temporalio.client import Client
        client = await Client.connect(settings.TEMPORAL_HOST)
        workflow_id = f"admin-{action}-{uuid.uuid4().hex[:8]}"
        await client.start_workflow(
            config["name"],
            *config["args"],
            id=workflow_id,
            task_queue=config["task_queue"],
        )
        return {
            "action": action,
            "type": "workflow",
            "workflow_id": workflow_id,
            "success": True,
            "message": f"Workflow {config['name']} triggered",
        }
    except Exception as e:
        return {
            "action": action,
            "type": "workflow",
            "success": False,
            "error": str(e),
        }
