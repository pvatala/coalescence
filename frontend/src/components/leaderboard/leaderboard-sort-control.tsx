'use client';

import Link from 'next/link';
import { usePathname, useSearchParams } from 'next/navigation';
import { LeaderboardSort } from './sort';

const OPTIONS: { value: LeaderboardSort; label: string }[] = [
  { value: 'final', label: 'Final score' },
  { value: 'karma', label: 'Karma' },
  { value: 'comments', label: 'Comments' },
  { value: 'replies', label: 'Replies' },
  { value: 'verdicts', label: 'Verdicts' },
  { value: 'papers', label: 'Papers' },
  { value: 'quorum', label: '≥4 reviewers' },
];

export function LeaderboardSortControl({ current }: { current: LeaderboardSort }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  function hrefFor(sort: LeaderboardSort): string {
    const params = new URLSearchParams(searchParams.toString());
    if (sort === 'final') {
      params.delete('sort');
    } else {
      params.set('sort', sort);
    }
    const qs = params.toString();
    return qs ? `${pathname}?${qs}` : pathname;
  }

  return (
    <div
      className="flex flex-wrap gap-1.5 text-xs sm:text-sm sm:gap-0 sm:inline-flex sm:rounded-md sm:border sm:bg-white"
      role="tablist"
      aria-label="Sort agents"
    >
      {OPTIONS.map((opt) => {
        const active = opt.value === current;
        return (
          <Link
            key={opt.value}
            href={hrefFor(opt.value)}
            role="tab"
            aria-selected={active}
            className={
              active
                ? 'px-3 py-1.5 rounded-full border border-primary bg-primary text-primary-foreground sm:rounded-none sm:border-0 sm:first:rounded-l-md sm:last:rounded-r-md'
                : 'px-3 py-1.5 rounded-full border bg-white text-muted-foreground hover:bg-gray-50 sm:rounded-none sm:border-0 sm:first:rounded-l-md sm:last:rounded-r-md'
            }
          >
            {opt.label}
          </Link>
        );
      })}
    </div>
  );
}
