"""Build a frozen *paper-centric* annotation batch.

Builds a **shared pool** of papers via a Mixed-Integer Program (PuLP +
CBC): every eligible agent gets exactly K reviewed papers in their
slate, each (agent, paper) tuple contributes at most ``cap`` comments
to annotate, and every pool paper has at least
``min_comments_per_paper`` capped comments to annotate. The objective
minimizes the pool size so annotators read as few distinct papers as
possible.

Usage:
    python -m scripts.build_annotation_batch \\
      --name v3-2026-05-13 \\
      --seed 0 \\
      --min-papers 20 \\
      --sample-size 6 \\
      --cap 2 \\
      --min-comments-per-paper 3 \\
      --annotators alice@x.com,bob@x.com \\
      --annotators-per-paper 2 \\
      [--dry-run]

    # Dry-run with synthetic annotators (no DB entries needed):
    python -m scripts.build_annotation_batch \\
      --name dry --seed 0 --sample-size 6 --cap 2 \\
      --min-comments-per-paper 3 --n-annotators 14 --dry-run

Eligibility: agents with ``>= --min-papers`` distinct ``reviewed``
papers they commented on.

``--seed`` is recorded on ``annotation_batch.random_seed`` for audit
only — the MIP is deterministic, so the seed does not affect pool
composition.
"""
import argparse
import asyncio
import json
import math
import statistics
import uuid
from collections import Counter
from dataclasses import dataclass

import pulp
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.core.config import settings


SELECT_ELIGIBLE_AGENTS_SQL = """
SELECT
    a.id,
    actor.name,
    COUNT(DISTINCT p.id) AS reviewed_paper_count
FROM agent a
JOIN actor ON actor.id = a.id
JOIN comment c ON c.author_id = a.id
JOIN paper p ON p.id = c.paper_id AND p.status = 'reviewed'
GROUP BY a.id, actor.name
HAVING COUNT(DISTINCT p.id) >= :min_papers
ORDER BY a.id ASC
"""

SELECT_REVIEWED_PAPERS_FOR_AGENT_SQL = """
SELECT DISTINCT p.id
FROM paper p
JOIN comment c ON c.paper_id = p.id
WHERE c.author_id = :agent_id AND p.status = 'reviewed'
ORDER BY p.id ASC
"""

SELECT_AGENT_PAPER_COMMENT_COUNTS_SQL = """
SELECT c.author_id, c.paper_id, COUNT(*) AS n_comments
FROM comment c
JOIN paper p ON p.id = c.paper_id AND p.status = 'reviewed'
JOIN agent a ON a.id = c.author_id
GROUP BY c.author_id, c.paper_id
"""

SELECT_VERDICT_SCORES_FOR_AGENT_SQL = """
SELECT v.score
FROM verdict v
JOIN paper p ON p.id = v.paper_id
WHERE v.author_id = :agent_id AND p.status = 'reviewed'
"""

SELECT_HUMAN_BY_EMAIL_SQL = """
SELECT id FROM human_account WHERE email = :email
"""

SELECT_BATCH_BY_NAME_SQL = """
SELECT id FROM annotation_batch WHERE name = :name
"""


@dataclass
class Plan:
    eligible_agents: list[tuple[uuid.UUID, str, int]]
    agent_papers: dict[uuid.UUID, list[uuid.UUID]]
    comment_counts: dict[tuple[uuid.UUID, uuid.UUID], int]
    pool: list[uuid.UUID]
    agent_samples: dict[uuid.UUID, list[uuid.UUID]]
    histograms: dict[uuid.UUID, tuple[list[dict], int]]
    paper_assignments: dict[uuid.UUID, list[uuid.UUID]]
    annotator_emails: list[str]
    annotator_ids: list[uuid.UUID]
    cap: int
    min_comments_per_paper: int


def _histogram_bins(scores: list[float]) -> list[dict]:
    bins = [0] * 10
    for s in scores:
        idx = int(math.floor(s))
        if idx < 0:
            idx = 0
        if idx > 9:
            idx = 9
        bins[idx] += 1
    return [{"bin": i, "count": bins[i]} for i in range(10)]


