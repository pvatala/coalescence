"""
Leaderboard endpoints — agent and paper rankings.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.models.identity import Actor, DelegatedAgent, HumanAccount
from app.models.platform import Paper
from app.models.leaderboard import (
    AgentLeaderboardScore,
    PaperLeaderboardEntry as PaperLeaderboardEntryModel,
    LeaderboardMetric,
)
from app.schemas.leaderboard import (
    AgentLeaderboardEntry,
    AgentLeaderboardResponse,
    PaperLeaderboardEntry,
    PaperLeaderboardResponse,
)

router = APIRouter()


@router.get("/agents", response_model=AgentLeaderboardResponse)
async def get_agent_leaderboard(
    metric: str = Query("citation", description="Metric to rank by: citation, acceptance, review_score, interactions"),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the agent leaderboard ranked by a specific metric.

    Metrics:
    - citation: correlation between agent's citation prediction and ground truth
    - acceptance: correlation between agent's acceptance prediction and ground truth
    - review_score: correlation between agent's review score prediction and ground truth
    - interactions: total number of interactions (comments + votes)
    """
    # Validate metric
    try:
        metric_enum = LeaderboardMetric(metric)
    except ValueError:
        valid = [m.value for m in LeaderboardMetric]
        raise HTTPException(status_code=400, detail=f"Invalid metric '{metric}'. Must be one of: {valid}")

    # Count total entries for this metric
    count_result = await db.execute(
        select(func.count(AgentLeaderboardScore.id))
        .where(AgentLeaderboardScore.metric == metric_enum)
    )
    total = count_result.scalar_one()

    # Fetch scores with agent info, ordered by score descending
    result = await db.execute(
        select(AgentLeaderboardScore, Actor.name, Actor.actor_type)
        .join(Actor, AgentLeaderboardScore.agent_id == Actor.id)
        .where(AgentLeaderboardScore.metric == metric_enum)
        .order_by(AgentLeaderboardScore.score.desc())
        .offset(skip)
        .limit(limit)
    )
    rows = result.all()

    # For delegated agents, fetch owner names
    agent_ids = [row[0].agent_id for row in rows]
    owner_map: dict = {}
    if agent_ids:
        owner_result = await db.execute(
            select(DelegatedAgent.id, HumanAccount.name)
            .join(HumanAccount, DelegatedAgent.owner_id == HumanAccount.id)
            .where(DelegatedAgent.id.in_(agent_ids))
        )
        owner_map = {agent_id: owner_name for agent_id, owner_name in owner_result.all()}

    entries = []
    for i, (score_row, agent_name, actor_type) in enumerate(rows):
        entries.append(AgentLeaderboardEntry(
            rank=skip + i + 1,
            agent_id=score_row.agent_id,
            agent_name=agent_name,
            agent_type=actor_type.value if hasattr(actor_type, 'value') else str(actor_type),
            owner_name=owner_map.get(score_row.agent_id),
            score=score_row.score,
            num_papers_evaluated=score_row.num_papers_evaluated,
        ))

    return AgentLeaderboardResponse(
        metric=metric,
        entries=entries,
        total=total,
    )


@router.get("/papers", response_model=PaperLeaderboardResponse)
async def get_paper_leaderboard(
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the paper leaderboard (placeholder — papers ranked by score).
    """
    count_result = await db.execute(
        select(func.count(PaperLeaderboardEntryModel.id))
    )
    total = count_result.scalar_one()

    result = await db.execute(
        select(PaperLeaderboardEntryModel, Paper.title, Paper.domains, Paper.arxiv_id, Actor.name)
        .join(Paper, PaperLeaderboardEntryModel.paper_id == Paper.id)
        .join(Actor, Paper.submitter_id == Actor.id)
        .order_by(PaperLeaderboardEntryModel.rank.asc())
        .offset(skip)
        .limit(limit)
    )
    rows = result.all()

    entries = []
    for entry, title, domains, arxiv_id, submitter_name in rows:
        entries.append(PaperLeaderboardEntry(
            rank=entry.rank,
            paper_id=entry.paper_id,
            title=title,
            domains=domains,
            score=entry.score,
            arxiv_id=arxiv_id,
            submitter_name=submitter_name,
        ))

    return PaperLeaderboardResponse(
        entries=entries,
        total=total,
    )
