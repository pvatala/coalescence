import Link from 'next/link';
import { getApiUrl } from '../lib/api';
import { Paper } from '../components/feed/paper-feed';
import { InfinitePaperFeed } from '../components/feed/infinite-paper-feed';
import { ActivityStrip } from '../components/feed/activity-strip';

interface SearchParams {
  domain?: string;
  view?: string;
  feed?: string;
}

const FEED_TABS = [
  { value: 'latest', label: 'Latest' },
  { value: 'reviewed', label: 'Reviewed' },
] as const;

function feedQuery(feed: string, domain: string | undefined): URLSearchParams {
  const params = new URLSearchParams();
  if (domain) params.set('domain', domain);
  if (feed === 'reviewed') {
    params.set('status', 'reviewed');
    params.set('sort', 'avg_score');
  }
  return params;
}

export default async function PaperDiscoveryFeed({ searchParams }: { searchParams: SearchParams }) {
  const apiUrl = getApiUrl();
  const domain = searchParams.domain;
  const view = searchParams.view || 'card';
  const feed = searchParams.feed === 'reviewed' ? 'reviewed' : 'latest';

  let papers: Paper[] = [];

  try {
    const params = feedQuery(feed, domain);
    params.set('limit', '50');
    const papersRes = await fetch(`${apiUrl}/papers/?${params}`, { cache: 'no-store' });
    if (papersRes.ok) papers = await papersRes.json();
  } catch (error) {
    if (error && typeof error === 'object' && 'digest' in error && error.digest === 'DYNAMIC_SERVER_USAGE') {
      throw error;
    }
    console.error("Failed to fetch data:", error);
  }

  function tabHref(value: string): string {
    const sp = new URLSearchParams();
    if (domain) sp.set('domain', domain);
    if (value !== 'latest') sp.set('feed', value);
    const qs = sp.toString();
    return qs ? `/?${qs}` : '/';
  }

  return (
    <main className="max-w-2xl mx-auto" role="main" aria-label="Paper Discovery Feed">
      <div className="mb-4">
        <ActivityStrip />
      </div>
      <div className="mb-4 inline-flex rounded-md border bg-white text-sm" role="tablist" aria-label="Feed">
        {FEED_TABS.map((t) => {
          const active = t.value === feed;
          return (
            <Link
              key={t.value}
              href={tabHref(t.value)}
              role="tab"
              aria-selected={active}
              className={
                active
                  ? 'px-3 py-1.5 bg-primary text-primary-foreground first:rounded-l-md last:rounded-r-md'
                  : 'px-3 py-1.5 text-muted-foreground hover:bg-gray-50 first:rounded-l-md last:rounded-r-md'
              }
            >
              {t.label}
            </Link>
          );
        })}
      </div>
      <section className="space-y-6" role="region" aria-label="Paper Feed">
        <InfinitePaperFeed
          initialPapers={papers}
          fetchPath={`/papers/?${feedQuery(feed, domain).toString()}`}
          view={view}
        />
      </section>
    </main>
  );
}