async def _resolve_annotators(
    conn: AsyncConnection, emails: list[str]
) -> list[uuid.UUID]:
    ids: list[uuid.UUID] = []
    for email in emails:
        row = (
            await conn.execute(text(SELECT_HUMAN_BY_EMAIL_SQL), {"email": email})
        ).one_or_none()
        if row is None:
            raise RuntimeError(f"annotator email not found: {email}")
        ids.append(row[0])
    return ids


def _mip_pool(
    agent_order: list[uuid.UUID],
    agent_papers: dict[uuid.UUID, list[uuid.UUID]],
    comment_counts: dict[tuple[uuid.UUID, uuid.UUID], int],
    sample_size: int,
    cap: int,
    min_comments_per_paper: int,
) -> tuple[list[uuid.UUID], dict[uuid.UUID, list[uuid.UUID]]]:
    """Return (pool, per-agent samples) by solving a MIP.

    For each agent ``a`` and paper ``p ∈ papers(a)``, binary ``x[a, p]``
    indicates ``p`` is in ``a``'s slate. Binary ``z[p]`` indicates ``p``
    is in the pool. Each agent picks exactly ``sample_size`` papers;
    each pool paper accumulates ``>= min_comments_per_paper`` capped
    comments across its agents. Objective: minimize the pool size.

    The returned pool and each agent's sample are sorted by UUID for
    determinism.
    """
    for agent_id in agent_order:
        n_have = len(agent_papers[agent_id])
        if n_have < sample_size:
            raise RuntimeError(
                f"agent {agent_id} has {n_have} reviewed papers, "
                f"needs >= K={sample_size} to be included"
            )

    all_papers: set[uuid.UUID] = set()
    for agent_id in agent_order:
        all_papers.update(agent_papers[agent_id])
    papers_sorted = sorted(all_papers)

    prob = pulp.LpProblem("annotation_pool", pulp.LpMinimize)

    x: dict[tuple[uuid.UUID, uuid.UUID], pulp.LpVariable] = {}
    for agent_id in agent_order:
        for paper_id in agent_papers[agent_id]:
            x[(agent_id, paper_id)] = pulp.LpVariable(
                f"x_{agent_id.hex}_{paper_id.hex}", cat=pulp.LpBinary
            )

    z: dict[uuid.UUID, pulp.LpVariable] = {
        paper_id: pulp.LpVariable(f"z_{paper_id.hex}", cat=pulp.LpBinary)
        for paper_id in papers_sorted
    }

    prob += pulp.lpSum(z.values())

    for agent_id in agent_order:
        prob += (
            pulp.lpSum(x[(agent_id, p)] for p in agent_papers[agent_id])
            == sample_size,
            f"slate_size_{agent_id.hex}",
        )

    for (agent_id, paper_id), var in x.items():
        prob += (
            var <= z[paper_id],
            f"slate_subset_pool_{agent_id.hex}_{paper_id.hex}",
        )

    agents_with_paper: dict[uuid.UUID, list[uuid.UUID]] = {p: [] for p in papers_sorted}
    for agent_id in agent_order:
        for paper_id in agent_papers[agent_id]:
            agents_with_paper[paper_id].append(agent_id)

    for paper_id in papers_sorted:
        contribs = []
        for agent_id in agents_with_paper[paper_id]:
            raw = comment_counts.get((agent_id, paper_id), 0)
            c_capped = min(cap, raw)
            if c_capped > 0:
                contribs.append(c_capped * x[(agent_id, paper_id)])
        prob += (
            pulp.lpSum(contribs) >= min_comments_per_paper * z[paper_id],
            f"min_comments_{paper_id.hex}",
        )

    solver = pulp.PULP_CBC_CMD(msg=0)
    status = prob.solve(solver)
    if pulp.LpStatus[status] != "Optimal":
        raise RuntimeError(
            f"MIP solver failed: status={pulp.LpStatus[status]}. "
            f"Check that every agent has >= K papers and each paper "
            f"can plausibly accumulate >= min_comments_per_paper "
            f"capped comments."
        )

    pool = sorted([p for p, var in z.items() if var.value() > 0.5])

    samples: dict[uuid.UUID, list[uuid.UUID]] = {}
    for agent_id in agent_order:
        picked = sorted(
            p
            for p in agent_papers[agent_id]
            if x[(agent_id, p)].value() > 0.5
        )
        samples[agent_id] = picked

    return pool, samples


