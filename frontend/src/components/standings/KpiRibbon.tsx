'use client';

import { BarChart2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { StandingsResponse } from './lib/types';

interface KpiRibbonProps {
  data: StandingsResponse;
  chartOpen: boolean;
  onToggleChart: () => void;
}

export function KpiRibbon({ data, chartOpen, onToggleChart }: KpiRibbonProps) {
  const { n_passers, n_failers, n_verdicts, n_gt_matched_papers } = data;
  const provisional = n_passers === 0 && n_gt_matched_papers === 0;
  const gtDisabled = data.entries.every(
    (e) => e.gt_corr_composite === null && e.gt_corr_avg_score === null
  );

  return (
    <section
      aria-label="Platform KPIs"
      className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-xl border border-border bg-background px-4 py-3"
    >
      {/* Passing */}
      <Stat
        label="Passing"
        value={
          provisional ? (
            <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800">
              Provisional
            </span>
          ) : (
            <span className="tabular-nums text-emerald-600">{n_passers}</span>
          )
        }
      />

      {/* Agents */}
      <Stat
        label="Agents"
        value={
          <span className="tabular-nums text-muted-foreground">
            {n_passers + n_failers}
          </span>
        }
      />

      {/* Verdicts */}
      <Stat
        label="Verdicts"
        value={<span className="tabular-nums">{n_verdicts}</span>}
      />

      {/* GT Status */}
      <Stat
        label="GT Status"
        value={
          n_gt_matched_papers > 0 ? (
            <span className="tabular-nums">{n_gt_matched_papers} papers matched</span>
          ) : (
            <span className="text-amber-600">Awaiting data</span>
          )
        }
      />

      {/* Gate chart toggle */}
      <button
        type="button"
        onClick={onToggleChart}
        disabled={gtDisabled}
        title={gtDisabled ? 'No ground-truth data available yet' : undefined}
        className={cn(
          'ml-auto flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors',
          chartOpen
            ? 'border-teal-600 bg-teal-50 text-teal-700'
            : 'border-border bg-muted/30 text-muted-foreground hover:border-teal-400 hover:text-teal-600',
          gtDisabled && 'cursor-not-allowed opacity-40'
        )}
        aria-pressed={chartOpen}
      >
        <BarChart2 className="h-3.5 w-3.5" aria-hidden />
        Gate chart
      </button>
    </section>
  );
}

function Stat({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
      <span className="font-heading text-xl leading-none">{value}</span>
    </div>
  );
}
