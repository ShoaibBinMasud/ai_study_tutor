import { useState, useRef, useEffect, memo } from 'react';
import type { Message, Document } from '../types';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import Mermaid from './Mermaid';

// --- Components ---

// Memoized Code block for performance and to handle Mermaid
const CodeBlock = memo(({ inline, className, children }: any) => {
  const match = /language-(\w+)/.exec(className || '');
  const codeString = String(children).replace(/\n$/, '');

  if (!inline && match && match[1] === 'mermaid') {
    return (
      <div className="my-6 w-full flex flex-col items-center">
        <span className="text-[10px] text-gray-400 mb-2 uppercase font-bold tracking-wider">Visualization</span>
        <Mermaid chart={codeString} />
      </div>
    );
  }

  if (inline) {
    return (
      <code className="bg-gray-100 px-1.5 py-0.5 rounded text-sm font-mono text-indigo-700">
        {children}
      </code>
    );
  }

  return (
    <pre className="bg-gray-800 text-gray-100 p-4 rounded-xl overflow-x-auto text-sm my-4 font-mono shadow-inner">
      <code className={className}>{children}</code>
    </pre>
  );
});

// Custom renderers
const MarkdownComponents: any = {
  p: ({ children }: any) => <p className="mb-4 last:mb-0 leading-relaxed">{children}</p>,
  strong: ({ children }: any) => <strong className="font-bold text-gray-900">{children}</strong>,
  code: CodeBlock,
};

interface Props {
  messages: Message[];
  documents: Document[];
  isThinking: boolean;
  thinkingLabel: string;
  onSend: (text: string) => void;
  onAddDocument: (files: FileList) => void;
  projectName: string;
  showProceedPrompt: boolean;
  onProceed: (choice: boolean) => void;
}

function EmptyState({ onAddDocument, projectName }: { onAddDocument: (f: FileList) => void, projectName: string }) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <div className="flex-1 flex flex-col items-center justify-center p-8 text-center animate-in fade-in duration-700">
      <div className="w-20 h-20 rounded-full bg-indigo-50 flex items-center justify-center mb-6 shadow-sm">
        <span className="text-4xl">🎓</span>
      </div>
      <h2 className="text-2xl font-bold text-gray-900 mb-2">Project: {projectName}</h2>
      <p className="text-gray-600 max-w-sm mb-8">
        Your private tutor is ready. Upload documents to train me on your course material, or just start asking questions!
      </p>
      <button className="btn-primary" onClick={() => ref.current?.click()}>
        📎 Upload Course Material
      </button>
      <input
        ref={ref} type="file" multiple className="hidden"
        accept=".pdf,.pptx,.docx,.txt"
        onChange={e => e.target.files && onAddDocument(e.target.files)}
      />
    </div>
  );
}

function ProceedPrompt({ onChoice }: { onChoice: (val: boolean) => void }) {
  return (
    <div className="flex flex-col items-center gap-4 py-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="bg-white border border-indigo-100 rounded-3xl px-6 py-5 shadow-xl max-w-sm w-full mx-auto flex flex-col items-center text-center">
        <div className="w-12 h-12 bg-indigo-50 rounded-2xl flex items-center justify-center mb-3">
          <span className="text-xl">🙌</span>
        </div>
        <h3 className="text-sm font-bold text-gray-900 mb-1">That covers this part!</h3>
        <p className="text-[13px] text-gray-600 mb-5 leading-relaxed">
          Ready to move forward, or would you like to explore this topic a bit more?
        </p>
        <div className="flex gap-3 w-full">
          <button
            onClick={() => onChoice(true)}
            className="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white text-[13px] font-bold py-2.5 rounded-xl transition-all shadow-md shadow-indigo-200"
          >
            Yes, Next Topic
          </button>
          <button
            onClick={() => onChoice(false)}
            className="flex-1 bg-white hover:bg-gray-50 text-gray-700 border border-gray-200 text-[13px] font-bold py-2.5 rounded-xl transition-all"
          >
            Not Yet
          </button>
        </div>
      </div>
    </div>
  );
}