def _assign_annotators(
    pool: list[uuid.UUID],
    annotator_ids: list[uuid.UUID],
    annotators_per_paper: int,
) -> dict[uuid.UUID, list[uuid.UUID]]:
    """Round-robin: paper i gets annotators ``i % N`` ... ``(i+P-1) % N``.

    Distinct annotators per paper requires ``annotators_per_paper <= N``.
    """
    n = len(annotator_ids)
    if annotators_per_paper > n:
        raise RuntimeError(
            f"--annotators-per-paper={annotators_per_paper} > "
            f"len(annotators)={n}"
        )
    out: dict[uuid.UUID, list[uuid.UUID]] = {}
    for i, paper_id in enumerate(pool):
        out[paper_id] = [
            annotator_ids[(i + offset) % n]
            for offset in range(annotators_per_paper)
        ]
    return out


async def _build_plan(
    conn: AsyncConnection,
    *,
    min_papers: int,
    sample_size: int,
    cap: int,
    min_comments_per_paper: int,
    annotator_emails: list[str],
    annotator_ids: list[uuid.UUID],
    annotators_per_paper: int,
) -> Plan:
    rows = (
        await conn.execute(
            text(SELECT_ELIGIBLE_AGENTS_SQL), {"min_papers": min_papers}
        )
    ).all()
    eligible_agents = [(r[0], r[1], r[2]) for r in rows]

    agent_papers: dict[uuid.UUID, list[uuid.UUID]] = {}
    histograms: dict[uuid.UUID, tuple[list[dict], int]] = {}
    for agent_id, _name, _count in eligible_agents:
        paper_rows = (
            await conn.execute(
                text(SELECT_REVIEWED_PAPERS_FOR_AGENT_SQL),
                {"agent_id": agent_id},
            )
        ).all()
        agent_papers[agent_id] = [r[0] for r in paper_rows]

        score_rows = (
            await conn.execute(
                text(SELECT_VERDICT_SCORES_FOR_AGENT_SQL),
                {"agent_id": agent_id},
            )
        ).all()
        scores = [float(r[0]) for r in score_rows]
        histograms[agent_id] = (_histogram_bins(scores), len(scores))

    eligible_ids = {a[0] for a in eligible_agents}
    count_rows = (
        await conn.execute(text(SELECT_AGENT_PAPER_COMMENT_COUNTS_SQL))
    ).all()
    comment_counts: dict[tuple[uuid.UUID, uuid.UUID], int] = {}
    for author_id, paper_id, n in count_rows:
        if author_id in eligible_ids:
            comment_counts[(author_id, paper_id)] = int(n)

    agent_order = sorted(a[0] for a in eligible_agents)

    pool, samples = _mip_pool(
        agent_order,
        agent_papers,
        comment_counts,
        sample_size,
        cap,
        min_comments_per_paper,
    )

    paper_assignments = _assign_annotators(
        pool, annotator_ids, annotators_per_paper
    )

    return Plan(
        eligible_agents=eligible_agents,
        agent_papers=agent_papers,
        comment_counts=comment_counts,
        pool=pool,
        agent_samples=samples,
        histograms=histograms,
        paper_assignments=paper_assignments,
        annotator_emails=annotator_emails,
        annotator_ids=annotator_ids,
        cap=cap,
        min_comments_per_paper=min_comments_per_paper,
    )


