import { overallProgress, sourceProgress } from '../../utils/progress';
import type { LearningPathPlan, LearningPathSource, LearningPathUnit } from '../../types';

// No local props interface needed anymore for internal cards

// Pretty label for source IDs
function sourceName(id: string) {
  return id
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase());
}

// Source color palette
const SOURCE_COLORS: Record<number, { accent: string; light: string; ring: string; badge: string }> = {
  0: { accent: '#6366f1', light: '#eef2ff', ring: '#a5b4fc', badge: '#e0e7ff' },
  1: { accent: '#0ea5e9', light: '#f0f9ff', ring: '#7dd3fc', badge: '#e0f2fe' },
  2: { accent: '#8b5cf6', light: '#f5f3ff', ring: '#c4b5fd', badge: '#ede9fe' },
  3: { accent: '#f59e0b', light: '#fffbeb', ring: '#fcd34d', badge: '#fef3c7' },
};

function getColor(idx: number) {
  return SOURCE_COLORS[idx % Object.keys(SOURCE_COLORS).length];
}

// ─── Ring SVG ───────────────────────────────────────────
function Ring({ pct, size = 52, color }: { pct: number; size?: number; color: string }) {
  const r = (size - 8) / 2;
  const circ = 2 * Math.PI * r;
  return (
    <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#E5E7EB" strokeWidth={5} />
      <circle
        cx={size / 2} cy={size / 2} r={r}
        fill="none" stroke={color} strokeWidth={5} strokeLinecap="round"
        strokeDasharray={circ}
        strokeDashoffset={circ - (pct / 100) * circ}
        style={{ transition: 'stroke-dashoffset 0.8s cubic-bezier(0.4,0,0.2,1)' }}
      />
    </svg>
  );
}

