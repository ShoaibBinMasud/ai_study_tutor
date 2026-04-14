import type { Concept } from '../../types';

interface Props {
  concepts: Concept[];
  verdict: string;
  sessions: { id: string; title: string; subject: string; messageCount: number; lastActive: Date }[];
}

const MASTERY_COLORS = ['#3D3D3D', '#6B7DAA', '#8B9E60', '#C4A035', '#E09020', '#F5A623'];
const MASTERY_LABELS = ['Not Started', 'Introduced', 'Familiar', 'Developing', 'Proficient', 'Mastered'];

function RadarChart({ concepts }: { concepts: Concept[] }) {
  const cx = 100, cy = 100, r = 70;
  const n = concepts.length;
  const angles = concepts.map((_, i) => ((2 * Math.PI * i) / n) - Math.PI / 2);
  const toXY = (angle: number, radius: number) => ({
    x: cx + radius * Math.cos(angle),
    y: cy + radius * Math.sin(angle),
  });

  const gridLevels = [0.2, 0.4, 0.6, 0.8, 1.0];
  const dataPoint = concepts.map((c, i) => toXY(angles[i], r * (c.mastery / 5)));
  const polygon = dataPoint.map(p => `${p.x},${p.y}`).join(' ');

  return (
    <svg width="200" height="200" viewBox="0 0 200 200">
      {/* Grid rings */}
      {gridLevels.map(level => {
        const pts = angles.map(a => toXY(a, r * level));
        return <polygon key={level} points={pts.map(p => `${p.x},${p.y}`).join(' ')} fill="none" stroke="#2E2E2E" strokeWidth="1" />;
      })}
      {/* Axis lines */}
      {angles.map((angle, i) => {
        const outer = toXY(angle, r);
        return <line key={i} x1={cx} y1={cy} x2={outer.x} y2={outer.y} stroke="#2E2E2E" strokeWidth="1" />;
      })}
      {/* Data polygon */}
      <polygon points={polygon} fill="rgba(245,166,35,0.2)" stroke="#F5A623" strokeWidth="2" />
      {/* Data points */}
      {dataPoint.map((p, i) => <circle key={i} cx={p.x} cy={p.y} r="3" fill="#F5A623" />)}
      {/* Labels */}
      {concepts.map((c, i) => {
        const pos = toXY(angles[i], r + 14);
        return (
          <text key={i} x={pos.x} y={pos.y} textAnchor="middle" fontSize="7" fill="#888" dominantBaseline="middle">
            {c.label.length > 12 ? c.label.slice(0, 11) + '…' : c.label}
          </text>
        );
      })}
    </svg>
  );
}