def _print_plan(plan: Plan, *, name: str, sample_size: int) -> None:
    n_agents = len(plan.eligible_agents)
    n_pool = len(plan.pool)
    tuples: list[tuple[uuid.UUID, uuid.UUID]] = []
    for agent_id, papers in plan.agent_samples.items():
        for p in papers:
            tuples.append((agent_id, p))
    n_tuples = len(tuples)

    capped_per_paper: dict[uuid.UUID, int] = {p: 0 for p in plan.pool}
    for agent_id, paper_id in tuples:
        raw = plan.comment_counts.get((agent_id, paper_id), 0)
        capped_per_paper[paper_id] += min(plan.cap, raw)
    total_comments = sum(capped_per_paper.values())

    print(f"batch name:                 {name}")
    print(f"eligible agents:            {n_agents}")
    print(f"pool size:                  {n_pool}")
    print(f"(agent, paper) tuples:      {n_tuples}")
    print(f"total comments to annotate: {total_comments}")
    print(f"cap per (agent, paper):     {plan.cap}")
    print(f"min comments per paper:     {plan.min_comments_per_paper}")

    if capped_per_paper:
        values = list(capped_per_paper.values())
        print(
            "comments per paper:         "
            f"min={min(values)} median={statistics.median(values):.1f} "
            f"mean={statistics.mean(values):.2f} max={max(values)}"
        )
        hist = Counter(values)
        for n_comments in sorted(hist):
            print(f"  {n_comments} comments: {hist[n_comments]} papers")

    papers_per_agent = {a: len(s) for a, s in plan.agent_samples.items()}
    if papers_per_agent:
        pa_vals = list(papers_per_agent.values())
        print(
            "papers per agent:           "
            f"min={min(pa_vals)} max={max(pa_vals)} (expected K={sample_size})"
        )

    per_annotator: dict[uuid.UUID, int] = {aid: 0 for aid in plan.annotator_ids}
    for assigned in plan.paper_assignments.values():
        for aid in assigned:
            per_annotator[aid] += 1
    if plan.annotator_emails:
        print("papers per annotator:")
        for email, aid in zip(plan.annotator_emails, plan.annotator_ids):
            print(f"  {email}: {per_annotator[aid]}")
    else:
        print("papers per annotator (synthetic):")
        for i, aid in enumerate(plan.annotator_ids):
            print(f"  annotator[{i}]: {per_annotator[aid]}")


async def _persist(
    conn: AsyncConnection,
    plan: Plan,
    *,
    name: str,
    seed: int,
    min_papers: int,
    sample_size: int,
) -> uuid.UUID:
    existing = (
        await conn.execute(text(SELECT_BATCH_BY_NAME_SQL), {"name": name})
    ).one_or_none()
    if existing is not None:
        raise RuntimeError(f"annotation_batch with name={name!r} already exists")

    batch_id = uuid.uuid4()
    await conn.execute(
        text(
            "INSERT INTO annotation_batch "
            "(id, name, random_seed, min_papers_threshold, sample_size, "
            " created_at, updated_at) "
            "VALUES (:id, :name, :seed, :mp, :ss, now(), now())"
        ),
        {
            "id": batch_id,
            "name": name,
            "seed": seed,
            "mp": min_papers,
            "ss": sample_size,
        },
    )

    batch_paper_ids: dict[uuid.UUID, uuid.UUID] = {}
    for pool_index, paper_id in enumerate(plan.pool):
        bp_id = uuid.uuid4()
        batch_paper_ids[paper_id] = bp_id
        await conn.execute(
            text(
                "INSERT INTO annotation_batch_paper "
                "(id, batch_id, paper_id, pool_index, "
                " created_at, updated_at) "
                "VALUES (:id, :b, :p, :pi, now(), now())"
            ),
            {
                "id": bp_id,
                "b": batch_id,
                "p": paper_id,
                "pi": pool_index,
            },
        )

    for agent_id, _, _ in plan.eligible_agents:
        bins, total_verdicts = plan.histograms[agent_id]
        batch_agent_id = uuid.uuid4()
        await conn.execute(
            text(
                "INSERT INTO annotation_batch_agent "
                "(id, batch_id, agent_id, score_histogram_json, total_verdicts, "
                " created_at, updated_at) "
                "VALUES (:id, :batch_id, :agent_id, "
                "        CAST(:bins AS JSONB), :tv, now(), now())"
            ),
            {
                "id": batch_agent_id,
                "batch_id": batch_id,
                "agent_id": agent_id,
                "bins": json.dumps(bins),
                "tv": total_verdicts,
            },
        )

        for sample_index, paper_id in enumerate(plan.agent_samples[agent_id]):
            await conn.execute(
                text(
                    "INSERT INTO annotation_batch_agent_paper "
                    "(id, batch_agent_id, batch_paper_id, sample_index, "
                    " created_at, updated_at) "
                    "VALUES (:id, :ba, :bp, :si, now(), now())"
                ),
                {
                    "id": uuid.uuid4(),
                    "ba": batch_agent_id,
                    "bp": batch_paper_ids[paper_id],
                    "si": sample_index,
                },
            )

    if plan.annotator_emails:
        for paper_id, annotator_ids in plan.paper_assignments.items():
            bp_id = batch_paper_ids[paper_id]
            for annotator_id in annotator_ids:
                await conn.execute(
                    text(
                        "INSERT INTO annotation_assignment "
                        "(id, batch_id, annotator_id, batch_paper_id, "
                        " created_at, updated_at) "
                        "VALUES (:id, :b, :ann, :bp, now(), now())"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "b": batch_id,
                        "ann": annotator_id,
                        "bp": bp_id,
                    },
                )

    return batch_id


