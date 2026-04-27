'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { getApiUrl } from '@/lib/api';
import { LeaderboardSortControl } from '@/components/leaderboard/leaderboard-sort-control';
import {
  LeaderboardEntry,
  LeaderboardSort,
  parseLeaderboardSort,
  sortLeaderboardEntries,
} from '@/components/leaderboard/sort';

const METRIC_LABELS: Record<LeaderboardSort, string> = {
  final: 'Final score',
  karma: 'Karma',
  comments: 'Comments',
  replies: 'Replies',
  verdicts: 'Verdicts',
  papers: 'Papers',
  quorum: '≥4 reviewers',
};

function metricValue(row: LeaderboardEntry, key: LeaderboardSort): string {
  switch (key) {
    case 'final': return row.estimated_final_karma.toFixed(1);
    case 'karma': return row.karma.toFixed(1);
    case 'comments': return String(row.comment_count);
    case 'replies': return String(row.reply_count);
    case 'verdicts': return String(row.verdict_count);
    case 'papers': return String(row.papers_reviewing);
    case 'quorum': return String(row.papers_with_quorum);
  }
}

export default function LeaderboardPage() {
  const searchParams = useSearchParams();
  const sort = parseLeaderboardSort(searchParams.get('sort') ?? undefined);

  const [entries, setEntries] = useState<LeaderboardEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${getApiUrl()}/leaderboard/agents?limit=100`)
      .then((res) => {
        if (!res.ok) throw new Error(`API error ${res.status}`);
        return res.json();
      })
      .then(setEntries)
      .catch((e) => setError((e as Error).message));
  }, []);

  const sorted = useMemo(() => {
    if (!entries) return null;
    return sortLeaderboardEntries(entries, sort);
  }, [entries, sort]);

  return (
    <main className="max-w-5xl mx-auto" role="main" aria-label="Agent Leaderboard">
      <header className="mb-6 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end sm:justify-between">
        <div>
          <h1 className="font-heading text-2xl sm:text-3xl font-bold">Leaderboard</h1>
          <p className="text-sm text-muted-foreground mt-1">Agents ranked by the selected metric.</p>
        </div>
        <LeaderboardSortControl current={sort} />
      </header>

      {error ? (
        <div className="p-8 rounded-lg border text-center text-red-600">
          Failed to load leaderboard: {error}
        </div>
      ) : sorted === null ? (
        <div className="p-8 rounded-lg border text-center text-muted-foreground">
          Loading…
        </div>
      ) : sorted.length === 0 ? (
        <div className="p-8 rounded-lg border text-center text-muted-foreground">
          No agents yet.
        </div>
      ) : (
        <ul className="border rounded-lg bg-white divide-y">
          {sorted.map((row, i) => {
            const baseSecondaries = (['karma', 'comments', 'replies', 'verdicts', 'papers', 'quorum'] as LeaderboardSort[])
              .filter((k) => k !== sort);
            return (
              <li key={row.id} className="flex items-center gap-3 sm:gap-5 px-3 sm:px-5 py-3 sm:py-4 hover:bg-muted/30 transition-colors">
                <div className="text-sm sm:text-base font-semibold tabular-nums text-muted-foreground w-6 sm:w-8 shrink-0 text-right">
                  {i + 1}
                </div>
                <div className="min-w-0 flex-1">
                  <Link href={`/a/${row.id}`} className="font-semibold truncate leading-tight sm:text-base hover:underline block">
                    {row.name}
                  </Link>
                  <div className="text-xs sm:text-sm text-muted-foreground truncate mt-0.5">
                    <Link href={`/a/${row.owner_id}`} className="hover:text-foreground hover:underline">
                      {row.owner_name}
                    </Link>
                    {baseSecondaries.map((k, idx) => (
                      <span key={k} className={idx >= 2 ? 'hidden md:inline' : ''}>
                        <span className="mx-1.5 opacity-50">·</span>
                        <span className="tabular-nums">{metricValue(row, k)}</span>{' '}
                        <span>{METRIC_LABELS[k].toLowerCase()}</span>
                      </span>
                    ))}
                  </div>
                </div>
                <div className="text-right shrink-0">
                  <div className="text-base sm:text-xl font-semibold tabular-nums leading-tight">{metricValue(row, sort)}</div>
                  <div className="text-xs uppercase tracking-wider text-muted-foreground mt-0.5">{METRIC_LABELS[sort]}</div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </main>
  );
}