function MasteryCard({ concept }: { concept: Concept }) {
  const pct = Math.round((concept.mastery / 5) * 100);
  return (
    <div className={`rounded-xl p-4 border ${concept.mastery === 5 ? 'border-[var(--color-amber-500)]/40 bg-[var(--color-amber-glow)]' : 'border-[var(--color-chrome-600)] bg-[var(--color-chrome-700)]'}`}>
      <div className="flex justify-between items-start mb-2">
        <span className="text-sm font-medium text-white leading-tight">{concept.label}</span>
        <span className="text-[0.65rem] font-mono shrink-0 ml-2" style={{ color: MASTERY_COLORS[concept.mastery] }}>
          {pct}%
        </span>
      </div>
      <div className="h-1.5 bg-[var(--color-chrome-600)] rounded-full overflow-hidden mb-2">
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${pct}%`, background: MASTERY_COLORS[concept.mastery] }}
        />
      </div>
      <div className="text-[0.62rem] text-[var(--color-chrome-300)]">{MASTERY_LABELS[concept.mastery]}</div>
    </div>
  );
}

export default function DashboardView({ concepts, verdict, sessions }: Props) {
  const avgMastery = concepts.reduce((s, c) => s + c.mastery, 0) / (concepts.length * 5);
  const totalPct = Math.round(avgMastery * 100);
  const mastered = concepts.filter(c => c.mastery === 5).length;

  return (
    <div className="h-full overflow-y-auto bg-[var(--color-chrome-900)] p-8">
      <div className="max-w-5xl mx-auto">
        {/* Page header */}
        <div className="mb-8 animate-fade-slide-up" style={{ opacity: 0 }}>
          <h1 className="text-2xl font-bold text-white mb-1">Your Progress Dashboard</h1>
          <p className="text-[var(--color-chrome-300)] text-sm">Physics 301 — Special Relativity · {concepts.length} concepts tracked</p>
        </div>

        {/* Top stats */}
        <div className="grid grid-cols-4 gap-4 mb-8">
          {[
            { label: 'Overall Mastery', value: `${totalPct}%`, sub: 'across all concepts', color: 'var(--color-amber-400)' },
            { label: 'Concepts Mastered', value: mastered, sub: `of ${concepts.length} total`, color: '#22C55E' },
            { label: 'Study Sessions', value: sessions.length, sub: 'total sessions', color: '#60A5FA' },
            { label: 'Messages Exchanged', value: sessions.reduce((s,x) => s + x.messageCount, 0), sub: 'total interactions', color: '#C084FC' },
          ].map((stat, i) => (
            <div key={i} className={`bg-[var(--color-chrome-800)] border border-[var(--color-chrome-600)] rounded-xl p-5 animate-fade-slide-up stagger-${i+1}`} style={{ opacity: 0 }}>
              <div className="text-[0.65rem] text-[var(--color-chrome-300)] uppercase tracking-widest mb-2">{stat.label}</div>
              <div className="text-3xl font-bold font-mono mb-1" style={{ color: stat.color }}>{stat.value}</div>
              <div className="text-xs text-[var(--color-chrome-400)]">{stat.sub}</div>
            </div>
          ))}
        </div>

        <div className="grid grid-cols-3 gap-6 mb-8">
          {/* Radar chart */}
          <div className="bg-[var(--color-chrome-800)] border border-[var(--color-chrome-600)] rounded-xl p-5 flex flex-col items-center animate-fade-slide-up stagger-2" style={{ opacity: 0 }}>
            <div className="text-xs font-semibold text-[var(--color-chrome-200)] uppercase tracking-widest mb-4">Concept Radar</div>
            <RadarChart concepts={concepts} />
          </div>

          {/* AI Verdict */}
          <div className="col-span-2 bg-[var(--color-chrome-800)] border border-[var(--color-chrome-600)] rounded-xl p-5 animate-fade-slide-up stagger-3" style={{ opacity: 0 }}>
            <div className="flex items-center gap-2 mb-4">
              <div className="w-8 h-8 rounded-full bg-[var(--color-amber-glow-strong)] border border-[var(--color-amber-500)]/50 flex items-center justify-center text-sm font-bold text-[var(--color-amber-400)]">T</div>
              <div>
                <div className="text-sm font-semibold text-white">Tutor's Assessment</div>
                <div className="text-xs text-[var(--color-chrome-300)]">Based on your performance across all sessions</div>
              </div>
            </div>
            <div className="bg-[var(--color-chrome-700)] rounded-lg p-4 border-l-2 border-[var(--color-amber-500)]">
              <p className="text-sm text-[var(--color-chrome-100)] leading-relaxed">{verdict}</p>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-3">
              {[
                { label: 'Strengths', items: concepts.filter(c => c.mastery >= 4).map(c => c.label), color: 'text-[var(--color-amber-400)]', bg: 'bg-[var(--color-amber-glow)]', border: 'border-[var(--color-amber-500)]/30' },
                { label: 'Areas to Focus', items: concepts.filter(c => c.mastery <= 2).map(c => c.label), color: 'text-red-400', bg: 'bg-red-500/10', border: 'border-red-500/30' },
              ].map(group => (
                <div key={group.label} className={`rounded-lg p-3 ${group.bg} border ${group.border}`}>
                  <div className={`text-[0.6rem] uppercase tracking-widest font-bold mb-2 ${group.color}`}>{group.label}</div>
                  {group.items.length > 0
                    ? group.items.map(item => <div key={item} className="text-xs text-[var(--color-chrome-200)] mb-0.5">· {item}</div>)
                    : <div className="text-xs text-[var(--color-chrome-400)] italic">None detected</div>
                  }
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Concept grid */}
        <div className="mb-8 animate-fade-slide-up stagger-4" style={{ opacity: 0 }}>
          <div className="text-xs font-semibold text-[var(--color-chrome-200)] uppercase tracking-widest mb-4">All Concepts</div>
          <div className="grid grid-cols-4 gap-3">
            {concepts.map(c => <MasteryCard key={c.id} concept={c} />)}
          </div>
        </div>

        {/* Session history */}
        <div className="animate-fade-slide-up stagger-5" style={{ opacity: 0 }}>
          <div className="text-xs font-semibold text-[var(--color-chrome-200)] uppercase tracking-widest mb-4">Recent Sessions</div>
          <div className="bg-[var(--color-chrome-800)] border border-[var(--color-chrome-600)] rounded-xl overflow-hidden">
            {sessions.map((s, i) => (
              <div key={s.id} className={`flex items-center gap-4 px-5 py-4 hover:bg-[var(--color-chrome-700)] transition-colors ${i !== sessions.length - 1 ? 'border-b border-[var(--color-chrome-600)]' : ''}`}>
                <div className="w-8 h-8 rounded-full bg-[var(--color-chrome-600)] flex items-center justify-center text-xs font-bold text-[var(--color-chrome-200)]">
                  {i + 1}
                </div>
                <div className="flex-1">
                  <div className="text-sm font-medium text-white">{s.title}</div>
                  <div className="text-xs text-[var(--color-chrome-300)]">{s.subject} · {s.messageCount} messages</div>
                </div>
                <div className="text-xs text-[var(--color-chrome-400)] font-mono">
                  {s.lastActive.toLocaleDateString()}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
