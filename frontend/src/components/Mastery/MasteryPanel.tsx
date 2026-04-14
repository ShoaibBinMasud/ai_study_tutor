import type { Concept, MasteryLevel } from '../../types';

interface Props {
  concepts: Concept[];
  verdict: string;
}

const MASTERY_LABELS: Record<MasteryLevel, string> = {
  0: 'Not Started',
  1: 'Introduced',
  2: 'Familiar',
  3: 'Developing',
  4: 'Proficient',
  5: 'Mastered',
};

const MASTERY_COLORS: Record<MasteryLevel, string> = {
  0: 'var(--color-chrome-500)',
  1: '#6B7DAA',
  2: '#8B9E60',
  3: '#C4A035',
  4: '#E09020',
  5: 'var(--color-amber-500)',
};

function RingChart({ mastery }: { mastery: number }) {
  const pct = Math.round((mastery / 5) * 100);
  const r = 48;
  const circ = 2 * Math.PI * r;
  const offset = circ - (pct / 100) * circ;
  return (
    <div className="relative inline-flex items-center justify-center">
      <svg width="120" height="120" className="-rotate-90">
        <circle cx="60" cy="60" r={r} fill="none" stroke="var(--color-chrome-600)" strokeWidth="8" />
        <circle
          cx="60" cy="60" r={r}
          fill="none"
          stroke="var(--color-amber-500)"
          strokeWidth="8"
          strokeDasharray={circ}
          strokeDashoffset={offset}
          strokeLinecap="round"
          className="ring-progress"
          style={{ filter: pct > 0 ? 'drop-shadow(0 0 6px var(--color-amber-glow-strong))' : 'none' }}
        />
      </svg>
      <div className="absolute flex flex-col items-center">
        <span className="text-xl font-bold font-mono text-[var(--color-amber-400)]">{pct}%</span>
        <span className="text-[0.55rem] text-[var(--color-chrome-300)] uppercase tracking-widest">mastery</span>
      </div>
    </div>
  );
}

function ConceptBar({ concept }: { concept: Concept }) {
  const pct = Math.round((concept.mastery / 5) * 100);
  const color = MASTERY_COLORS[concept.mastery];
  return (
    <div className="group">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-[var(--color-chrome-100)] truncate pr-2 group-hover:text-white transition-colors">{concept.label}</span>
        <span className="text-[0.62rem] font-mono shrink-0" style={{ color }}>{MASTERY_LABELS[concept.mastery]}</span>
      </div>
      <div className="h-1.5 bg-[var(--color-chrome-600)] rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${pct}%`, background: color, boxShadow: pct > 0 ? `0 0 6px ${color}60` : 'none' }}
        />
      </div>
    </div>
  );
}

export default function MasteryPanel({ concepts, verdict }: Props) {
  const avgMastery = concepts.reduce((s, c) => s + c.mastery, 0) / (concepts.length * 5);
  const mastered = concepts.filter(c => c.mastery === 5).length;
  const inProgress = concepts.filter(c => c.mastery > 0 && c.mastery < 5).length;
  const notStarted = concepts.filter(c => c.mastery === 0).length;

  return (
    <div className="w-64 h-full bg-[var(--color-chrome-800)] border-l border-[var(--color-chrome-600)] flex flex-col shrink-0">
      {/* Header */}
      <div className="px-4 py-2.5 border-b border-[var(--color-chrome-600)] shrink-0">
        <span className="text-xs font-semibold text-[var(--color-chrome-100)] uppercase tracking-widest">Mastery Map</span>
      </div>

      <div className="flex-1 overflow-y-auto">
        {/* Overall ring */}
        <div className="flex flex-col items-center py-5 border-b border-[var(--color-chrome-600)] px-4">
          <RingChart mastery={avgMastery * 5} />
          <div className="grid grid-cols-3 gap-2 w-full mt-4">
            {[
              { label: 'Mastered', value: mastered, color: 'var(--color-amber-500)' },
              { label: 'In Progress', value: inProgress, color: '#C4A035' },
              { label: 'Not Started', value: notStarted, color: 'var(--color-chrome-400)' },
            ].map(stat => (
              <div key={stat.label} className="flex flex-col items-center">
                <span className="text-lg font-bold font-mono" style={{ color: stat.color }}>{stat.value}</span>
                <span className="text-[0.55rem] text-[var(--color-chrome-400)] text-center leading-tight">{stat.label}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Concept Bars */}
        <div className="px-4 py-3 border-b border-[var(--color-chrome-600)]">
          <div className="text-[0.6rem] font-bold uppercase tracking-widest text-[var(--color-chrome-400)] mb-3">Concept Breakdown</div>
          <div className="space-y-3">
            {concepts.map(c => <ConceptBar key={c.id} concept={c} />)}
          </div>
        </div>

        {/* AI Verdict */}
        <div className="px-4 py-3">
          <div className="text-[0.6rem] font-bold uppercase tracking-widest text-[var(--color-chrome-400)] mb-2">🧑‍⚖️ Tutor's Verdict</div>
          <div className="text-xs text-[var(--color-chrome-200)] leading-relaxed italic border-l-2 border-[var(--color-amber-500)]/60 pl-3">
            {verdict}
          </div>
        </div>

        {/* Weak spots */}
        <div className="px-4 pb-4">
          <div className="text-[0.6rem] font-bold uppercase tracking-widest text-[var(--color-chrome-400)] mb-2">⚡ Weak Spots</div>
          <div className="space-y-1">
            {concepts.filter(c => c.mastery <= 2).map(c => (
              <div key={c.id} className="flex items-center gap-2 px-2 py-1.5 rounded-md bg-[var(--color-chrome-700)] border border-[var(--color-chrome-600)]">
                <div className="w-1.5 h-1.5 rounded-full bg-red-400 shrink-0" />
                <span className="text-xs text-[var(--color-chrome-100)] truncate">{c.label}</span>
              </div>
            ))}
            {concepts.filter(c => c.mastery <= 2).length === 0 && (
              <div className="text-xs text-[var(--color-amber-400)] opacity-70 font-mono">No weak spots detected ✓</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
