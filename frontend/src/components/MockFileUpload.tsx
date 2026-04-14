import { useState } from "react";

interface Props {
  onUpload: () => void;
}

export default function MockFileUpload({ onUpload }: Props) {
  const [drag, setDrag] = useState(false);
  const [loading, setLoading] = useState(false);

  const simulateUpload = () => {
    setLoading(true);
    setTimeout(() => {
      onUpload();
    }, 1500); // simulate upload & TOC extraction
  };

  return (
    <div className="h-full w-full flex flex-col items-center justify-center p-12 bg-pattern animate-slide-up">
      <div 
        className={`w-full max-w-2xl aspect-[3/2] flex flex-col justify-between p-8 brutal-border ${drag ? 'bg-[var(--color-ink)] text-[var(--color-paper)]' : 'bg-[#f8f6f0]'}`}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); simulateUpload(); }}
      >
        <div className="flex justify-between items-start">
          <span className="font-[var(--font-mono)] text-xs tracking-widest uppercase">Phase 01 /// Ingestion</span>
          <span className="w-8 h-8 rounded-full border border-current flex items-center justify-center font-mono">↓</span>
        </div>

        <div className="text-center space-y-6">
          <h2 className="text-5xl md:text-6xl font-[var(--font-serif-display)] leading-none text-balance">
            Initialize <br/> <i className="text-[var(--color-accent-magenta)] not-italic">Knowledge</i> Base
          </h2>
          <p className="font-[var(--font-mono)] text-sm opacity-70">
            [ DROP SECURE ARCHIVE .PDF / .PPTX HERE ]
          </p>
        </div>

        <div className="flex justify-center">
          <button 
            onClick={simulateUpload}
            disabled={loading}
            className={`
              px-8 py-3 font-[var(--font-mono)] text-sm 
              uppercase tracking-widest brutal-border bg-[var(--color-accent-cyan)] text-black font-bold
              hover:bg-[#00D1C4] transition-colors relative overflow-hidden group
              ${loading ? 'opacity-50 pointer-events-none' : ''}
            `}
          >
            {loading ? "Extracting TOC..." : "Select File"}
            <div className="absolute bottom-0 left-0 h-1 bg-black w-0 group-hover:w-full transition-all duration-300"></div>
          </button>
        </div>
      </div>

      <div className="mt-12 max-w-lg text-center font-[var(--font-serif-body)] text-[var(--color-ink-light)] italic text-lg stagger-2 animate-slide-up">
        "The mind is not a vessel to be filled, but a fire to be kindled." <br />
        <span className="text-sm not-italic font-sans mt-2 inline-block uppercase tracking-widest text-black font-bold">— Plutarch</span>
      </div>
    </div>
  );
}