export default function ChatPanel({
  messages, documents, isThinking, thinkingLabel,
  onSend, onAddDocument, projectName,
  showProceedPrompt, onProceed
}: Props) {
  const [input, setInput] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isThinking, showProceedPrompt]);

  const send = () => {
    if (!input.trim() || isThinking) return;
    onSend(input.trim());
    setInput('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  return (
    <div className="flex flex-col flex-1 h-full overflow-hidden bg-[#FBFBFB]">
      {/* Header */}
      <header className="flex items-center justify-between px-6 py-4 bg-white border-b border-gray-100 shadow-sm z-10 shrink-0">
        <div>
          <h1 className="text-base font-bold text-gray-900 leading-none">{projectName}</h1>
          <div className="flex items-center gap-2 mt-1">
            <span className="w-1.5 h-1.5 rounded-full bg-green-500"></span>
            <span className="text-[11px] text-gray-500 font-medium uppercase tracking-wider">
              {documents.length} Source{documents.length !== 1 ? 's' : ''} Connected
            </span>
          </div>
        </div>
      </header>

      {/* Messages */}
      <main className="flex-1 overflow-y-auto scrollbar-thin flex flex-col pt-4">
        {messages.length === 0 ? (
          <EmptyState onAddDocument={onAddDocument} projectName={projectName} />
        ) : (
          <div className="max-w-4xl mx-auto w-full px-4 sm:px-6 pb-12">
            <div className="space-y-8">
              {messages.map((msg, i) => (
                <div
                  key={msg.id}
                  className={`flex gap-4 sm:gap-6 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}
                >
                  {/* Avatar */}
                  <div 
                    className={`w-9 h-9 rounded-xl flex items-center justify-center text-xs font-bold text-white shadow-sm shrink-0 mt-1`}
                    style={{ background: msg.role === 'assistant' ? 'var(--color-accent)' : '#475569' }}
                  >
                    {msg.role === 'assistant' ? 'AI' : 'S'}
                  </div>

                  {/* Content */}
                  <div className={`flex flex-col max-w-[85%] ${msg.role === 'user' ? 'items-end' : ''}`}>
                    {msg.thinking && (
                      <div className="text-[10px] font-mono text-gray-400 uppercase tracking-widest mb-1.5 px-2">
                         {msg.thinking}
                      </div>
                    )}
                    
                    <div 
                      className={`px-5 py-4 text-[0.95rem] leading-relaxed shadow-sm border`}
                      style={{
                        background: msg.role === 'user' ? 'var(--color-accent)' : '#fff',
                        color: msg.role === 'user' ? '#fff' : 'var(--color-text-1)',
                        borderColor: msg.role === 'user' ? 'transparent' : 'var(--color-border)',
                        borderRadius: msg.role === 'user' ? '24px 24px 4px 24px' : '24px 24px 24px 4px'
                      }}
                    >
                      {msg.role === 'user' ? (
                        <span className="whitespace-pre-wrap">{msg.content}</span>
                      ) : (
                        <article className="prose prose-indigo max-w-none">
                          <ReactMarkdown
                            remarkPlugins={[remarkMath, remarkGfm]}
                            rehypePlugins={[rehypeKatex]}
                            components={MarkdownComponents}
                          >
                            {msg.content}
                          </ReactMarkdown>
                        </article>
                      )}
                    </div>
                  </div>
                </div>
              ))}

              {isThinking && (
                <div className="flex gap-4 sm:gap-6 animate-pulse">
                  <div className="w-9 h-9 rounded-xl flex items-center justify-center text-xs font-bold text-white bg-indigo-300 shadow-sm shrink-0" />
                  <div className="px-6 py-4 rounded-[24px_24px_24px_4px] bg-white border border-gray-100 shadow-sm min-w-[200px]">
                    <div className="text-[10px] font-mono uppercase tracking-widest text-gray-300 mb-2">{thinkingLabel}</div>
                    <div className="flex gap-1.5">
                      <div className="w-2 h-2 rounded-full bg-indigo-200" />
                      <div className="w-2 h-2 rounded-full bg-indigo-200" />
                      <div className="w-2 h-2 rounded-full bg-indigo-200" />
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Proceed Prompt Overlay at the end of content */}
            {showProceedPrompt && !isThinking && (
              <ProceedPrompt onChoice={onProceed} />
            )}

            <div ref={bottomRef} className="h-4" />
          </div>
        )}
      </main>

      {/* Input */}
      <footer className="p-4 sm:p-6 bg-gradient-to-t from-[#FBFBFB] via-[#FBFBFB] to-transparent shrink-0">
        <div className="max-w-4xl mx-auto">
          <div className="relative flex flex-col bg-white rounded-3xl border border-gray-200 shadow-lg p-2 focus-within:border-indigo-300 transition-all">
            <textarea
              ref={textareaRef}
              rows={1}
              value={input}
              onChange={(e) => {
                setInput(e.target.value);
                e.target.style.height = 'auto';
                e.target.style.height = `${Math.min(e.target.scrollHeight, 200)}px`;
              }}
              onKeyDown={handleKeyDown}
              disabled={showProceedPrompt}
              placeholder={showProceedPrompt ? "Please respond to the prompt above..." : "Ask anything..."}
              className="w-full pl-4 pr-16 py-3 text-[0.95rem] outline-none resize-none bg-transparent disabled:opacity-50"
              style={{ color: 'var(--color-text-1)', minHeight: '3rem' }}
            />
            <button
              onClick={send}
              disabled={!input.trim() || isThinking || showProceedPrompt}
              className="absolute right-3 bottom-3 w-10 h-10 rounded-2xl flex items-center justify-center transition-all disabled:opacity-30 disabled:grayscale"
              style={{ background: 'var(--color-accent)' }}
            >
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M10 3V17M3 10L10 3L17 10" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
          </div>
          <p className="mt-3 text-center text-[10px] text-gray-400 font-medium uppercase tracking-[0.1em]">
            Press Enter to Send · Shift + Enter for New Line
          </p>
        </div>
      </footer>
    </div>
  );
}
