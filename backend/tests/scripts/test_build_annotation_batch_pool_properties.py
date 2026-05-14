"""Property-style tests for the MIP pool builder.

Direct tests of the pure ``_mip_pool`` helper — no DB required.
"""
import uuid

import pytest

from scripts.build_annotation_batch import _mip_pool


def _ids(n: int) -> list[uuid.UUID]:
    return [uuid.uuid4() for _ in range(n)]


def _make_counts(
    agent_papers: dict[uuid.UUID, list[uuid.UUID]], n: int
) -> dict[tuple[uuid.UUID, uuid.UUID], int]:
    return {
        (a, p): n
        for a, papers in agent_papers.items()
        for p in papers
    }


def test_every_agent_gets_exactly_k_papers():
    K = 4
    cap = 2
    min_comments = 3

    shared = _ids(8)
    agents = _ids(5)
    agent_papers = {a: list(shared) for a in agents}
    counts = _make_counts(agent_papers, 5)

    pool, samples = _mip_pool(agents, agent_papers, counts, K, cap, min_comments)

    for a in agents:
        assert len(samples[a]) == K
        assert len(set(samples[a])) == K
        for p in samples[a]:
            assert p in pool


def test_pool_papers_meet_min_comments_constraint():
    K = 3
    cap = 2
    min_comments = 4

    shared = _ids(6)
    agents = _ids(4)
    agent_papers = {a: list(shared) for a in agents}
    counts = _make_counts(agent_papers, 10)

    pool, samples = _mip_pool(agents, agent_papers, counts, K, cap, min_comments)

    paper_capped: dict[uuid.UUID, int] = {p: 0 for p in pool}
    for a, picks in samples.items():
        for p in picks:
            raw = counts[(a, p)]
            paper_capped[p] += min(cap, raw)
    for p in pool:
        assert paper_capped[p] >= min_comments


def test_pool_is_minimized_on_hand_built_instance():
    """Three agents fully share six papers; with K=3, cap=2, min=4 the
    optimal pool has exactly 3 papers (3 agents × 2 capped comments = 6
    ≥ 4 per paper, and each agent needs exactly K=3 distinct picks)."""
    K = 3
    cap = 2
    min_comments = 4

    shared = _ids(6)
    a1, a2, a3 = _ids(3)
    agent_papers = {a1: list(shared), a2: list(shared), a3: list(shared)}
    counts = _make_counts(agent_papers, 5)

    pool, samples = _mip_pool(
        [a1, a2, a3], agent_papers, counts, K, cap, min_comments
    )

    assert len(pool) == K
    assert set(pool) <= set(shared)
    for a in (a1, a2, a3):
        assert set(samples[a]) == set(pool)


def test_single_agent_pool_equals_K_when_cap_meets_min():
    """One agent, cap=2, min_comments=2: each picked paper is covered by
    its own (capped=2) contribution alone, so the MIP picks exactly K
    papers."""
    K = 3
    cap = 2
    min_comments = 2

    a = uuid.uuid4()
    papers = _ids(5)
    agent_papers = {a: papers}
    counts = {(a, p): 4 for p in papers}

    pool, samples = _mip_pool([a], agent_papers, counts, K, cap, min_comments)

    assert len(pool) == K
    assert set(samples[a]) == set(pool)


def test_pool_deterministic_via_uuid_sort():
    K = 3
    cap = 2
    min_comments = 3

    shared = _ids(8)
    agents = _ids(3)
    agent_papers = {a: list(shared) for a in agents}
    counts = _make_counts(agent_papers, 5)

    pool_a, samples_a = _mip_pool(
        agents, agent_papers, counts, K, cap, min_comments
    )
    pool_b, samples_b = _mip_pool(
        agents, agent_papers, counts, K, cap, min_comments
    )
    assert pool_a == sorted(pool_a)
    assert pool_a == pool_b
    for a in agents:
        assert samples_a[a] == sorted(samples_a[a])
        assert samples_a[a] == samples_b[a]


def test_infeasible_when_agent_has_fewer_than_k_papers():
    K = 4
    cap = 2
    min_comments = 3

    a1 = uuid.uuid4()
    a2 = uuid.uuid4()
    papers_a1 = _ids(4)
    papers_a2 = _ids(2)
    agent_papers = {a1: papers_a1, a2: papers_a2}
    counts = _make_counts(agent_papers, 5)

    with pytest.raises(RuntimeError, match=str(a2)):
        _mip_pool([a1, a2], agent_papers, counts, K, cap, min_comments)


def test_disjoint_agents_pool_equals_n_agents_times_k():
    """Two agents with disjoint paper sets => pool = 2K because no
    sharing is possible. Each agent's K papers must each meet the
    min-comments constraint via that agent's own capped count."""
    K = 3
    cap = 3
    min_comments = 3

    a1 = uuid.uuid4()
    a2 = uuid.uuid4()
    papers_a1 = _ids(5)
    papers_a2 = _ids(5)
    agent_papers = {a1: papers_a1, a2: papers_a2}
    counts = _make_counts(agent_papers, 10)

    pool, samples = _mip_pool(
        [a1, a2], agent_papers, counts, K, cap, min_comments
    )
    assert len(pool) == 2 * K
