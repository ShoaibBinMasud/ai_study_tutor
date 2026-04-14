import { useRef } from 'react';
import type { Source, ChatSession } from '../../types';

interface Props {
  sources: Source[];
  sessions: ChatSession[];
  activeSessionId: string | null;
  onSessionSelect: (id: string) => void;
  onNewChat: () => void;
  onAddSource: (files: FileList) => void;
  onToggleSource: (id: string) => void;
}

const SOURCE_ICONS: Record<Source['type'], string> = {
  pdf: '📄', pptx: '📊', docx: '📝', txt: '📃', url: '🔗',
};

export default function SourcesSidebar({
  sources, sessions, activeSessionId,
  onSessionSelect, onNewChat, onAddSource, onToggleSource,
}: Props) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  return (
    <div
      className="flex flex-col h-full"
      style={{
        width: '240px',
        minWidth: '240px',
        background: '#fff',
        borderRight: '1px solid var(--color-border)',
      }}
    >
      {/* App Logo */}
      <div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: '1px solid var(--color-border)' }}>
        <div className="flex items-center gap-2">
          <div
            className="w-7 h-7 rounded-lg flex items-center justify-center text-white text-sm font-bold"
            style={{ background: 'var(--color-accent)' }}
          >
            A
          </div>
          <span className="font-semibold text-sm" style={{ color: 'var(--color-text-1)' }}>AI Tutor</span>
        </div>
      </div>

      {/* New Chat Button */}
      <div className="px-3 pt-3 pb-1">
        <button
          onClick={onNewChat}
          className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors"
          style={{ background: 'var(--color-surface-sub)', color: 'var(--color-text-2)' }}
          onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'var(--color-border)'; }}
          onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'var(--color-surface-sub)'; }}
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M7 1v12M1 7h12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>
          New chat
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-3 pb-3 space-y-4">
        {/* Sources */}
        <div>
          <div className="flex items-center justify-between py-2">
            <span
              className="text-xs font-semibold uppercase tracking-wider"
              style={{ color: 'var(--color-text-3)' }}
            >
              Sources
            </span>
            <button
              onClick={() => fileInputRef.current?.click()}
              className="text-xs font-medium flex items-center gap-1 px-2 py-0.5 rounded-md transition-colors"
              style={{ color: 'var(--color-accent)' }}
              title="Add a source"
            >
              + Add
            </button>
          </div>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            accept=".pdf,.pptx,.docx,.txt"
            onChange={e => e.target.files && onAddSource(e.target.files)}
          />

          {sources.length === 0 ? (
            <button
              onClick={() => fileInputRef.current?.click()}
              className="w-full flex flex-col items-center gap-2 p-4 rounded-xl text-center cursor-pointer transition-colors"
              style={{
                border: '1.5px dashed var(--color-border-strong)',
                color: 'var(--color-text-3)',
              }}
            >
              <span className="text-2xl">📥</span>
              <span className="text-xs">Upload PDFs, slides, notes</span>
            </button>
          ) : (
            <div className="space-y-0.5">
              {sources.map(src => (
                <div
                  key={src.id}
                  className="source-chip"
                  onClick={() => onToggleSource(src.id)}
                >
                  <div
                    className="w-3.5 h-3.5 rounded border flex items-center justify-center shrink-0 transition-colors"
                    style={{
                      background: src.active ? 'var(--color-accent)' : 'transparent',
                      borderColor: src.active ? 'var(--color-accent)' : 'var(--color-border-strong)',
                    }}
                  >
                    {src.active && (
                      <svg width="8" height="8" viewBox="0 0 8 8" fill="none">
                        <path d="M1.5 4l2 2 3-3" stroke="white" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    )}
                  </div>
                  <span className="text-sm shrink-0">{SOURCE_ICONS[src.type]}</span>
                  <span className="truncate flex-1 text-xs">{src.name.replace(/\.(pdf|pptx|docx|txt)$/i, '')}</span>
                </div>
              ))}
              <button
                onClick={() => fileInputRef.current?.click()}
                className="source-chip w-full"
                style={{ color: 'var(--color-accent)' }}
              >
                <span className="text-base">+</span>
                <span className="text-xs">Add source</span>
              </button>
            </div>
          )}
        </div>

        {/* Sessions */}
        {sessions.length > 0 && (
          <div>
            <div className="py-2">
              <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--color-text-3)' }}>
                Recent
              </span>
            </div>
            <div className="space-y-0.5">
              {sessions.map(session => (
                <button
                  key={session.id}
                  onClick={() => onSessionSelect(session.id)}
                  className="nav-row w-full text-left"
                  style={activeSessionId === session.id ? { background: 'var(--color-surface-sub)', color: 'var(--color-text-1)' } : {}}
                >
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-medium truncate" style={{ color: 'var(--color-text-1)' }}>{session.title}</div>
                    <div className="text-xs truncate mt-0.5" style={{ color: 'var(--color-text-3)' }}>{session.preview}</div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-4 py-3" style={{ borderTop: '1px solid var(--color-border)' }}>
        <div className="flex items-center gap-2">
          <div
            className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold text-white shrink-0"
            style={{ background: '#6366F1' }}
          >
            S
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-xs font-medium" style={{ color: 'var(--color-text-1)' }}>Student</div>
            <div className="text-xs" style={{ color: 'var(--color-text-3)' }}>Free plan</div>
          </div>
        </div>
      </div>
    </div>
  );
}
