import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';
import type { Message } from '../types';

interface Props {
  message: Message;
  onAction?: (action: 'simpler' | 'deeper', messageId: string) => void;
}

const MarkdownComponents: Record<string, React.FC<any>> = {
  code({ node, inline, className, children, ...props }: any) {
    return !inline ? (
      <pre className="overflow-x-auto my-4">
        <code className={`font-mono text-sm ${className || ''}`} {...props}>
          {children}
        </code>
      </pre>
    ) : (
      <code className="font-mono text-sm" style={{ background: 'rgba(198,168,91,0.08)', color: '#c6a85b', padding: '0.1em 0.4em', borderRadius: 4 }} {...props}>
        {children}
      </code>
    );
  },
};

export default function TutorMessage({ message, onAction }: Props) {
  return (
    <div className="anim-fade-up flex flex-col gap-3" style={{ maxWidth: '760px' }}>
      {/* Tutor label */}
      <div className="flex items-center gap-2">
        <div
          className="w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-semibold shrink-0"
          style={{ background: 'rgba(198,168,91,0.18)', color: '#c6a85b', fontFamily: 'var(--font-sans)' }}
        >
          Dr
        </div>
        <span style={{ fontSize: '0.75rem', color: 'var(--color-text-2)', fontFamily: 'var(--font-sans)', letterSpacing: '0.03em' }}>
          Dr. Arjun · Theoretical Physicist
        </span>
        {message.thinking && (
          <span style={{ fontSize: '0.7rem', color: 'var(--color-text-3)', fontFamily: 'var(--font-mono)', marginLeft: '0.5rem' }}>
            {message.thinking}
          </span>
        )}
      </div>

      {/* Bubble */}
      <div
        className="rounded-2xl tutor-prose"
        style={{
          background: 'var(--color-surface)',
          border: '1px solid var(--color-border)',
          padding: '20px 24px',
        }}
      >
        <ReactMarkdown
          remarkPlugins={[remarkMath, remarkGfm]}
          rehypePlugins={[rehypeKatex]}
          components={MarkdownComponents}
        >
          {message.content}
        </ReactMarkdown>
      </div>

      {/* Inline Action Controls (Keeping new style) */}
      {onAction && (
        <div className="flex gap-6 pl-1 pt-1">
          <button className="action-btn" onClick={() => onAction('simpler', message.id)}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M4 6h16M4 12h10M4 18h16"/>
            </svg>
            Simpler explanation
          </button>
          <button className="action-btn" onClick={() => onAction('deeper', message.id)}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 5v14M5 12h14"/>
            </svg>
            Go deeper
          </button>
        </div>
      )}
    </div>
  );
}
