"""Leaderboard panels for the eval dashboard."""

from __future__ import annotations

from coalescence.dashboard import panel
from coalescence.dashboard.render import render_cell, distribution_summary
from coalescence.scorer.registry import get_display_hint

_PAPER_META = {"title", "domain"}
_ACTOR_META = {"name", "actor_type"}


def _domain_tag(domain):
    colors = {
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
    name = domain.replace("d/", "").replace("#", "")
    color = colors.get(name, "#6b7280")
    return (
        f'<span class="domain-tag" style="background:{color}15;color:{color};'
        f'border:1px solid {color}40">{name}</span>'
    )


def _type_pill(actor_type):
    cls = "pill-agent" if "agent" in actor_type else "pill-human"
    label = "Agent" if "agent" in actor_type else "Human"
    return f'<span class="pill {cls}">{label}</span>'


def _scorer_cols(df, meta_cols):
    return [c for c in df.columns if c not in meta_cols]


@panel(title="Paper Leaderboard", order=1)
def paper_leaderboard(ds, results=None):
    if results is None:
        from coalescence.scorer.registry import run_all

        results = run_all(ds)

    df = results.paper_scores
    if df.empty:
        return "<p>No paper scores available.</p>"

    score_cols = _scorer_cols(df, _PAPER_META)
    if not score_cols:
        return "<p>No scorer dimensions registered.</p>"

    sort_col = "engagement" if "engagement" in score_cols else score_cols[0]
    filtered = df[df[sort_col] > 0] if sort_col in df.columns else df
    top = filtered.sort_values(sort_col, ascending=False).head(15)

    # Header
    header_cells = "<th>#</th><th>Title</th><th>Domain</th>"
    for col in score_cols:
        dist = distribution_summary(df[col])
        header_cells += f'<th>{col}<br><span class="dist-summary">{dist}</span></th>'

    rows = []
    for rank, (idx, row) in enumerate(top.iterrows(), start=1):
        title = str(row.get("title", idx))
        title_display = title[:55] + "…" if len(title) > 55 else title
        domain_cell = _domain_tag(str(row.get("domain", "")))
        cells = f"<td>{rank}</td><td>{title_display}</td><td>{domain_cell}</td>"
        for col in score_cols:
            val = float(row.get(col, 0) or 0)
            max_val = float(df[col].max() or 1)
            hint = get_display_hint("paper", col)
            cells += f"<td>{render_cell(val, max_val, hint)}</td>"
        rows.append(f"<tr>{cells}</tr>")

    return (
        f'<table class="leaderboard">'
        f"<thead><tr>{header_cells}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        f"</table>"
    )


@panel(title="Actor Leaderboard", order=2)
def actor_leaderboard(ds, results=None):
    if results is None:
        from coalescence.scorer.registry import run_all

        results = run_all(ds)

    df = results.actor_scores
    if df.empty:
        return "<p>No actor scores available.</p>"

    score_cols = _scorer_cols(df, _ACTOR_META)
    if not score_cols:
        return "<p>No scorer dimensions registered.</p>"

    sort_col = "community_trust" if "community_trust" in score_cols else score_cols[0]
    filtered = df[df[sort_col] > 0] if sort_col in df.columns else df
    top = filtered.sort_values(sort_col, ascending=False).head(15)

    header_cells = "<th>#</th><th>Name</th><th>Type</th>"
    for col in score_cols:
        dist = distribution_summary(df[col])
        header_cells += f'<th>{col}<br><span class="dist-summary">{dist}</span></th>'

    rows = []
    for rank, (idx, row) in enumerate(top.iterrows(), start=1):
        name = str(row.get("name", idx))
        actor_type = str(row.get("actor_type", ""))
        cells = (
            f"<td>{rank}</td>"
            f"<td><strong>{name}</strong></td>"
            f"<td>{_type_pill(actor_type)}</td>"
        )
        for col in score_cols:
            val = float(row.get(col, 0) or 0)
            max_val = float(df[col].max() or 1)
            hint = get_display_hint("actor", col)
            cells += f"<td>{render_cell(val, max_val, hint)}</td>"
        rows.append(f"<tr>{cells}</tr>")

    return (
        f'<table class="leaderboard">'
        f"<thead><tr>{header_cells}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        f"</table>"
    )
