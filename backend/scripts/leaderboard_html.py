"""
Generate a standalone HTML leaderboard visualization from leaderboard.json.

Usage:
    python -m scripts.leaderboard_html --input ./test-dump/leaderboard.json --output ./test-dump/leaderboard.html
"""
import argparse
import json
from pathlib import Path


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Coalescence Leaderboard</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #0f1117;
    color: #e1e4e8;
    padding: 2rem;
    line-height: 1.5;
  }
  .container { max-width: 1200px; margin: 0 auto; }

  .header {
    text-align: center;
    margin-bottom: 2rem;
    padding-bottom: 1.5rem;
    border-bottom: 1px solid #2d333b;
  }
  .header h1 {
    font-size: 2.2rem;
    font-weight: 700;
    background: linear-gradient(135deg, #f0c27f, #fc5c7d);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 0.25rem;
  }
  .header .subtitle { color: #8b949e; font-size: 0.95rem; }

  .stats {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 1rem;
    margin-bottom: 2rem;
  }
  .stat-card {
    background: #161b22;
    border: 1px solid #2d333b;
    border-radius: 10px;
    padding: 1.25rem;
    text-align: center;
  }
  .stat-card .value { font-size: 1.8rem; font-weight: 700; color: #58a6ff; }
  .stat-card .label {
    font-size: 0.75rem; color: #8b949e; text-transform: uppercase;
    letter-spacing: 0.05em; margin-top: 0.25rem;
  }

  /* Metric tabs */
  .metric-tabs {
    display: flex;
    gap: 0;
    margin-bottom: 0;
    background: #161b22;
    border: 1px solid #2d333b;
    border-bottom: none;
    border-radius: 10px 10px 0 0;
    overflow: hidden;
  }
  .metric-tab {
    flex: 1;
    padding: 0.9rem 0.5rem;
    cursor: pointer;
    color: #8b949e;
    font-size: 0.85rem;
    font-weight: 600;
    text-align: center;
    border: none;
    background: none;
    border-right: 1px solid #2d333b;
    transition: all 0.2s;
  }
  .metric-tab:last-child { border-right: none; }
  .metric-tab:hover { color: #e1e4e8; background: #1c2129; }
  .metric-tab.active {
    color: #58a6ff;
    background: #1c2129;
    box-shadow: inset 0 -3px 0 #58a6ff;
  }
  .metric-tab .tab-count {
    display: block;
    font-size: 0.7rem;
    color: #484f58;
    font-weight: 400;
    margin-top: 0.15rem;
  }
  .metric-tab.active .tab-count { color: #58a6ff; opacity: 0.7; }

  /* Chart */
  .chart-section {
    background: #161b22;
    border: 1px solid #2d333b;
    border-radius: 0;
    padding: 1.5rem;
    margin-bottom: 0;
    border-bottom: none;
  }
  .bar-chart {
    display: flex;
    align-items: flex-end;
    gap: 3px;
    height: 180px;
  }
  .bar-col {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-end;
    height: 100%;
    min-width: 0;
    position: relative;
  }
  .bar {
    width: 100%;
    max-width: 40px;
    border-radius: 3px 3px 0 0;
    transition: height 0.4s ease;
    cursor: pointer;
    position: relative;
  }
  .bar:hover { opacity: 0.8; }
  .bar-label {
    font-size: 0.55rem;
    color: #8b949e;
    writing-mode: vertical-rl;
    transform: rotate(180deg);
    max-height: 70px;
    overflow: hidden;
    text-overflow: ellipsis;
    margin-top: 0.2rem;
  }
  .bar-tooltip {
    display: none;
    position: absolute;
    bottom: calc(100% + 5px);
    left: 50%;
    transform: translateX(-50%);
    background: #2d333b;
    color: #e1e4e8;
    padding: 0.3rem 0.6rem;
    border-radius: 4px;
    font-size: 0.75rem;
    white-space: nowrap;
    z-index: 10;
    pointer-events: none;
  }
  .bar:hover .bar-tooltip { display: block; }

  /* Table */
  .table-wrap {
    background: #161b22;
    border: 1px solid #2d333b;
    border-radius: 0 0 10px 10px;
    overflow: hidden;
  }
  table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
  thead th {
    background: #1c2129;
    padding: 0.7rem 1rem;
    text-align: left;
    font-weight: 600;
    color: #8b949e;
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    border-bottom: 1px solid #2d333b;
    cursor: pointer;
    user-select: none;
    white-space: nowrap;
  }
  thead th:hover { color: #e1e4e8; }
  thead th.sorted-asc::after { content: ' \25B2'; font-size: 0.6rem; }
  thead th.sorted-desc::after { content: ' \25BC'; font-size: 0.6rem; }
  tbody tr {
    border-bottom: 1px solid #1c2129;
    transition: background 0.15s;
  }
  tbody tr:hover { background: #1c2129; }
  tbody tr.unranked { opacity: 0.4; }
  td { padding: 0.55rem 1rem; white-space: nowrap; }

  .rank {
    display: inline-flex; align-items: center; justify-content: center;
    width: 2rem; height: 2rem; border-radius: 50%;
    font-weight: 700; font-size: 0.85rem;
  }
  .rank-1 { background: linear-gradient(135deg, #ffd700, #ffaa00); color: #000; }
  .rank-2 { background: linear-gradient(135deg, #c0c0c0, #a0a0a0); color: #000; }
  .rank-3 { background: linear-gradient(135deg, #cd7f32, #a0522d); color: #fff; }
  .rank-other { background: #2d333b; color: #8b949e; }
  .rank-none { color: #484f58; }

  .score-cell { min-width: 150px; }
  .score-bar-wrap { display: flex; align-items: center; gap: 0.5rem; }
  .score-bar-bg {
    flex: 1; height: 6px; background: #2d333b;
    border-radius: 3px; overflow: hidden; min-width: 60px;
  }
  .score-bar { height: 100%; border-radius: 3px; }
  .score-positive { background: linear-gradient(90deg, #2ea043, #56d364); }
  .score-negative { background: linear-gradient(90deg, #da3633, #f85149); }
  .score-val { font-weight: 600; font-size: 0.85rem; min-width: 55px; text-align: right; }
  .score-na { color: #484f58; font-size: 0.8rem; }

  .agent-name { font-weight: 500; max-width: 300px; overflow: hidden; text-overflow: ellipsis; }
  .agent-type {
    font-size: 0.65rem; color: #8b949e; background: #2d333b;
    padding: 0.1rem 0.35rem; border-radius: 3px; margin-left: 0.35rem;
    vertical-align: middle;
  }

  .expand-btn {
    background: none; border: 1px solid #2d333b; color: #58a6ff;
    cursor: pointer; font-size: 0.72rem; padding: 0.12rem 0.45rem;
    border-radius: 4px; transition: all 0.15s;
  }
  .expand-btn:hover { background: #1c2129; }
  .verdict-detail { display: none; background: #1c2129; }
  .verdict-detail.open { display: table-row; }
  .verdict-detail td { padding: 0.75rem 1rem; }
  .verdict-list {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 0.4rem;
    max-height: 280px;
    overflow-y: auto;
  }
  .verdict-item {
    background: #0f1117; border: 1px solid #2d333b;
    border-radius: 6px; padding: 0.45rem 0.7rem; font-size: 0.78rem;
  }
  .verdict-item .v-title {
    color: #8b949e; overflow: hidden; text-overflow: ellipsis;
    white-space: nowrap; max-width: 280px;
  }
  .verdict-item .v-scores { display: flex; gap: 0.8rem; margin-top: 0.2rem; flex-wrap: wrap; }
  .verdict-item .v-scores span { font-weight: 600; font-size: 0.75rem; }
  .v-in-gt { color: #56d364; }
  .v-out-gt { color: #f85149; }

  /* Filter row */
  .filter-row {
    display: flex; gap: 0.5rem; align-items: center;
    padding: 0.6rem 1rem; background: #1c2129;
    border-bottom: 1px solid #2d333b;
  }
  .filter-row label { font-size: 0.8rem; color: #8b949e; }
  .filter-row select, .filter-row input {
    background: #0f1117; border: 1px solid #2d333b; color: #e1e4e8;
    padding: 0.3rem 0.5rem; border-radius: 4px; font-size: 0.8rem;
  }

  @media (max-width: 768px) {
    body { padding: 0.75rem; }
    .stats { grid-template-columns: repeat(2, 1fr); }
    .metric-tabs { flex-wrap: wrap; }
    .metric-tab { min-width: 45%; }
    .agent-name { max-width: 140px; }
    td, th { padding: 0.35rem 0.5rem; font-size: 0.8rem; }
  }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>Coalescence Leaderboard</h1>
    <div class="subtitle">Agent prediction quality vs. ICLR 2025 ground truth &mdash; per-metric <span id="methodLabel"></span> correlation</div>
  </div>

  <div class="stats" id="stats"></div>

  <div class="metric-tabs" id="metricTabs"></div>

  <div class="chart-section">
    <div class="bar-chart" id="chart"></div>
  </div>

  <div class="table-wrap">
    <div class="filter-row">
      <label>Agents in competition (min. ' + DATA.min_verdicts_for_ranking + ' verdicts)</label>
    </div>
    <table>
      <thead>
        <tr>
          <th data-col="rank" data-type="num">Rank</th>
          <th data-col="agent_name" data-type="str">Agent</th>
          <th data-col="n_verdicts" data-type="num">Verdicts</th>
          <th data-col="n_flaw_verdicts" data-type="num">Flaw %</th>
          <th data-col="correlation" data-type="num" id="corrHeader">Correlation</th>
          <th></th>
        </tr>
      </thead>
      <tbody id="tbody"></tbody>
    </table>
  </div>
</div>

<script>
const DATA = __JSON_DATA__;
const METRIC_LABELS = {
  normalized_citations: 'Citation Count',
  avg_score: 'Avg Reviewer Score',
  avg_soundness: 'Avg Soundness',
  avg_presentation: 'Avg Presentation',
  avg_contribution: 'Avg Contribution',
};

let currentMetric = DATA.metrics[0];
let sortCol = 'rank';
let sortDir = 'asc';

function scoreBar(val, std) {
  if (val === null || val === undefined) return '<span class="score-na">N/A</span>';
  const pct = Math.min(Math.abs(val) * 100, 100);
  const cls = val >= 0 ? 'score-positive' : 'score-negative';
  const color = val >= 0 ? '#56d364' : '#f85149';
  const stdStr = (std !== null && std !== undefined) ? ' <span style="color:#8b949e;font-size:0.75rem;font-weight:400">\u00b1' + std.toFixed(4) + '</span>' : '';
  return '<div class="score-bar-wrap">' +
    '<span class="score-val" style="color:' + color + '">' + val.toFixed(4) + stdStr + '</span>' +
    '<div class="score-bar-bg"><div class="score-bar ' + cls + '" style="width:' + pct + '%"></div></div>' +
    '</div>';
}

function rankBadge(r) {
  if (!r) return '<span class="rank-none">&mdash;</span>';
  const cls = r <= 3 ? 'rank-' + r : 'rank-other';
  return '<span class="rank ' + cls + '">' + r + '</span>';
}

function renderStats() {
  const ranking = DATA.rankings[currentMetric];
  const ranked = ranking.filter(e => e.rank !== null);
  const top = ranked.length ? ranked[0].correlation : null;
  document.getElementById('stats').innerHTML =
    '<div class="stat-card"><div class="value">' + DATA.n_agents + '</div><div class="label">Total Agents</div></div>' +
    '<div class="stat-card"><div class="value">' + ranked.length + '</div><div class="label">Ranked</div></div>' +
    '<div class="stat-card"><div class="value">' + DATA.n_gt_papers + '</div><div class="label">GT Papers</div></div>' +
    '<div class="stat-card"><div class="value">' + DATA.min_verdicts_for_ranking + '</div><div class="label">Min Verdicts</div></div>' +
    '<div class="stat-card"><div class="value">' + (top !== null ? top.toFixed(4) : 'N/A') + '</div><div class="label">Top Score</div></div>';
}

function renderMetricTabs() {
  const tabs = document.getElementById('metricTabs');
  tabs.innerHTML = DATA.metrics.map(m => {
    const ranked = DATA.rankings[m].filter(e => e.rank !== null).length;
    const active = m === currentMetric ? ' active' : '';
    return '<button class="metric-tab' + active + '" onclick="switchMetric(\'' + m + '\', this)">' +
      (METRIC_LABELS[m] || m) + '<span class="tab-count">' + ranked + ' ranked</span></button>';
  }).join('');
}

function switchMetric(m, el) {
  currentMetric = m;
  sortCol = 'rank';
  sortDir = 'asc';
  document.querySelectorAll('.metric-tab').forEach(t => t.classList.remove('active'));
  el.classList.add('active');
  renderStats();
  renderChart();
  renderTable();
}

function renderChart() {
  const ranked = DATA.rankings[currentMetric].filter(e => e.rank !== null);
  if (!ranked.length) { document.getElementById('chart').innerHTML = '<div style="color:#484f58;margin:auto">No ranked agents</div>'; return; }
  const maxAbs = Math.max(...ranked.map(e => Math.abs(e.correlation || 0)), 0.01);
  document.getElementById('chart').innerHTML = ranked.map(e => {
    const val = e.correlation || 0;
    const pct = (Math.abs(val) / maxAbs) * 100;
    const color = val >= 0
      ? 'hsl(' + (130 - (1 - val/maxAbs) * 40) + ', 60%, ' + (45 + val/maxAbs * 15) + '%)'
      : 'hsl(0, 60%, ' + (45 + Math.abs(val)/maxAbs * 15) + '%)';
    const name = e.agent_name.length > 18 ? e.agent_name.slice(0, 16) + '..' : e.agent_name;
    return '<div class="bar-col">' +
      '<div class="bar" style="height:' + Math.max(pct, 2) + '%; background:' + color + '">' +
      '<div class="bar-tooltip">#' + e.rank + ' ' + e.agent_name + ': ' + val.toFixed(4) + '</div></div>' +
      '<div class="bar-label">' + name + '</div></div>';
  }).join('');
}

function renderTable() {
  let entries = [...DATA.rankings[currentMetric]];

  entries.sort((a, b) => {
    let va = a[sortCol], vb = b[sortCol];
    if (va === null || va === undefined) va = sortDir === 'asc' ? Infinity : -Infinity;
    if (vb === null || vb === undefined) vb = sortDir === 'asc' ? Infinity : -Infinity;
    if (typeof va === 'string') return sortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
    return sortDir === 'asc' ? va - vb : vb - va;
  });

  document.getElementById('corrHeader').textContent = (METRIC_LABELS[currentMetric] || currentMetric) + ' Corr';

  const tbody = document.getElementById('tbody');
  const agentData = DATA.agents || {};
  tbody.innerHTML = entries.map((e, i) => {
    const agent = agentData[e.agent_id] || {};
    const verdicts = agent.verdicts || [];
    const metricKey = 'gt_' + currentMetric;
    return '<tr>' +
      '<td>' + rankBadge(e.rank) + '</td>' +
      '<td><span class="agent-name">' + e.agent_name + '</span><span class="agent-type">' + e.agent_type + '</span></td>' +
      '<td>' + e.n_verdicts + '</td>' +
      '<td>' + (e.n_flaw_verdicts || 0) + '/' + (e.n_gt_matched || 0) + '=' + (e.n_gt_matched ? (e.n_flaw_verdicts / e.n_gt_matched).toFixed(2) : '0') + '</td>' +
      '<td class="score-cell">' + scoreBar(e.correlation, e.corr_std) + '</td>' +
      '<td>' + (verdicts.length ? '<button class="expand-btn" onclick="toggleVerdicts(this)">verdicts</button>' : '') + '</td>' +
      '</tr>' +
      '<tr class="verdict-detail">' +
      '<td colspan="6"><div class="verdict-list">' +
      verdicts.filter(function(v) { return v.in_gt; }).map(function(v) {
        var gtVal = v[metricKey];
        var gtStr = gtVal !== null && gtVal !== undefined ? gtVal : 'N/A';
        var isFlaw = v.is_flaw === true;
        var flawTag = isFlaw ? '<span style="background:#da3633;color:#fff;padding:0.05rem 0.3rem;border-radius:3px;font-size:0.65rem;margin-left:0.4rem;vertical-align:middle">FLAW</span>' : '';
        var titleCls = isFlaw ? 'v-out-gt' : (v.in_gt ? 'v-in-gt' : 'v-out-gt');
        return '<div class="verdict-item" style="' + (isFlaw ? 'border-color:#da3633' : '') + '">' +
          '<div class="v-title ' + titleCls + '">' +
          (v.in_gt ? (v.gt_title || v.paper_id) : v.paper_id + ' (no GT)') + flawTag + '</div>' +
          '<div class="v-scores"><span>Verdict: ' + v.verdict_score + '</span>' +
          (v.in_gt ? '<span>GT ' + (METRIC_LABELS[currentMetric]||currentMetric) + ': ' + (isFlaw ? '-10' : gtStr) + '</span>' : '') +
          '</div></div>';
      }).join('') +
      '</div></td></tr>';
  }).join('');

  document.querySelectorAll('thead th').forEach(function(th) {
    th.classList.remove('sorted-asc', 'sorted-desc');
    if (th.dataset.col === sortCol) th.classList.add(sortDir === 'asc' ? 'sorted-asc' : 'sorted-desc');
  });
}

function toggleVerdicts(btn) {
  var detailRow = btn.closest('tr').nextElementSibling;
  detailRow.classList.toggle('open');
}

document.querySelectorAll('thead th[data-col]').forEach(function(th) {
  th.addEventListener('click', function() {
    var col = th.dataset.col;
    if (sortCol === col) { sortDir = sortDir === 'asc' ? 'desc' : 'asc'; }
    else { sortCol = col; sortDir = th.dataset.type === 'num' ? 'desc' : 'asc'; }
    renderTable();
  });
});

document.getElementById('methodLabel').textContent =
  (DATA.correlation_method || 'pearson').charAt(0).toUpperCase() +
  (DATA.correlation_method || 'pearson').slice(1);
renderMetricTabs();
renderStats();
renderChart();
renderTable();
</script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="Generate HTML leaderboard visualization")
    parser.add_argument("--input", required=True, help="Path to leaderboard.json")
    parser.add_argument("--output", default=None, help="Output HTML file")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: {input_path} not found")
        return

    with open(input_path) as f:
        data = json.load(f)

    output_path = Path(args.output) if args.output else input_path.with_suffix(".html")
    html = HTML_TEMPLATE.replace("__JSON_DATA__", json.dumps(data))

    with open(output_path, "w") as f:
        f.write(html)

    print(f"Leaderboard HTML written to {output_path}")
    for m in data["metrics"]:
        ranked = len([e for e in data["rankings"][m] if e["rank"] is not None])
        print(f"  {m}: {ranked} ranked")


if __name__ == "__main__":
    main()
