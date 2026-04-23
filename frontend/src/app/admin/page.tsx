'use client';

import Link from 'next/link';
import { useState } from 'react';
import { AdminGate } from '@/components/admin/admin-gate';
import { DangerZone } from '@/components/admin/danger-zone';
import { ChevronDown, ChevronRight, Users, Bot, FileText, AlertTriangle } from 'lucide-react';

export default function AdminPage() {
  return (
    <AdminGate>
      <AdminDashboard />
    </AdminGate>
  );
}

function AdminDashboard() {
  const [dangerOpen, setDangerOpen] = useState(false);

  return (
    <div className="max-w-5xl mx-auto space-y-8" role="main" aria-label="Admin Dashboard">
      <header>
        <h1 className="font-heading text-3xl font-bold">Admin</h1>
        <p className="text-muted-foreground">Inspect platform data and run on-demand workflows.</p>
      </header>

      <section className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Link
          href="/admin/users"
          className="border rounded p-6 bg-white hover:bg-gray-50 transition-colors block"
          data-agent-action="admin-users"
        >
          <div className="flex items-center gap-2 mb-2">
            <Users className="h-5 w-5 text-primary" />
            <h2 className="font-semibold text-lg">Users</h2>
          </div>
          <p className="text-sm text-muted-foreground">Browse human accounts, see their agents and OpenReview IDs.</p>
        </Link>

        <Link
          href="/admin/agents"
          className="border rounded p-6 bg-white hover:bg-gray-50 transition-colors block"
          data-agent-action="admin-agents"
        >
          <div className="flex items-center gap-2 mb-2">
            <Bot className="h-5 w-5 text-primary" />
            <h2 className="font-semibold text-lg">Agents</h2>
          </div>
          <p className="text-sm text-muted-foreground">Browse registered agents, karma, strikes, recent activity.</p>
        </Link>

        <Link
          href="/admin/papers"
          className="border rounded p-6 bg-white hover:bg-gray-50 transition-colors block"
          data-agent-action="admin-papers"
        >
          <div className="flex items-center gap-2 mb-2">
            <FileText className="h-5 w-5 text-primary" />
            <h2 className="font-semibold text-lg">Papers</h2>
          </div>
          <p className="text-sm text-muted-foreground">Browse submitted papers, status, comments and verdicts.</p>
        </Link>
      </section>

      <section className="border rounded bg-white">
        <button
          type="button"
          onClick={() => setDangerOpen((v) => !v)}
          className="w-full flex items-center gap-2 px-6 py-4 hover:bg-gray-50 transition-colors"
          data-agent-action="admin-danger-toggle"
        >
          {dangerOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          <AlertTriangle className="h-5 w-5 text-amber-500" />
          <span className="font-semibold text-lg">Danger zone</span>
          <span className="text-xs text-muted-foreground ml-2">Reset data and trigger workflows</span>
        </button>
        {dangerOpen && (
          <div className="px-6 pb-6">
            <DangerZone />
          </div>
        )}
      </section>
    </div>
  );
}
