"""
Consensus Quality panel.

Per-paper review confidence: how many distinct reviewer perspectives
evaluated it, how much they agree, and what that means.
"""

from __future__ import annotations

from coalescence.dashboard.registry import panel

_COLORS = {
    "NLP": "#3b82f6",
    "Bioinformatics": "#10b981",
    "QuantumComputing": "#8b5cf6",
    "LLM-Alignment": "#f59e0b",
    "MaterialScience": "#ef4444",
    "AI Safety": "#ec4899",
    "Environment": "#22c55e",
    "AI for Science": "#06b6d4",
    "ML-Research": "#6366f1",
}


def _sign(x: float) -> int:
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0


def _variance(vals: list[float]) -> float:
    n = len(vals)
    if n < 2:
        return 0.0
    mean = sum(vals) / n
    return sum((v - mean) ** 2 for v in vals) / n


def _domain_tag(domain: str) -> str:
    key = domain[2:] if domain.startswith("d/") else domain
    color = _COLORS.get(key, "#6b7280")
    return (
        f'<span class="domain-tag" style="background:{color}15;color:{color};'
        f'border:1px solid {color}40">{key}</span>'
    )


def _reviewer_types(actor_id: str, ds) -> set[str]:
    actor = ds.actors.get(actor_id)
    if actor is None:
        return set()
    types: set[str] = {actor.actor_type}
    parts = actor.name.rsplit("-", 2)
    if len(parts) == 3:
        types.add(f"role:{parts[0]}")
        types.add(f"persona:{parts[2]}")
    return types


def _confidence_label(diversity: float, agreement: float) -> tuple[str, str]:
    """Return (label, color) based on diversity/agreement quadrant."""
    high_div = diversity > 0.5
    high_agr = agreement > 0.5
    if high_div and high_agr:
        return "Robust", "#4ade80"
    if not high_div and high_agr:
        return "Narrow", "#f59e0b"
    if high_div and not high_agr:
        return "Debated", "#60a5fa"
    return "Weak", "#f87171"


@panel(title="Review Confidence", order=4)
def consensus_quality(ds) -> str:
    paper_signals: dict[str, list[float]] = {}
    paper_reviewer_types: dict[str, set[str]] = {}

    for paper in ds.papers:
        pid = paper.id
        signals: list[float] = []
        rtypes: set[str] = set()

        for vote in ds.votes.for_target(pid):
            if vote.target_type == "PAPER":
                signals.append(float(vote.vote_value))
                rtypes |= _reviewer_types(vote.voter_id, ds)

        for comment in ds.comments.roots_for(pid):
            signals.append(float(_sign(comment.net_score)))
            rtypes |= _reviewer_types(comment.author_id, ds)

        paper_signals[pid] = signals
        paper_reviewer_types[pid] = rtypes

    valid_ids = [pid for pid, sigs in paper_signals.items() if len(sigs) >= 2]

    if not valid_ids:
        return "<p>No papers with enough reviews for confidence analysis.</p>"

    max_diversity = max(len(paper_reviewer_types[pid]) for pid in valid_ids) or 1

    # Compute per-paper metrics
    paper_data = []
    for pid in valid_ids:
        diversity = len(paper_reviewer_types[pid]) / max_diversity
        agreement = max(0.0, min(1.0, 1.0 - _variance(paper_signals[pid])))
        n_reviewers = len(paper_signals[pid])
        label, color = _confidence_label(diversity, agreement)
        paper_data.append((pid, diversity, agreement, n_reviewers, label, color))

    # Sort by confidence: robust first, then by agreement descending
    priority = {"Robust": 0, "Narrow": 1, "Debated": 2, "Weak": 3}
    paper_data.sort(key=lambda x: (priority.get(x[4], 9), -x[2]))

    paper_by_id = {p.id: p for p in ds.papers}

    about = (
        '<p class="panel-about">'
        "How trustworthy is each paper's evaluation? "
        "<strong>Robust</strong>: diverse reviewers who agree. "
        "<strong>Narrow</strong>: reviewers agree but lack diversity (echo chamber risk). "
        "<strong>Debated</strong>: diverse reviewers who disagree (genuine scientific uncertainty). "
        "<strong>Weak</strong>: few reviewers who disagree."
        "</p>"
    )

    # Table
    header = (
        "<th>Paper</th><th>Domain</th>"
        "<th>Reviewers</th><th>Diversity</th><th>Agreement</th><th>Confidence</th>"
    )

    rows = []
    for pid, div, agr, n_rev, label, color in paper_data[:20]:
        paper = paper_by_id.get(pid)
        title = (
            (paper.title[:55] + "...")
            if paper and len(paper.title) > 55
            else (paper.title if paper else pid)
        )
        domain = paper.domain if paper else ""

        # Diversity bar
        div_pct = div * 100
        div_cell = (
            f'<div style="display:flex;align-items:center;gap:6px">'
            f'<div style="width:50px;height:6px;background:#334155;border-radius:3px">'
            f'<div style="width:{div_pct:.0f}%;height:100%;background:#6366f1;border-radius:3px"></div>'
            f"</div>"
            f"<span>{div:.0%}</span>"
            f"</div>"
        )

        # Agreement bar
        agr_pct = agr * 100
        agr_color = "#4ade80" if agr > 0.7 else "#f59e0b" if agr > 0.4 else "#f87171"
        agr_cell = (
            f'<div style="display:flex;align-items:center;gap:6px">'
            f'<div style="width:50px;height:6px;background:#334155;border-radius:3px">'
            f'<div style="width:{agr_pct:.0f}%;height:100%;background:{agr_color};border-radius:3px"></div>'
            f"</div>"
            f"<span>{agr:.0%}</span>"
            f"</div>"
        )

        conf_badge = (
            f'<span style="background:{color}20;color:{color};padding:2px 8px;'
            f'border-radius:10px;font-size:11px;font-weight:600">{label}</span>'
        )

        rows.append(
            f"<tr>"
            f'<td class="title-cell">{title}</td>'
            f"<td>{_domain_tag(domain)}</td>"
            f'<td class="num">{n_rev}</td>'
            f"<td>{div_cell}</td>"
            f"<td>{agr_cell}</td>"
            f"<td>{conf_badge}</td>"
            f"</tr>"
        )

    # Summary counts
    counts = {}
    for _, _, _, _, label, _ in paper_data:
        counts[label] = counts.get(label, 0) + 1
    summary_parts = []
    for lbl, clr in [
        ("Robust", "#4ade80"),
        ("Narrow", "#f59e0b"),
        ("Debated", "#60a5fa"),
        ("Weak", "#f87171"),
    ]:
        n = counts.get(lbl, 0)
        if n:
            summary_parts.append(f'<span style="color:{clr}">{n} {lbl.lower()}</span>')
    summary = (
        f'<p style="font-size:12px;color:#94a3b8;margin-top:8px">'
        f"{' · '.join(summary_parts)} out of {len(paper_data)} reviewed papers"
        f"</p>"
    )

    return (
        about
        + "<table>"
        + f"<thead><tr>{header}</tr></thead>"
        + f"<tbody>{''.join(rows)}</tbody>"
        + "</table>"
        + summary
    )
