import fs from 'fs';
import path from 'path';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export const metadata = {
  title: 'Team — Koala Science',
};

const CONTENT = fs.readFileSync(
  path.join(process.cwd(), 'public', 'TEAM.md'),
  'utf-8',
);

export default function TeamPage() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-6 sm:py-10">
      <article className="prose prose-slate max-w-none prose-table:text-sm prose-th:font-semibold">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            table: ({ node, ...props }) => (
              <div className="overflow-x-auto"><table {...props} /></div>
            ),
          }}
        >
          {CONTENT}
        </ReactMarkdown>
      </article>
    </div>
  );
}
