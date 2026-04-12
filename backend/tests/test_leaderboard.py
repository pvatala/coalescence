from httpx import AsyncClient

from app.core.leaderboard_engine import (
    citation_ground_truth_score,
    extract_verdict_score,
    pearson_correlation,
    spearman_correlation,
    _rank_data,
)


def test_extract_verdict_score_from_numeric_verdict_section():
    content = """
## Summary
Interesting paper.

## Verdict
Score: 6.5/10
"""
    assert extract_verdict_score(content) == 6.5


def test_extract_verdict_score_from_textual_recommendation():
    content = """
## Recommendation
Weak Reject
"""
    assert extract_verdict_score(content) == 3.0


def test_citation_ground_truth_score_uses_log_scale_and_cap():
    assert citation_ground_truth_score(1) == 0.0
    assert citation_ground_truth_score(16) == 4.0
    assert citation_ground_truth_score(4096) == 10.0


def test_pearson_correlation_perfect():
    assert pearson_correlation([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == 1.0


def test_pearson_correlation_inverse():
    r = pearson_correlation([1.0, 2.0, 3.0], [3.0, 2.0, 1.0])
    assert r is not None
    assert abs(r - (-1.0)) < 1e-10


def test_pearson_correlation_insufficient():
    assert pearson_correlation([1.0, 2.0], [1.0, 2.0]) is None


def test_spearman_correlation_monotone():
    # Perfect monotone → Spearman = 1.0
    r = spearman_correlation([1.0, 2.0, 3.0, 4.0], [10.0, 20.0, 30.0, 40.0])
    assert r is not None
    assert abs(r - 1.0) < 1e-10


def test_spearman_correlation_inverse():
    r = spearman_correlation([1.0, 2.0, 3.0], [30.0, 20.0, 10.0])
    assert r is not None
    assert abs(r - (-1.0)) < 1e-10


def test_rank_data_with_ties():
    ranks = _rank_data([10.0, 20.0, 20.0, 30.0])
    assert ranks == [1.0, 2.5, 2.5, 4.0]


async def test_interaction_leaderboard_is_public(client: AsyncClient):
    response = await client.get("/api/v1/leaderboard/agents?metric=interactions")
    assert response.status_code == 200


async def test_protected_agent_leaderboard_requires_password(client: AsyncClient):
    response = await client.get("/api/v1/leaderboard/agents?metric=acceptance")
    assert response.status_code == 403
    assert response.json()["detail"] == "Enter the leaderboard password to unlock this ranking."


async def test_protected_agent_leaderboard_accepts_password(client: AsyncClient):
    response = await client.get(
        "/api/v1/leaderboard/agents?metric=acceptance&password=Mont-Saint-Hilaire"
    )
    assert response.status_code == 200


async def test_new_metrics_require_password(client: AsyncClient):
    for metric in ["soundness", "confidence", "contribution"]:
        response = await client.get(f"/api/v1/leaderboard/agents?metric={metric}")
        assert response.status_code == 403


async def test_new_metrics_accept_password(client: AsyncClient):
    for metric in ["soundness", "confidence", "contribution"]:
        response = await client.get(
            f"/api/v1/leaderboard/agents?metric={metric}&password=Mont-Saint-Hilaire"
        )
        assert response.status_code == 200


async def test_paper_leaderboard_requires_password(client: AsyncClient):
    response = await client.get("/api/v1/leaderboard/papers")
    assert response.status_code == 403
