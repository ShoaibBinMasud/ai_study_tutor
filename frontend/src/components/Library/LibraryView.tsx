import { useState } from 'react';
import type { Folder, StudyDocument } from '../../types';

interface Props {
  folders: Folder[];
  onFoldersChange: (folders: Folder[]) => void;
}

const FILE_ICONS: Record<string, string> = { pdf: '📄', pptx: '📊', docx: '📝', txt: '📃' };

export default function LibraryView({ folders, onFoldersChange }: Props) {
  const [newFolderName, setNewFolderName] = useState('');
  const [showNewFolder, setShowNewFolder] = useState(false);
  const [dragOver, setDragOver] = useState<string | null>(null);

  const createFolder = () => {
    if (!newFolderName.trim()) return;
    const newFolder: Folder = {
      id: `f${Date.now()}`,
      name: newFolderName.trim(),
      documents: [],
    };
    onFoldersChange([...folders, newFolder]);
    setNewFolderName('');
    setShowNewFolder(false);
  };

  const toggleActive = (folderId: string, docId: string) => {
    onFoldersChange(folders.map(f =>
      f.id === folderId
        ? { ...f, documents: f.documents.map(d => d.id === docId ? { ...d, active: !d.active } : d) }
        : f
    ));
  };

  const simulateUpload = (folderId: string) => {
    const names = ['chapter_2_notes.pdf', 'lab_report.pdf', 'assignment_4.pptx'];
    const name = names[Math.floor(Math.random() * names.length)];
    const ext = name.split('.').pop() as StudyDocument['type'];
    const newDoc: StudyDocument = {
      id: `d${Date.now()}`,
      name,
      type: ext,
      size: `${(Math.random() * 5 + 0.5).toFixed(1)} MB`,
      folder: folderId,
      active: true,
    };
    onFoldersChange(folders.map(f => f.id === folderId ? { ...f, documents: [...f.documents, newDoc] } : f));
  };

  const totalActive = folders.reduce((sum, f) => sum + f.documents.filter(d => d.active).length, 0);
  const totalDocs = folders.reduce((sum, f) => sum + f.documents.length, 0);

  return (
    <div className="h-full overflow-y-auto bg-[var(--color-chrome-900)] p-8">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="flex items-start justify-between mb-8 animate-fade-slide-up" style={{ opacity: 0 }}>
          <div>
            <h1 className="text-2xl font-bold text-white mb-1">Knowledge Library</h1>
            <p className="text-[var(--color-chrome-300)] text-sm">{totalDocs} documents · {totalActive} active in current session</p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setShowNewFolder(f => !f)}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--color-chrome-700)] border border-[var(--color-chrome-500)] text-sm text-white hover:bg-[var(--color-chrome-600)] transition-all"
            >
              📁 New Folder
            </button>
          </div>
        </div>

        {/* New folder input */}
        {showNewFolder && (
          <div className="mb-5 flex gap-2 animate-pop-in">
            <input
              value={newFolderName}
              onChange={e => setNewFolderName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && createFolder()}
              placeholder="Folder name..."
              autoFocus
              className="flex-1 bg-[var(--color-chrome-700)] border border-[var(--color-amber-500)]/60 rounded-lg px-4 py-2 text-sm text-white placeholder-[var(--color-chrome-400)] outline-none"
            />
            <button onClick={createFolder} className="px-4 py-2 bg-[var(--color-amber-500)] text-black text-sm font-semibold rounded-lg hover:bg-[var(--color-amber-400)] transition-all">
              Create
            </button>
            <button onClick={() => setShowNewFolder(false)} className="px-4 py-2 bg-[var(--color-chrome-700)] text-[var(--color-chrome-200)] text-sm rounded-lg hover:bg-[var(--color-chrome-600)] transition-all">
              Cancel
            </button>
          </div>
        )}

        {/* Folders */}
        <div className="space-y-4">
          {folders.map((folder, fi) => (
            <div
              key={folder.id}
              className={`bg-[var(--color-chrome-800)] border rounded-xl overflow-hidden transition-all animate-fade-slide-up stagger-${Math.min(fi+1, 5)} ${
                dragOver === folder.id ? 'border-[var(--color-amber-500)]/60 bg-[var(--color-amber-glow)]' : 'border-[var(--color-chrome-600)]'
              }`}
              style={{ opacity: 0 }}
              onDragOver={e => { e.preventDefault(); setDragOver(folder.id); }}
              onDragLeave={() => setDragOver(null)}
              onDrop={e => { e.preventDefault(); setDragOver(null); simulateUpload(folder.id); }}
            >
              {/* Folder header */}
              <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--color-chrome-600)]">
                <div className="flex items-center gap-2">
                  <span className="text-base">📁</span>
                  <span className="text-sm font-semibold text-white">{folder.name}</span>
                  <span className="text-[0.65rem] text-[var(--color-chrome-400)] font-mono">{folder.documents.length} files</span>
                </div>
                <button
                  onClick={() => simulateUpload(folder.id)}
                  className="flex items-center gap-1.5 text-xs text-[var(--color-amber-400)] hover:text-[var(--color-amber-300)] transition-colors font-medium"
                >
                  + Upload File
                </button>
              </div>

              {/* Documents */}
              {folder.documents.length === 0 ? (
                <div className="px-5 py-8 text-center text-sm text-[var(--color-chrome-400)]">
                  <div className="text-2xl mb-2">📂</div>
                  Drop files here or click "Upload File"
                </div>
              ) : (
                <div className="divide-y divide-[var(--color-chrome-700)]">
                  {folder.documents.map(doc => (
                    <div key={doc.id} className="flex items-center gap-4 px-5 py-3 hover:bg-[var(--color-chrome-700)] transition-colors group">
                      <span className="text-xl">{FILE_ICONS[doc.type] ?? '📄'}</span>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm text-white truncate">{doc.name}</div>
                        <div className="text-xs text-[var(--color-chrome-400)] mt-0.5">{doc.size} · {doc.type.toUpperCase()}</div>
                      </div>
                      {/* Active toggle */}
                      <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                        <span className="text-xs text-[var(--color-chrome-400)]">{doc.active ? 'Active' : 'Inactive'}</span>
                      </div>
                      <button
                        onClick={() => toggleActive(folder.id, doc.id)}
                        className={`relative w-9 h-5 rounded-full border transition-all shrink-0 ${
                          doc.active
                            ? 'bg-[var(--color-amber-500)] border-[var(--color-amber-400)]'
                            : 'bg-[var(--color-chrome-600)] border-[var(--color-chrome-500)]'
                        }`}
                        title={doc.active ? 'Remove from active context' : 'Add to active context'}
                      >
                        <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-all ${doc.active ? 'left-4' : 'left-0.5'}`} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Drop zone */}
        <div className="mt-6 border-2 border-dashed border-[var(--color-chrome-600)] rounded-xl p-10 text-center text-[var(--color-chrome-400)] hover:border-[var(--color-amber-500)]/40 hover:text-[var(--color-chrome-200)] transition-all cursor-pointer animate-fade-slide-up stagger-5" style={{ opacity: 0 }}>
          <div className="text-3xl mb-2">📥</div>
          <div className="text-sm font-medium">Drop files anywhere to upload</div>
          <div className="text-xs mt-1">Supports PDF, PPTX, DOCX, TXT</div>
        </div>
      </div>
    </div>
  );
}
