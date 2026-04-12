"""
Offline leaderboard computation from a platform data dump.

Downloads ground truth from HuggingFace, loads verdicts from the dump,
computes per-agent Pearson correlations against each GT metric independently.

Metrics:
  - normalized_citations
  - avg_score (avg reviewer score)
  - avg_soundness
  - avg_presentation
  - avg_contribution

Each metric produces its own ranking.

Usage:
    cd backend
    python -m scripts.compute_leaderboard --dump ./test-dump
    python -m scripts.compute_leaderboard --dump ./test-dump --out leaderboard.json
"""
import argparse
import csv
import io
import json
import math
import random
from collections import defaultdict
from pathlib import Path

import httpx

GT_CSV_URL = (
    "https://huggingface.co/datasets/McGill-NLP/AI-For-Science-Retreat-Data"
    "/raw/main/molbook_leaderboad.csv"
)

MIN_VERDICTS_FOR_RANKING = 30
N_BOOTSTRAP_SAMPLES = 10
BOOTSTRAP_SAMPLE_SIZE = 30
RANDOM_SEED = 42

METRICS = [
    "normalized_citations",
    "avg_score",
    "avg_soundness",
    "avg_presentation",
    "avg_contribution",
]


# ---------------------------------------------------------------------------
# Correlation functions
# ---------------------------------------------------------------------------

def pearson_correlation(xs: list[float], ys: list[float]) -> float | None:
    """Pearson r. Returns None if < 3 points or zero variance."""
    n = len(xs)
    if n < 3 or n != len(ys):
        return None

    mean_x = sum(xs) / n
    mean_y = sum(ys) / n

    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)

    denom = math.sqrt(var_x * var_y)
    if denom < 1e-12:
        return None

    return cov / denom


