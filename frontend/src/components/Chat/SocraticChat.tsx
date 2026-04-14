import { useState, useRef, useEffect } from 'react';
import type { Message } from '../../types';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';

interface Props {
  messages: Message[];
  onSend: (text: string) => void;
  isThinking: boolean;
  thinkingStep: string;
  examMode: boolean;
  onFlashcards: () => void;
  onQuiz: () => void;
  onSummary: () => void;
  onDocument: () => void;
}

const quickActions = [
  { id: 'doc',        label: '📖 Source',     handler: 'onDocument' as const },
  { id: 'flashcards', label: '🃏 Flashcards',  handler: 'onFlashcards' as const },
  { id: 'quiz',       label: '🎯 Quiz Me',     handler: 'onQuiz' as const },
  { id: 'summary',    label: '📋 Summarize',   handler: 'onSummary' as const },
];

export default function SocraticChat({ messages, onSend, isThinking, thinkingStep, examMode, onFlashcards, onQuiz, onSummary, onDocument }: Props) {
  const [input, setInput] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const handlers = { onDocument, onFlashcards, onQuiz, onSummary };

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isThinking]);

  const handleSend = () => {
    if (!input.trim() || isThinking) return;
    onSend(input.trim());
    setInput('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  const autoResize = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    e.target.style.height = 'auto';
    e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px';
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Message Stream */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {messages.map((msg, i) => (
          <div
            key={msg.id}
            className={`flex gap-2.5 animate-fade-slide-up stagger-${Math.min(i % 4 + 1, 4)}`}
            style={{ opacity: 0 }}
          >
            {/* Avatar */}
            {msg.role === 'assistant' && (
              <div className="shrink-0 w-7 h-7 rounded-full bg-[var(--color-amber-glow-strong)] border border-[var(--color-amber-500)]/50 flex items-center justify-center text-xs font-bold text-[var(--color-amber-400)] mt-0.5">
                T
              </div>
            )}

            <div className={`max-w-[88%] ${msg.role === 'user' ? 'ml-auto' : ''}`}>
              {msg.agentStep && (
                <div className="font-mono text-[0.62rem] text-[var(--color-chrome-300)] mb-1 ml-1 opacity-70">
                  ⚙ {msg.agentStep}
                </div>
              )}
              <div className={`px-3.5 py-2.5 rounded-xl text-sm leading-relaxed ${
                msg.role === 'user' ? 'msg-bubble-user' : 'msg-bubble-ai'
              }`}>
                <ReactMarkdown
                  remarkPlugins={[remarkMath, remarkGfm]}
                  rehypePlugins={[rehypeKatex]}
                  components={{
                    p: ({ children }) => <p className="mb-1.5 last:mb-0">{children}</p>,
                    strong: ({ children }) => <strong className="text-white font-semibold">{children}</strong>,
                    code: ({ children }) => <code className="font-mono text-[0.8em] bg-black/30 rounded px-1 py-0.5 text-[var(--color-amber-300)]">{children}</code>,
                    table: ({ children }) => <table className="text-xs border-collapse my-2 w-full">{children}</table>,
                    th: ({ children }) => <th className="px-2 py-1 bg-black/30 text-[var(--color-chrome-100)] text-left text-[0.7rem] uppercase tracking-wide border border-[var(--color-chrome-500)]">{children}</th>,
                    td: ({ children }) => <td className="px-2 py-1 border border-[var(--color-chrome-500)] text-[var(--color-chrome-100)]">{children}</td>,
                    ul: ({ children }) => <ul className="list-disc pl-4 space-y-0.5 my-1">{children}</ul>,
                    li: ({ children }) => <li className="text-sm">{children}</li>,
                  }}
                >
                  {msg.content}
                </ReactMarkdown>
              </div>
              <div className="text-[0.6rem] text-[var(--color-chrome-400)] mt-1 ml-1">
                {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </div>
            </div>

            {msg.role === 'user' && (
              <div className="shrink-0 w-7 h-7 rounded-full bg-[var(--color-chrome-600)] border border-[var(--color-chrome-500)] flex items-center justify-center text-xs font-bold text-white mt-0.5">
                S
              </div>
            )}
          </div>
        ))}

        {/* Thinking indicator */}
        {isThinking && (
          <div className="flex gap-2.5 animate-fade-in">
            <div className="shrink-0 w-7 h-7 rounded-full bg-[var(--color-amber-glow-strong)] border border-[var(--color-amber-500)]/50 flex items-center justify-center text-xs font-bold text-[var(--color-amber-400)] mt-0.5 animate-pulse-amber">
              T
            </div>
            <div className="msg-bubble-ai px-3.5 py-2.5 rounded-xl">
              <div className="font-mono text-[0.65rem] text-[var(--color-chrome-300)] mb-1">⚙ {thinkingStep}</div>
              <div className="flex gap-1 items-center">
                <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-amber-400)] animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-amber-400)] animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-amber-400)] animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Quick Actions */}
      <div className="px-3 py-2 border-t border-[var(--color-chrome-600)] flex gap-1.5 flex-wrap">
        {quickActions.map(action => (
          <button
            key={action.id}
            onClick={handlers[action.handler]}
            className="px-2.5 py-1 rounded-md text-xs text-[var(--color-chrome-200)] bg-[var(--color-chrome-700)] border border-[var(--color-chrome-500)] hover:border-[var(--color-amber-500)]/60 hover:text-[var(--color-amber-400)] transition-all"
          >
            {action.label}
          </button>
        ))}
        {examMode && (
          <div className="ml-auto text-[0.65rem] flex items-center gap-1 text-red-400 font-mono animate-exam-blink">
            🎯 EXAM MODE ACTIVE
          </div>
        )}
      </div>

      {/* Input */}
      <div className="px-3 pb-3">
        <div className="flex gap-2 items-end bg-[var(--color-chrome-700)] border border-[var(--color-chrome-500)] rounded-xl p-2 focus-within:border-[var(--color-amber-500)]/60 transition-all">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={autoResize}
            onKeyDown={handleKeyDown}
            placeholder={examMode ? "Answer the question..." : "Ask your tutor anything..."}
            rows={1}
            className="flex-1 bg-transparent text-sm text-white placeholder-[var(--color-chrome-300)] resize-none outline-none leading-relaxed py-0.5"
            style={{ minHeight: '24px', maxHeight: '120px' }}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isThinking}
            className="shrink-0 w-8 h-8 rounded-lg bg-[var(--color-amber-500)] text-black font-bold text-sm flex items-center justify-center hover:bg-[var(--color-amber-400)] disabled:opacity-40 disabled:cursor-not-allowed transition-all"
          >
            ↑
          </button>
        </div>
        <div className="text-[0.6rem] text-[var(--color-chrome-400)] mt-1 text-center">
          Enter to send · Shift+Enter for new line · Actions above open in Canvas →
        </div>
      </div>
    </div>
  );
}