// ─── Unit Card (Main Topic) ─────────────────────────────
function UnitCard({
  unit,
}: {
  unit: LearningPathUnit;
}) {
  const isCompleted = unit.completed;

  return (
    <div
      className="rounded-xl border transition-all duration-500 shadow-sm"
      style={{
        borderColor: isCompleted ? '#22c55e' : '#E5E7EB',
        background: isCompleted ? '#f0fdf4' : 'white',
        overflow: 'hidden',
      }}
    >
      <div className="flex items-center gap-3 px-4 py-3.5 select-none">
        {/* Circular Indicator */}
        <span
          className="shrink-0 w-[20px] h-[20px] rounded-full flex items-center justify-center border-2 transition-all duration-500"
          style={{
            borderColor: isCompleted ? '#22c55e' : '#CBD5E1',
            background: isCompleted ? '#22c55e' : 'white',
            boxShadow: isCompleted ? '0 0 0 4px rgba(34, 197, 94, 0.1)' : 'none',
          }}
        >
          {isCompleted && (
            <svg width="10" height="8" viewBox="0 0 10 8" fill="none">
              <path d="M1 4L3.5 6.5L9 1" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          )}
        </span>

        <div className="flex-1 min-w-0">
          <div
            className="text-[0.95rem] leading-tight truncate"
            style={{ 
              color: isCompleted ? '#166534' : '#374151',
              textDecoration: isCompleted ? 'line-through' : 'none',
              opacity: isCompleted ? 0.7 : 1,
              fontWeight: 400,
            }}
            title={unit.title}
          >
            {unit.title}
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Source Section ──────────────────────────────────────
function SourceSection({
  source, colorIdx,
}: {
  source: LearningPathSource;
  colorIdx: number;
}) {
  const color = getColor(colorIdx);
  const { done, total, pct } = sourceProgress(source);

  return (
    <div className="rounded-2xl border" style={{ borderColor: color.ring, background: 'white', overflow: 'hidden' }}>
      {/* Source Header */}
      <div className="flex items-center gap-3 px-4 py-4" style={{ background: color.light, borderBottom: '1px solid ' + color.ring }}>
        <div className="relative shrink-0" style={{ width: 44, height: 44 }}>
          <Ring pct={pct} size={44} color={color.accent} />
          <span className="absolute inset-0 flex items-center justify-center text-[10px] font-bold" style={{ color: color.accent }}>
            {pct}%
          </span>
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full" style={{ background: color.badge, color: color.accent }}>
              {source.sourceId.replace(/_/g, ' ')}
            </span>
          </div>
          <div className="text-[15px] font-medium mt-1 leading-tight text-gray-900 truncate" title={source.subject.split('—')[0].trim()}>
            {source.subject.split('—')[0].trim()}
          </div>
          <div className="text-[11px] mt-1 text-gray-500 font-medium opacity-80">
            {done} of {total} topics complete
          </div>
        </div>
      </div>

      {/* Units */}
      <div className="p-3 space-y-2.5">
        {source.units.map((unit) => (
          <UnitCard
            key={unit.unitId}
            unit={unit}
          />
        ))}
      </div>
    </div>
  );
}

export default function LearningPathPanel({ plan }: { plan: LearningPathPlan }) {
  const { done, total, pct } = overallProgress(plan);

  const nextUnit = (() => {
    for (const uid of plan.finalLearningPath) {
      for (const src of plan.sources) {
        const unit = src.units.find(u => u.unitId === uid);
        if (unit && !unit.completed) return { unit, source: src };
      }
    }
    return null;
  })();

  return (
    <div className="flex flex-col h-full overflow-y-auto scrollbar-thin" style={{ padding: '16px 16px 24px', background: '#FAFBFF' }}>

      {/* ── Overall Progress Card ── */}
      <div
        className="flex items-center gap-4 rounded-2xl p-5 mb-6"
        style={{ 
          background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)', 
          boxShadow: '0 10px 25px -5px rgba(16, 185, 129, 0.3)' 
        }}
      >
        <div className="relative shrink-0" style={{ width: 68, height: 68 }}>
          <svg width="68" height="68" style={{ transform: 'rotate(-90deg)' }}>
            <circle cx="34" cy="34" r="28" fill="none" stroke="rgba(255,255,255,0.2)" strokeWidth="6" />
            <circle
              cx="34" cy="34" r="28" fill="none" stroke="white" strokeWidth="6" strokeLinecap="round"
              strokeDasharray={2 * Math.PI * 28}
              strokeDashoffset={2 * Math.PI * 28 - (pct / 100) * 2 * Math.PI * 28}
              style={{ transition: 'stroke-dashoffset 1s cubic-bezier(0.4,0,0.2,1)' }}
            />
          </svg>
          <span className="absolute inset-0 flex items-center justify-center text-lg font-black text-white">{pct}%</span>
        </div>
        <div>
          <div className="text-white font-medium text-[16px] tracking-tight">Mastery Progress</div>
          <div className="text-emerald-100 text-[13px] mt-1 opacity-90">{done} of {total} topics mastered</div>
          {pct === 100 && (
            <div className="text-xs mt-1.5 font-bold text-yellow-300 flex items-center gap-1 animate-bounce">
              ✨ Curriculum complete!
            </div>
          )}
        </div>
      </div>

      {/* ── Next Up ── */}
      {nextUnit && (
        <div className="bg-white rounded-2xl p-4 mb-6 border border-amber-100 shadow-sm relative overflow-hidden">
          <div className="absolute top-0 left-0 w-1.25 h-full bg-amber-400" />
          <div className="text-[10px] font-bold uppercase tracking-widest text-amber-500 mb-1">Target Module</div>
          <div className="text-[15px] text-gray-800 leading-snug">
            {nextUnit.unit.title}
          </div>
          <div className="text-[12px] text-gray-400 mt-1">
            Source: {sourceName(nextUnit.source.sourceId)}
          </div>
        </div>
      )}

      {/* ── Curriculum ── */}
      <div className="flex items-center justify-between mb-4 px-1">
        <div className="text-[11px] font-bold uppercase tracking-widest text-gray-400">
          Syllabus Content
        </div>
        <div className="h-[1px] flex-1 bg-gray-100 ml-4" />
      </div>

      <div className="space-y-6">
        {plan.sources.map((src, i) => (
          <SourceSection
            key={src.sourceId}
            source={src}
            colorIdx={i}
          />
        ))}
      </div>

      {/* ── Footer ── */}
      <div className="mt-8 text-center">
        <p className="text-[11px] text-gray-400 font-medium px-4">
          Topics progress automatically as you move through the chapters with your tutor.
        </p>
      </div>
    </div>
  );
}