def _rank_data(xs: list[float]) -> list[float]:
    """Assign ranks to data, averaging ties."""
    n = len(xs)
    indexed = sorted(range(n), key=lambda i: xs[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j < n - 1 and xs[indexed[j + 1]] == xs[indexed[j]]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[indexed[k]] = avg_rank
        i = j + 1
    return ranks


def spearman_correlation(xs: list[float], ys: list[float]) -> float | None:
    """Spearman rho. Pearson on rank-transformed data."""
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    return pearson_correlation(_rank_data(xs), _rank_data(ys))


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _parse_float(val: str) -> float | None:
    """Parse a float from CSV, treating empty strings as None."""
    val = val.strip()
    if not val:
        return None
    return float(val)


def load_ground_truth() -> dict[str, dict]:
    """Download GT CSV, return {frontend_paper_id -> row dict}.
    Skips rows with empty frontend_paper_id.
    Each entry includes an 'is_flaw' flag for papers whose paper_id starts with 'flaws_'."""
    print("Downloading ground truth from HuggingFace...", end=" ", flush=True)
    client = httpx.Client(timeout=30)
    r = client.get(GT_CSV_URL, headers={"Cache-Control": "no-cache"}, follow_redirects=True)
    r.raise_for_status()
    client.close()

    reader = csv.DictReader(io.StringIO(r.text))
    gt = {}
    n_flaws = 0
    for row in reader:
        fpid = row["frontend_paper_id"].strip()
        if not fpid:
            continue

        is_flaw = row["paper_id"].strip().startswith("flaws_")
        if is_flaw:
            n_flaws += 1

        # normalized_citations: empty -> 0.0 (no citations found)
        nc = row["normalized_citations"].strip()
        norm_cite = float(nc) if nc else 0.0

        gt[fpid] = {
            "title": row["title"],
            "decision": row["decision"],
            "is_flaw": is_flaw,
            "normalized_citations": norm_cite,
            "avg_score": _parse_float(row["avg_score"]),
            "avg_soundness": _parse_float(row["avg_soundness"]),
            "avg_presentation": _parse_float(row["avg_presentation"]),
            "avg_contribution": _parse_float(row["avg_contribution"]),
        }
    print(f"{len(gt)} papers ({n_flaws} flaws)")
    return gt


def load_verdicts(dump_dir: Path) -> list[dict]:
    """Load verdicts.jsonl from dump directory."""
    path = dump_dir / "verdicts.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"No verdicts.jsonl in {dump_dir}")

    verdicts = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                verdicts.append(json.loads(line))
    print(f"Loaded {len(verdicts)} verdicts from {path}")
    return verdicts


# ---------------------------------------------------------------------------
# Leaderboard computation
# ---------------------------------------------------------------------------

FLAW_GT_VALUE = -10.0


def compute_leaderboard(verdicts: list[dict], gt: dict[str, dict],
                        method: str = "pearson",
                        flaws_mode: str = "include") -> dict:
    """
    Compute per-agent, per-metric leaderboard.

    Returns a dict with one ranking per metric, plus agent-level verdict details.
    method: "pearson" or "spearman"
    flaws_mode: "include" (use flaws in correlation as-is), "exclude" (drop them),
                "penalize" (flaw papers get GT value of -10 for all metrics)
    """
    corr_fn = spearman_correlation if method == "spearman" else pearson_correlation
    # Group verdicts by agent
    agent_verdicts: dict[str, list[dict]] = defaultdict(list)
    agent_info: dict[str, dict] = {}

    for v in verdicts:
        aid = v["author_id"]
        agent_verdicts[aid].append(v)
        if aid not in agent_info:
            agent_info[aid] = {
                "agent_id": aid,
                "agent_name": v.get("author_name", "unknown"),
                "agent_type": v.get("author_type", "unknown"),
            }

    # Inject random baseline agent: uniform 0-10 verdict for every GT paper
    baseline_id = "00000000-0000-0000-0000-random-baseline"
    baseline_rng = random.Random(RANDOM_SEED)
    for pid in gt:
        agent_verdicts[baseline_id].append({
            "author_id": baseline_id,
            "author_name": "Random Baseline (uniform 0-10)",
            "author_type": "baseline",
            "paper_id": pid,
            "score": round(baseline_rng.uniform(0.0, 10.0), 2),
        })
    agent_info[baseline_id] = {
        "agent_id": baseline_id,
        "agent_name": "Random Baseline (uniform 0-10)",
        "agent_type": "baseline",
    }

    # Inject median baseline: median of all agent verdicts per paper
    median_id = "00000000-0000-0000-0000-median-baseline"
    paper_scores: dict[str, list[float]] = defaultdict(list)
    for v in verdicts:
        paper_scores[v["paper_id"]].append(v["score"])
    for pid, scores in paper_scores.items():
        if pid not in gt:
            continue
        sorted_s = sorted(scores)
        n = len(sorted_s)
        median = (sorted_s[n // 2] + sorted_s[(n - 1) // 2]) / 2.0
        agent_verdicts[median_id].append({
            "author_id": median_id,
            "author_name": "Median Baseline",
            "author_type": "baseline",
            "paper_id": pid,
            "score": round(median, 2),
        })
    agent_info[median_id] = {
        "agent_id": median_id,
        "agent_name": "Median Baseline",
        "agent_type": "baseline",
    }

    # Step 1: Entry gate — only agents with >= MIN_VERDICTS_FOR_RANKING
    #         total verdicts enter the competition
    # Step 2: Filter out verdicts with no GT
    # Step 3: For correlation, build valid pairs (handling flaws per mode)
    # Step 4: Sample BOOTSTRAP_SAMPLE_SIZE per bootstrap run from valid pairs
    agents = {}
    for aid, vlist in agent_verdicts.items():
        if len(vlist) < MIN_VERDICTS_FOR_RANKING:
            continue

        info = agent_info[aid]
        n_total = len(vlist)

        # Pair verdicts with GT — drop verdicts with no GT match
        gt_pairs = []
        verdict_details = []
        for v in vlist:
            pid = v["paper_id"]
            detail = {
                "paper_id": pid,
                "verdict_score": v["score"],
                "in_gt": pid in gt,
            }
            if pid in gt:
                g = gt[pid]
                detail["gt_title"] = g["title"]
                detail["is_flaw"] = g["is_flaw"]
                for m in METRICS:
                    detail[f"gt_{m}"] = g[m]
                gt_pairs.append({"score": v["score"], "gt": g})
            verdict_details.append(detail)

        n_gt = len(gt_pairs)
        n_flaws = sum(1 for p in gt_pairs if p["gt"]["is_flaw"])
        n_clean = n_gt - n_flaws

        # Build valid pairs per metric (handling flaws per mode)
        correlations = {}
        corr_stds = {}
        for metric in METRICS:
            valid = []
            for p in gt_pairs:
                is_flaw = p["gt"]["is_flaw"]
                if flaws_mode == "exclude" and is_flaw:
                    continue
                if flaws_mode == "penalize" and is_flaw:
                    valid.append((p["score"], FLAW_GT_VALUE))
                else:
                    gt_val = p["gt"][metric]
                    if gt_val is not None:
                        valid.append((p["score"], gt_val))

            if len(valid) < BOOTSTRAP_SAMPLE_SIZE:
                correlations[metric] = None
                corr_stds[metric] = None
                continue

            # Bootstrap: sample BOOTSTRAP_SAMPLE_SIZE from valid,
            # repeat N_BOOTSTRAP_SAMPLES times
            rng = random.Random(RANDOM_SEED)
            sample_corrs = []
            for _ in range(N_BOOTSTRAP_SAMPLES):
                sample = rng.sample(valid, BOOTSTRAP_SAMPLE_SIZE)
                preds = [s[0] for s in sample]
                gts = [s[1] for s in sample]
                c = corr_fn(preds, gts)
                if c is not None:
                    sample_corrs.append(c)
            if sample_corrs:
                mean = sum(sample_corrs) / len(sample_corrs)
                variance = sum((c - mean) ** 2 for c in sample_corrs) / len(sample_corrs)
                correlations[metric] = mean
                corr_stds[metric] = math.sqrt(variance)
            else:
                correlations[metric] = None
                corr_stds[metric] = None

        agents[aid] = {
            **info,
            "n_verdicts": n_total,
            "n_gt_matched": n_gt,
            "n_clean_pairs": n_clean,
            "n_flaw_verdicts": n_flaws,
            "correlations": {
                m: round(v, 4) if v is not None else None
                for m, v in correlations.items()
            },
            "corr_stds": {
                m: round(v, 4) if v is not None else None
                for m, v in corr_stds.items()
            },
            "verdicts": verdict_details,
        }

    # Build per-metric rankings — only agents with a score for this metric
    rankings = {}
    for metric in METRICS:
        scored = [
            (aid, a) for aid, a in agents.items()
            if a["correlations"][metric] is not None
        ]
        scored.sort(key=lambda x: x[1]["correlations"][metric], reverse=True)

        ranking = []
        for rank, (aid, a) in enumerate(scored, 1):
            ranking.append({
                "rank": rank,
                "agent_id": aid,
                "agent_name": a["agent_name"],
                "agent_type": a["agent_type"],
                "n_verdicts": a["n_verdicts"],
                "n_gt_matched": a["n_gt_matched"],
                "n_clean_pairs": a["n_clean_pairs"],
                "n_flaw_verdicts": a["n_flaw_verdicts"],
                "correlation": a["correlations"][metric],
                "corr_std": a["corr_stds"][metric],
            })

        rankings[metric] = ranking

    return {
        "min_verdicts_for_ranking": MIN_VERDICTS_FOR_RANKING,
        "correlation_method": method,
        "flaws_mode": flaws_mode,
        "flaw_gt_value": FLAW_GT_VALUE if flaws_mode == "penalize" else None,
        "n_gt_papers": len(gt),
        "n_agents": len(agents),
        "metrics": METRICS,
        "rankings": rankings,
        "agents": agents,
    }


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def print_leaderboard(result: dict):
    for metric in result["metrics"]:
        ranking = result["rankings"][metric]
        print(f"\n{'='*110}")
        print(f"  {metric.upper()} — {len(ranking)} agents")
        print(f"{'='*110}")
        print(f"{'Rank':>5}  {'Agent':<45} {'Vrdcts':>6} {'Flaw%':>14} {'Corr':>9} {'Std':>9}")
        print(f"{'-'*5}  {'-'*45} {'-'*6} {'-'*14} {'-'*9} {'-'*9}")
        for e in ranking:
            name = (e["agent_name"] or "?")[:45]
            corr = f"{e['correlation']:.4f}"
            std = f"{e['corr_std']:.4f}" if e["corr_std"] is not None else "-"
            n_gt = e["n_gt_matched"]
            n_flaw = e["n_flaw_verdicts"]
            pct = f"{n_flaw/n_gt:.2f}" if n_gt > 0 else "0"
            flaw_str = f"{n_flaw}/{n_gt}={pct}"
            print(f"{e['rank']:>5}  {name:<45} {e['n_verdicts']:>6} {flaw_str:>14} {corr:>9} {std:>9}")


def main():
    parser = argparse.ArgumentParser(description="Compute leaderboard from data dump")
    parser.add_argument("--dump", required=True, help="Path to dump directory")
    parser.add_argument("--out", default=None, help="Output JSON file")
    parser.add_argument("--method", default="pearson", choices=["pearson", "spearman"],
                        help="Correlation method (default: pearson)")
    parser.add_argument("--flaws", default="include", choices=["include", "exclude", "penalize"],
                        help="How to handle flaw papers: include (default), exclude, or penalize (-10 per flaw verdict)")
    args = parser.parse_args()

    dump_dir = Path(args.dump)
    if not dump_dir.is_dir():
        print(f"Error: {dump_dir} is not a directory")
        return

    gt = load_ground_truth()
    verdicts = load_verdicts(dump_dir)
    result = compute_leaderboard(verdicts, gt, method=args.method,
                                flaws_mode=args.flaws)

    print_leaderboard(result)

    if args.out:
        with open(args.out, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\nJSON written to {args.out}")


if __name__ == "__main__":
    main()
