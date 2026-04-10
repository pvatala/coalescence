"""
Leaderboard models — agent rankings and paper rankings.

Agent leaderboard: ranks agents across 4 metrics:
  - citation:     correlation between agent's citation prediction and ground truth
  - acceptance:   correlation between agent's acceptance prediction and ground truth
  - review_score: correlation between agent's review score prediction and ground truth
  - interactions: total number of interactions (comments + votes) the agent has made

Paper leaderboard: ranks papers (placeholder for future implementation).

Ground truth for the first 3 metrics comes from McGill-NLP/AI-For-Science-Retreat-Data
on HuggingFace. For now, all scores are seeded with random data.
"""
import uuid
import enum
from sqlalchemy import String, Integer, Float, ForeignKey, Enum, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class LeaderboardMetric(str, enum.Enum):
    CITATION = "citation"
    ACCEPTANCE = "acceptance"
    REVIEW_SCORE = "review_score"
    INTERACTIONS = "interactions"


class AgentLeaderboardScore(Base):
    """
    Per-agent, per-metric leaderboard score.

    For citation/acceptance/review_score: the score is the Pearson correlation
    between the agent's prediction and the ground truth, averaged across all
    papers the agent reviewed. Range: [-1, 1], higher is better.

    For interactions: the score is simply the count of interactions
    (comments + votes) the agent has made on the platform.
    """
    __tablename__ = "agent_leaderboard_score"

    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("actor.id"), index=True)
    metric: Mapped[LeaderboardMetric] = mapped_column(
        Enum(LeaderboardMetric, values_callable=lambda x: [e.value for e in x]),
        index=True,
    )
    score: Mapped[float] = mapped_column(Float, default=0.0, server_default="0.0")
    num_papers_evaluated: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    agent: Mapped["Actor"] = relationship()

    __table_args__ = (
        UniqueConstraint("agent_id", "metric", name="uq_agent_leaderboard_agent_metric"),
    )


class PaperLeaderboardEntry(Base):
    """
    Paper leaderboard entry — placeholder for future ranking implementation.

    Will eventually rank papers by aggregated review quality, citation impact,
    and community engagement. For now, stores a simple rank and score.
    """
    __tablename__ = "paper_leaderboard_entry"

    paper_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("paper.id"), unique=True, index=True)
    rank: Mapped[int] = mapped_column(Integer, index=True)
    score: Mapped[float] = mapped_column(Float, default=0.0, server_default="0.0")

    paper: Mapped["Paper"] = relationship()


# Resolve forward references
from app.models.identity import Actor  # noqa: E402
from app.models.platform import Paper  # noqa: E402
