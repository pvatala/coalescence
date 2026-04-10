import katex from 'katex';
import 'katex/dist/katex.min.css';

/**
 * Renders text with inline ($...$) and display ($$...$$) LaTeX.
 * Works in both server and client components.
 */
export function LaTeX({ children, className }: { children: string; className?: string }) {
  const html = renderLatex(children);
  return <span className={className} dangerouslySetInnerHTML={{ __html: html }} />;
}

function renderLatex(text: string): string {
  return text
    .replace(/\$\$([^$]+?)\$\$/g, (_, tex) => {
      try {
        return katex.renderToString(tex.trim(), { displayMode: true, throwOnError: false });
      } catch {
        return `$$${tex}$$`;
      }
    })
    .replace(/\$([^$]+?)\$/g, (_, tex) => {
      try {
        return katex.renderToString(tex.trim(), { displayMode: false, throwOnError: false });
      } catch {
        return `$${tex}$`;
      }
    });
}
