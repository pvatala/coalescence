/**
 * Renders markdown content with LaTeX math support.
 * Used for reviews, comments, and any user-generated markdown.
 *
 * Also intercepts inline `[[comment:<uuid>]]` citation tokens and
 * renders them as anchors pointing to `#comment-<uuid>`. When a
 * `commentAuthors` lookup is provided and the UUID resolves to a
 * known author, the link text reads ``@AuthorName``; otherwise it
 * falls back to a short `@<8-char-uuid>`. Malformed tokens fall
 * through as plain text. This matches the server-side parser in
 * ``backend/app/core/verdict_citations.py``.
 *
 * Limitation: citations are rendered as anchors only when they appear
 * as direct text children of `<p>` or `<li>`. Tokens inside headings,
 * blockquotes, tables, or emphasized spans render as plain text. The
 * backend still validates them regardless of placement.
 */

import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import { cn } from '@/lib/utils';

interface MarkdownProps {
  children: string;
  className?: string;
  compact?: boolean;
  /** Map of comment UUID → author display name. Used to turn `[[comment:<uuid>]]`
   * tokens into `@AuthorName` anchors. Missing keys fall back to `@<short-uuid>`. */
  commentAuthors?: Record<string, string>;
}

const COMMENT_CITATION_RE =
  /\[\[comment:([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\]\]/g;

function getLinkText(children: React.ReactNode): string | null {
  if (typeof children === 'string') return children;
  if (Array.isArray(children) && children.length === 1 && typeof children[0] === 'string') {
    return children[0];
  }
  return null;
}

function shortenUrl(href: string, maxLen = 50): string {
  try {
    const u = new URL(href);
    const base = u.host + u.pathname;
    if (base.length > maxLen) return base.slice(0, maxLen - 1) + '…';
    return u.search || u.hash ? base + '…' : base;
  } catch {
    return href.length > maxLen ? href.slice(0, maxLen - 1) + '…' : href;
  }
}

function renderCitations(
  text: string,
  commentAuthors: Record<string, string> | undefined,
): React.ReactNode {
  const nodes: React.ReactNode[] = [];
  let lastIndex = 0;
  COMMENT_CITATION_RE.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = COMMENT_CITATION_RE.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }
    const commentId = match[1].toLowerCase();
    const author = commentAuthors?.[commentId];
    const label = author ? `@${author}` : `@${commentId.slice(0, 8)}`;
    nodes.push(
      <a
        key={match.index}
        href={`#comment-${commentId}`}
        className="text-primary hover:underline"
      >
        {label}
      </a>,
    );
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }
  return nodes.length === 1 ? nodes[0] : nodes;
}

export function Markdown({
  children,
  className,
  compact = false,
  commentAuthors,
}: MarkdownProps) {
  return (
    <div className={cn(
      "prose prose-sm max-w-none",
      "prose-h2:text-sm prose-h3:text-sm prose-h2:font-semibold prose-h3:font-semibold",
      "prose-h2:mt-3 prose-h2:mb-1 prose-h3:mt-2 prose-h3:mb-1",
      // Long URLs / unbroken strings shouldn't blow out the column width on mobile.
      "[overflow-wrap:anywhere]",
      compact && "prose-p:my-0.5",
      className,
    )}>
      <ReactMarkdown
        remarkPlugins={[remarkMath, remarkGfm]}
        rehypePlugins={[rehypeKatex]}
        components={{
          p: ({ children, ...props }) => (
            <p {...props}>{renderChildrenWithCitations(children, commentAuthors)}</p>
          ),
          li: ({ children, ...props }) => (
            <li {...props}>{renderChildrenWithCitations(children, commentAuthors)}</li>
          ),
          a: ({ children, href, ...props }) => {
            const text = getLinkText(children);
            const isBareUrl = !!(href && text && text === href);
            const display = isBareUrl && href!.length > 50 ? shortenUrl(href!) : children;
            return (
              <a
                {...props}
                href={href}
                title={isBareUrl ? href : undefined}
                target="_blank"
                rel="noopener noreferrer"
              >
                {display}
              </a>
            );
          },
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}

function renderChildrenWithCitations(
  children: React.ReactNode,
  commentAuthors: Record<string, string> | undefined,
): React.ReactNode {
  return React.Children.map(children, (child) => {
    if (typeof child === 'string') {
      return renderCitations(child, commentAuthors);
    }
    return child;
  });
}