async def build(
    *,
    name: str,
    seed: int,
    min_papers: int,
    sample_size: int,
    cap: int = 2,
    min_comments_per_paper: int = 3,
    annotator_emails: list[str] | None = None,
    n_annotators: int | None = None,
    annotators_per_paper: int = 2,
    dry_run: bool,
) -> Plan:
    if n_annotators is not None and annotator_emails:
        raise RuntimeError(
            "--n-annotators and --annotators are mutually exclusive"
        )
    if n_annotators is None and not annotator_emails:
        raise RuntimeError("provide either --annotators or --n-annotators")
    if annotator_emails and len(annotator_emails) < annotators_per_paper:
        raise RuntimeError(
            f"need >= {annotators_per_paper} annotators "
            f"(--annotators-per-paper={annotators_per_paper})"
        )
    if n_annotators is not None and n_annotators < annotators_per_paper:
        raise RuntimeError(
            f"--n-annotators={n_annotators} < "
            f"--annotators-per-paper={annotators_per_paper}"
        )

    engine = create_async_engine(str(settings.DATABASE_URL), pool_pre_ping=True)
    try:
        async with engine.begin() as conn:
            if n_annotators is not None:
                annotator_ids = [uuid.uuid4() for _ in range(n_annotators)]
                emails: list[str] = []
            else:
                annotator_ids = await _resolve_annotators(conn, annotator_emails)
                emails = annotator_emails

            plan = await _build_plan(
                conn,
                min_papers=min_papers,
                sample_size=sample_size,
                cap=cap,
                min_comments_per_paper=min_comments_per_paper,
                annotator_emails=emails,
                annotator_ids=annotator_ids,
                annotators_per_paper=annotators_per_paper,
            )
            _print_plan(plan, name=name, sample_size=sample_size)

            if dry_run:
                print("(dry-run: no writes)")
                return plan

            batch_id = await _persist(
                conn,
                plan,
                name=name,
                seed=seed,
                min_papers=min_papers,
                sample_size=sample_size,
            )
            print(f"persisted annotation_batch id={batch_id}")
            return plan
    finally:
        await engine.dispose()


def _parse_emails(raw: str) -> list[str]:
    return [e.strip() for e in raw.split(",") if e.strip()]


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--name", required=True, help="unique batch name")
    p.add_argument("--seed", type=int, required=True, help="RNG seed")
    p.add_argument(
        "--min-papers",
        type=int,
        default=20,
        help="eligibility threshold (default 20)",
    )
    p.add_argument(
        "--sample-size",
        "-k",
        type=int,
        default=6,
        help="papers per agent (default 6)",
    )
    p.add_argument(
        "--cap",
        type=int,
        default=2,
        help="max comments annotated per (agent, paper) (default 2)",
    )
    p.add_argument(
        "--min-comments-per-paper",
        type=int,
        default=3,
        help="min capped comments per pool paper (default 3)",
    )
    annotator_group = p.add_mutually_exclusive_group(required=True)
    annotator_group.add_argument(
        "--annotators",
        type=_parse_emails,
        help="comma-separated annotator emails",
    )
    annotator_group.add_argument(
        "--n-annotators",
        type=int,
        help="number of synthetic annotators (dry-run only)",
    )
    p.add_argument(
        "--annotators-per-paper",
        type=int,
        default=2,
        help="number of annotators per pool paper (default 2)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="print plan and exit without writes",
    )
    return p


def main() -> None:
    args = _build_argparser().parse_args()
    asyncio.run(
        build(
            name=args.name,
            seed=args.seed,
            min_papers=args.min_papers,
            sample_size=args.sample_size,
            cap=args.cap,
            min_comments_per_paper=args.min_comments_per_paper,
            annotator_emails=args.annotators,
            n_annotators=args.n_annotators,
            annotators_per_paper=args.annotators_per_paper,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()
