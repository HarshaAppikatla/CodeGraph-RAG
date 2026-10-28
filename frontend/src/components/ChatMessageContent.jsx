import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { MermaidViewer } from './MermaidViewer';

const remarkPlugins = [remarkGfm];

// Static markdown components map - defined outside to ensure stable reference across renders
const markdownComponents = {
  pre({ children }) {
    // Flatten <pre> so code/mermaid components control their own container
    return <>{children}</>;
  },
  code({ node, className, children, ...props }) {
    const match = /language-(\w+)/.exec(className || '');
    const lang = match ? match[1] : '';
    const codeContent = String(children).replace(/\n$/, '');

    // Mermaid diagram block
    if (lang === 'mermaid') {
      return <MermaidViewer chart={codeContent} />;
    }

    // Fenced code block (e.g. python, bash, json, etc.)
    if (lang || String(children).includes('\n')) {
      return (
        <div className="my-2.5 rounded-xl overflow-hidden border border-slate-800 bg-slate-950 shadow-md">
          <div className="px-3 py-1.5 bg-slate-900/90 border-b border-slate-800 text-[10px] font-mono font-semibold text-cyan-400 uppercase tracking-wider flex items-center justify-between">
            <span>{lang || 'CODE'}</span>
          </div>
          <pre className="p-3 text-[11px] font-mono overflow-x-auto text-slate-300 leading-relaxed">
            <code>{codeContent}</code>
          </pre>
        </div>
      );
    }

    // Inline code: `GEMINI_API_KEY`, `POST`, `bolt://localhost:7687`, etc.
    return (
      <code className="px-1.5 py-0.5 rounded bg-slate-800/80 text-cyan-300 font-mono text-[11px] border border-slate-700/50">
        {children}
      </code>
    );
  },
  table({ children }) {
    return (
      <div className="my-3 overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/80 shadow-lg">
        <table className="w-full text-left text-xs border-collapse">
          {children}
        </table>
      </div>
    );
  },
  thead({ children }) {
    return (
      <thead className="bg-slate-900/90 text-cyan-300 font-mono text-[11px] uppercase tracking-wider border-b border-slate-800">
        {children}
      </thead>
    );
  },
  th({ children }) {
    return (
      <th className="px-3.5 py-2.5 font-semibold text-slate-200">
        {children}
      </th>
    );
  },
  tbody({ children }) {
    return (
      <tbody className="divide-y divide-slate-800/60 text-slate-300">
        {children}
      </tbody>
    );
  },
  tr({ children }) {
    return (
      <tr className="hover:bg-slate-900/40 transition">
        {children}
      </tr>
    );
  },
  td({ children }) {
    return (
      <td className="px-3.5 py-2.5 leading-relaxed align-top">
        {children}
      </td>
    );
  },
  h1({ children }) {
    return <h1 className="text-base font-bold text-cyan-300 mt-4 mb-2">{children}</h1>;
  },
  h2({ children }) {
    return <h2 className="text-sm font-bold text-cyan-300 mt-3 mb-1.5">{children}</h2>;
  },
  h3({ children }) {
    return <h3 className="text-xs font-bold text-cyan-400 mt-2.5 mb-1">{children}</h3>;
  },
  h4({ children }) {
    return <h4 className="text-xs font-bold text-slate-200 mt-2 mb-1">{children}</h4>;
  },
  hr() {
    return <hr className="my-3 border-slate-800" />;
  },
  ul({ children }) {
    return <ul className="list-disc list-inside space-y-1 my-1.5 text-slate-300">{children}</ul>;
  },
  ol({ children }) {
    return <ol className="list-decimal list-inside space-y-1 my-1.5 text-slate-300">{children}</ol>;
  },
  li({ children }) {
    return <li className="leading-relaxed">{children}</li>;
  },
  blockquote({ children }) {
    return (
      <blockquote className="my-2 border-l-2 border-cyan-500/80 bg-slate-900/40 pl-3 py-1.5 text-slate-300 italic rounded-r-lg">
        {children}
      </blockquote>
    );
  },
  strong({ children }) {
    return <strong className="text-slate-100 font-semibold">{children}</strong>;
  },
  a({ href, children }) {
    return (
      <a
        href={href}
        target="_blank"
        rel="noreferrer"
        className="text-cyan-400 hover:text-cyan-300 underline underline-offset-2"
      >
        {children}
      </a>
    );
  }
};

// Memoized to prevent re-rendering when typing in inputs or when parent components update
export const ChatMessageContent = React.memo(({ text }) => {
  if (!text) return null;

  return (
    <div className="space-y-3 leading-relaxed text-slate-200 text-sm">
      <ReactMarkdown
        remarkPlugins={remarkPlugins}
        components={markdownComponents}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
});

export default ChatMessageContent;
