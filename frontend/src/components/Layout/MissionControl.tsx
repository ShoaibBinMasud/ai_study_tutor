import { useState } from 'react';
import type { Folder, Session } from '../../types';

interface Props {
  folders: Folder[];
  sessions: Session[];
  activeSessionId: string;
  onSessionSelect: (id: string) => void;
  onNewSession: () => void;
}

export default function MissionControl({ folders, sessions, activeSessionId, onSessionSelect, onNewSession }: Props) {
  const [collapsed, setCollapsed] = useState(false);
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set(['f1']));

  const toggleFolder = (id: string) => {
    setExpandedFolders(prev => {
      const s = new Set(prev);
      s.has(id) ? s.delete(id) : s.add(id);
      return s;
    });
  };

  const activeDocCount = folders.reduce((acc, f) => acc + f.documents.filter(d => d.active).length, 0);

  if (collapsed) {
    return (
      <div className="w-12 h-full bg-[var(--color-chrome-800)] border-r border-[var(--color-chrome-600)] flex flex-col items-center py-3 gap-4">
        <button onClick={() => setCollapsed(false)} className="text-[var(--color-chrome-300)] hover:text-white text-lg">→</button>
        {['📁', '💬', '⏱'].map((icon, i) => (
          <span key={i} className="text-lg opacity-50 cursor-pointer hover:opacity-100">{icon}</span>
        ))}
      </div>
    );
  }

  return (
    <div className="w-60 h-full bg-[var(--color-chrome-800)] border-r border-[var(--color-chrome-600)] flex flex-col shrink-0">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2.5 border-b border-[var(--color-chrome-600)]">
        <span className="text-xs font-semibold text-[var(--color-chrome-100)] uppercase tracking-widest">Mission Control</span>
        <button onClick={() => setCollapsed(true)} className="text-[var(--color-chrome-300)] hover:text-white text-sm">←</button>
      </div>

      <div className="flex-1 overflow-y-auto py-2">

        {/* Active Sources */}
        <Section label={`Active Sources · ${activeDocCount}`}>
          {folders.map(folder => (
            <div key={folder.id}>
              <button
                onClick={() => toggleFolder(folder.id)}
                className="w-full flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-[var(--color-chrome-200)] hover:text-white hover:bg-[var(--color-chrome-700)] transition-colors group"
              >
                <span className="text-[0.6rem] text-[var(--color-chrome-300)]">{expandedFolders.has(folder.id) ? '▾' : '▸'}</span>
                <span className="opacity-70">📁</span>
                <span className="flex-1 text-left truncate">{folder.name}</span>
              </button>
              {expandedFolders.has(folder.id) && folder.documents.map(doc => (
                <div key={doc.id} className="flex items-center gap-2 pl-7 pr-3 py-1">
                  <span className={`w-2 h-2 rounded-full shrink-0 ${doc.active ? 'bg-[var(--color-amber-500)]' : 'bg-[var(--color-chrome-500)]'}`} />
                  <span className="text-[0.72rem] text-[var(--color-chrome-200)] truncate flex-1">
                    {doc.name.replace(/\.(pdf|pptx|docx)$/, '')}
                  </span>
                </div>
              ))}
            </div>
          ))}
        </Section>

        {/* Tutor Sessions */}
        <Section label="Tutor Sessions">
          <button
            onClick={onNewSession}
            className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-[var(--color-amber-400)] hover:bg-[var(--color-chrome-700)] transition-colors rounded-md mx-1"
          >
            <span className="text-sm">+</span> New Session
          </button>
          {sessions.map(s => (
            <button
              key={s.id}
              onClick={() => onSessionSelect(s.id)}
              className={`w-full text-left px-3 py-1.5 mx-1 rounded-md transition-colors ${
                s.id === activeSessionId
                  ? 'bg-[var(--color-chrome-600)] text-white'
                  : 'text-[var(--color-chrome-200)] hover:bg-[var(--color-chrome-700)] hover:text-white'
              }`}
            >
              <div className="text-xs font-medium truncate">{s.title}</div>
              <div className="text-[0.65rem] text-[var(--color-chrome-300)] mt-0.5">{s.subject} · {s.messageCount} msgs</div>
            </button>
          ))}
        </Section>
      </div>

      {/* Footer */}
      <div className="border-t border-[var(--color-chrome-600)] p-3">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-full bg-[var(--color-chrome-600)] flex items-center justify-center text-xs font-bold text-[var(--color-amber-400)]">S</div>
          <div>
            <div className="text-xs font-medium text-white">Student</div>
            <div className="text-[0.65rem] text-[var(--color-chrome-300)]">Physics 301</div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mb-1">
      <div className="px-3 pt-3 pb-1.5 text-[0.6rem] font-bold uppercase tracking-widest text-[var(--color-chrome-400)]">{label}</div>
      {children}
    </div>
  );
}
