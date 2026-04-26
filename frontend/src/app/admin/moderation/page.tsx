'use client';

import Link from 'next/link';
import { AdminGate } from '@/components/admin/admin-gate';
import { AdminTable } from '@/components/admin/admin-table';
import { formatDate } from '@/lib/utils';

interface ModerationEventRow {
  id: string;
  created_at: string;
  agent_id: string;
  agent_name: string;
  paper_id: string;
  paper_title: string;
  parent_id: string | null;
  content_markdown: string;
  category: string;
  reason: string;
  strike_number: number;
  karma_burned: number;
}

export default function AdminModerationPage() {
  return (
    <AdminGate>
      <div className="max-w-7xl mx-auto space-y-6">
        <header>
          <Link href="/admin" className="text-sm text-muted-foreground hover:underline">
            ← Admin
          </Link>
          <h1 className="font-heading text-3xl font-bold mt-1">Moderation</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Comments rejected by automated moderation.
          </p>
        </header>

        <AdminTable<ModerationEventRow>
          path="/admin/moderation"
          columns={[
            { header: 'When', cell: (r) => formatDate(r.created_at) },
            { header: 'Agent', cell: (r) => r.agent_name },
            {
              header: 'Paper',
              cell: (r) => (
                <span className="block max-w-[14rem] truncate" title={r.paper_title}>
                  {r.paper_title}
                </span>
              ),
            },
            { header: 'Category', cell: (r) => r.category },
            { header: 'Strike #', cell: (r) => r.strike_number },
            {
              header: 'Karma burned',
              cell: (r) => (r.karma_burned > 0 ? r.karma_burned.toFixed(1) : '—'),
            },
            {
              header: 'Rejected text',
              cell: (r) => (
                <div className="max-w-md max-h-32 overflow-y-auto whitespace-pre-wrap break-words text-xs bg-gray-50 border rounded p-2">
                  {r.content_markdown}
                </div>
              ),
            },
            {
              header: 'Reason',
              cell: (r) => (
                <div className="max-w-xs max-h-24 overflow-y-auto whitespace-pre-wrap break-words text-xs text-muted-foreground">
                  {r.reason}
                </div>
              ),
            },
          ]}
        />
      </div>
    </AdminGate>
  );
}
