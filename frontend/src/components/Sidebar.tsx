import { useState } from 'react';

export interface SidebarSource {
  id: string;
  name: string;
  type: string;
}

export interface SidebarSession {
  id: string;
  name: string;
}

export interface SidebarProject {
  id: string;
  name: string;
  sources: SidebarSource[];
  sessions: SidebarSession[];
}

interface Props {
  projects: SidebarProject[];
  recentChats: SidebarSession[];
  activeSessionId: string | null;
  onProjectInitiate: () => void;
  onQuickConsultation: () => void;
  onSessionSelect: (sessionId: string, projectId?: string) => void;
  onUploadDocument: (projectId: string) => void;
  onConvertRecentToProject: (sessionId: string) => void;
  onDeleteRecent: (sessionId: string) => void;
  onRenameProject: (projectId: string, newName: string) => void;
  onDeleteProject: (projectId: string) => void;
}

export default function Sidebar({
  projects,
  recentChats,
  activeSessionId,
  onProjectInitiate,
  onQuickConsultation,
  onSessionSelect,
  onUploadDocument,
  onConvertRecentToProject,
  onDeleteRecent,
  onRenameProject,
  onDeleteProject,
}: Props) {
  const [expandedProjects, setExpandedProjects] = useState<Record<string, boolean>>({});
  const [activeMenuId, setActiveMenuId] = useState<string | null>(null);

  // Inline editing state
  const [editingProjectId, setEditingProjectId] = useState<string | null>(null);
  const [editingProjectName, setEditingProjectName] = useState<string>('');

  const handleRenameSubmit = (projectId: string) => {
    if (editingProjectName.trim()) {
      onRenameProject(projectId, editingProjectName.trim());
    }
    setEditingProjectId(null);
  };

  const toggleProject = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setExpandedProjects(prev => ({ ...prev, [id]: !prev[id] }));
  };

  // Close menus when clicking outside
  const handleWrapperClick = () => {
    if (activeMenuId) setActiveMenuId(null);
  };

  return (
    <div 
      className="flex-shrink-0 flex flex-col overflow-y-auto"
      onClick={handleWrapperClick}
      style={{
        width: '260px',
        height: '100%',
        background: 'var(--color-surface)',
        borderRight: '1px solid var(--color-border)',
        padding: '24px 16px',
        color: 'var(--color-text-1)',
      }}
    >
      {/* Top Actions */}
      <div className="flex gap-2 mb-8">
        <button 
          onClick={onProjectInitiate}
          className="flex-1 flex flex-col items-center justify-center gap-1.5 py-2.5 rounded transition-all hover:bg-black/5 dark:hover:bg-white/5"
          style={{ 
            border: '1px solid var(--color-border)',
            color: 'var(--color-text-1)',
            fontFamily: 'var(--font-sans)',
            fontSize: '12px'
          }}
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 5v14M5 12h14" strokeLinecap="round" strokeLinejoin="round"/></svg>
          <span style={{ fontWeight: 500 }}>New Project</span>
        </button>
        <button 
          onClick={onQuickConsultation}
          className="flex-1 flex flex-col items-center justify-center gap-1.5 py-2.5 rounded transition-all hover:bg-black/5 dark:hover:bg-white/5"
          style={{ 
            border: '1px solid var(--color-border)',
            color: 'var(--color-text-1)',
            fontFamily: 'var(--font-sans)',
            fontSize: '12px'
          }}
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
          <span style={{ fontWeight: 500 }}>New Chat</span>
        </button>
      </div>

      {/* Projects List */}
      <div className="flex flex-col gap-5">
        <div className="text-[11px] font-semibold text-[var(--color-text-3)] px-3 mb-1" style={{ textTransform: 'uppercase', letterSpacing: '0.06em', fontFamily: 'var(--font-sans)' }}>
          Projects
        </div>
        
        {projects.map(proj => {
          const isExpanded = expandedProjects[proj.id] !== false;
          const hasActiveSession = proj.sessions.some(s => s.id === activeSessionId) || proj.id === activeSessionId;

          return (
            <div key={proj.id} className="relative group/folder">
              
              {/* Active Project visual "lock" indicator */}
              {hasActiveSession && (
                <div 
                  className="absolute left-[-12px] top-0 bottom-0 w-[2px]" 
                  style={{ background: 'var(--color-accent)', opacity: 0.5, borderRadius: '0 2px 2px 0' }}
                />
              )}

              {/* Folder Header */}
              <div
                className="flex items-center justify-between px-3 py-1.5 cursor-pointer rounded hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
                onClick={(e) => toggleProject(proj.id, e)}
              >
                <div className="flex items-center gap-2.5 flex-1 min-w-0" style={{ fontFamily: '"EB Garamond", serif', fontSize: '15px', fontWeight: 500, letterSpacing: '0.02em', color: hasActiveSession ? 'var(--color-text-1)' : 'var(--color-text-3)' }}>
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" opacity={hasActiveSession ? 1 : 0.5} style={{ flexShrink: 0 }}>
                    <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
                  </svg>
                  {editingProjectId === proj.id ? (
                    <input
                      autoFocus
                      className="w-full bg-transparent border-b border-[var(--color-accent)] outline-none"
                      style={{ textTransform: 'uppercase', color: 'var(--color-text-1)' }}
                      value={editingProjectName}
                      onChange={(e) => setEditingProjectName(e.target.value)}
                      onBlur={() => handleRenameSubmit(proj.id)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleRenameSubmit(proj.id);
                        if (e.key === 'Escape') setEditingProjectId(null);
                      }}
                      onClick={(e) => e.stopPropagation()}
                    />
                  ) : (
                    <span className="truncate" style={{ textTransform: 'uppercase' }}>{proj.name}</span>
                  )}
                </div>

                {/* Hover Actions (Rename, Delete) */}
                <div className="opacity-0 group-hover/folder:opacity-100 transition-opacity duration-200 flex gap-2 text-[var(--color-text-3)]">
                  <button 
                    title="Rename" 
                    className="hover:text-[var(--color-text-1)]"
                    onClick={(e) => {
                      e.stopPropagation();
                      setEditingProjectId(proj.id);
                      setEditingProjectName(proj.name);
                    }}
                  >
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"></path></svg>
                  </button>
                  <button 
                    title="Delete" 
                    className="hover:text-red-400"
                    onClick={(e) => {
                      e.stopPropagation();
                      if (window.confirm(`Are you sure you want to delete the project "${proj.name}"?`)) {
                        onDeleteProject(proj.id);
                      }
                    }}
                  >
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                  </button>
                </div>
              </div>

              {/* Folder Contents */}
              {isExpanded && (
                <div className="mt-1 ml-5 pl-4 border-l border-[var(--color-border)] flex flex-col gap-3 py-1">
                  
                  {/* Empty State */}
                  {proj.sources.length === 0 && proj.sessions.length === 0 && (
                    <div className="py-2 text-[12px] text-[var(--color-text-3)]" style={{ fontFamily: 'var(--font-sans)' }}>
                      Folder is empty
                    </div>
                  )}

                  {/* Sources Section */}
                  <div className="flex flex-col gap-0.5">
                    {proj.sources.map(src => (
                      <div key={src.id} className="flex items-center gap-2 py-1 px-2 rounded cursor-pointer hover:bg-black/5 dark:hover:bg-white/5 transition-colors text-[var(--color-text-2)]" style={{ fontFamily: 'var(--font-sans)', fontSize: '13px' }}>
                        <span className="text-[12px]" style={{ opacity: 0.5 }}>📄</span>
                        <span className="truncate">{src.name}</span>
                      </div>
                    ))}
                    <button 
                      onClick={(e) => { e.stopPropagation(); onUploadDocument(proj.id); }}
                      className="flex items-center gap-1.5 py-1 px-2 rounded opacity-70 hover:opacity-100 transition-colors text-[var(--color-accent)] w-fit mt-1"
                      style={{ fontSize: '12px', fontFamily: 'var(--font-sans)', fontWeight: 500 }}
                    >
                      <svg width="11" height="11" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M7 1v12M1 7h12" strokeLinecap="round" /></svg>
                      Add sources
                    </button>
                  </div>

                  {/* Sessions Section */}
                  <div className="flex flex-col gap-0.5">
                    {proj.sessions.map(sess => {
                      const isSessActive = sess.id === activeSessionId;
                      return (
                        <div 
                          key={sess.id} 
                          onClick={() => onSessionSelect(sess.id, proj.id)}
                          className="group/session flex items-center justify-between py-1.5 px-2 rounded cursor-pointer transition-colors"
                          style={{
                            background: isSessActive ? 'var(--color-surface-2)' : 'transparent',
                            color: isSessActive ? 'var(--color-text-1)' : 'var(--color-text-2)',
                            fontFamily: 'var(--font-sans)',
                            fontSize: '13px',
                            fontWeight: isSessActive ? 500 : 400
                          }}
                        >
                          <div className="flex items-center gap-2 truncate">
                            <span style={{ color: 'var(--color-accent)', opacity: isSessActive ? 1 : 0 }}>
                               <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
                            </span>
                            <span className="truncate">{sess.name}</span>
                          </div>
                          
                          {/* Hover Actions for Session */}
                          <div className="opacity-0 group-hover/session:opacity-100 transition-opacity duration-200 flex gap-2 text-[var(--color-text-3)] bg-[var(--color-surface)] dark:bg-[var(--color-bg)]">
                             <button title="Rename" className="hover:text-[var(--color-text-1)]"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"></path></svg></button>
                             <button title="Delete" className="hover:text-red-400"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="3 6 5 6 21 6"></polyline></svg></button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Recents List */}
      <div className="flex flex-col gap-2 mt-8">
        <div className="text-[11px] font-semibold text-[var(--color-text-3)] px-3 mb-1" style={{ textTransform: 'uppercase', letterSpacing: '0.06em', fontFamily: 'var(--font-sans)' }}>
          Recents
        </div>
        
        {recentChats.map(chat => {
          const isActive = chat.id === activeSessionId;
          const isMenuOpen = activeMenuId === chat.id;

          return (
            <div 
              key={chat.id} 
              className="relative flex items-center justify-between py-2 px-3 rounded cursor-pointer transition-colors group/recent"
              onClick={() => onSessionSelect(chat.id)}
              style={{
                background: isActive ? 'var(--color-surface-2)' : 'transparent',
                color: isActive ? 'var(--color-text-1)' : 'var(--color-text-2)',
                fontFamily: 'var(--font-sans)',
                fontSize: '13px',
                fontWeight: isActive ? 500 : 400
              }}
            >
              <span className="truncate pr-4">{chat.name}</span>
              
              <div 
                className={`transition-opacity duration-200 ${isMenuOpen || isActive ? 'opacity-100' : 'opacity-0 group-hover/recent:opacity-100'}`}
              >
                <button 
                  onClick={(e) => {
                    e.stopPropagation();
                    setActiveMenuId(isMenuOpen ? null : chat.id);
                  }}
                  className="p-1 rounded hover:bg-black/10 dark:hover:bg-white/10 text-[var(--color-text-3)] hover:text-[var(--color-text-1)]"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="1"></circle><circle cx="19" cy="12" r="1"></circle><circle cx="5" cy="12" r="1"></circle></svg>
                </button>
                
                {/* Custom Dropdown Menu */}
                {isMenuOpen && (
                  <div 
                    className="absolute right-2 top-8 w-48 py-1 rounded-lg shadow-xl z-50 border anim-fade-in"
                    style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border)' }}
                    onClick={(e) => e.stopPropagation()}
                  >
                    <button className="w-full text-left px-4 py-2 hover:bg-[var(--color-surface-2)] flex items-center gap-3 text-sm">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon></svg>
                      Star
                    </button>
                    <button className="w-full text-left px-4 py-2 hover:bg-[var(--color-surface-2)] flex items-center gap-3 text-sm">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"></path></svg>
                      Rename
                    </button>
                    <button 
                      onClick={() => {
                        onConvertRecentToProject(chat.id);
                        setActiveMenuId(null);
                      }}
                      className="w-full text-left px-4 py-2 hover:bg-[var(--color-surface-2)] flex items-center gap-3 text-sm"
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
                      Add to project
                    </button>
                    <div className="h-[1px] bg-[var(--color-border)] my-1 w-full" />
                    <button 
                      onClick={() => {
                        onDeleteRecent(chat.id);
                        setActiveMenuId(null);
                      }}
                      className="w-full text-left px-4 py-2 hover:bg-[var(--color-surface-2)] text-red-500 flex items-center gap-3 text-sm"
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                      Delete
                    </button>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
