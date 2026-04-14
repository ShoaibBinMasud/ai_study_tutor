import type { TeachingPlan } from '../types';

interface Props {
  plan: TeachingPlan;
}

export default function SyllabusView({ plan }: Props) {
  const mastered = plan.topics.filter(t => t.status === 'mastered').length;
  const total = plan.topics.length;
  const progress = total === 0 ? 0 : Math.round((mastered / total) * 100);

  return (
    <div className="flex flex-col h-full overflow-y-auto p-5 space-y-6 scrollbar-thin">
      {/* Progress Card */}
      <div className="flex items-center gap-5 p-5 rounded-2xl bg-indigo-50 border border-indigo-100 shadow-sm">
        <div className="relative shrink-0 flex items-center justify-center w-[72px] h-[72px]">
          <svg width="72" height="72" className="transform -rotate-90">
            <circle cx="36" cy="36" r="32" fill="none" stroke="#E0E7FF" strokeWidth="6" />
            <circle
              cx="36" cy="36" r="32" fill="none"
              stroke="var(--color-accent)" strokeWidth="6" strokeLinecap="round"
              strokeDasharray="201.06"
              strokeDashoffset={201.06 - (progress / 100) * 201.06}
              style={{ transition: 'stroke-dashoffset 1s cubic-bezier(0.4, 0, 0.2, 1)' }}
            />
          </svg>
          <span className="absolute text-base font-bold text-indigo-900">{progress}%</span>
        </div>
        <div>
          <div className="text-sm font-bold text-indigo-900">Total Mastery</div>
          <div className="text-xs mt-1 text-indigo-700 font-medium">
            {mastered} of {total} units completed
          </div>
        </div>
      </div>

      {/* Syllabus / Topics Checklist */}
      <div className="space-y-4">
        <h3 className="text-[10px] font-bold uppercase tracking-[0.15em] text-gray-400 px-1">
          Course Curriculum
        </h3>
        <div className="space-y-2.5">
          {plan.topics.map((topic, i) => {
            const isMastered = topic.status === 'mastered';
            const isInProgress = topic.status === 'in-progress';
            
            return (
              <div 
                key={topic.id}
                className="flex p-4 rounded-2xl border transition-all duration-300"
                style={{
                  background: isMastered ? '#F0FDF4' : isInProgress ? '#fff' : '#F9FBFF',
                  borderColor: isMastered ? '#BBF7D0' : isInProgress ? 'var(--color-accent)' : '#E5E7EB',
                  boxShadow: isInProgress ? '0 4px 12px rgba(79, 70, 229, 0.08)' : 'none'
                }}
              >
                <div className="shrink-0 pt-0.5 mr-3">
                  {isMastered ? (
                    <div className="w-5 h-5 rounded-full bg-green-500 flex items-center justify-center text-white shadow-sm">
                      <svg width="10" height="8" viewBox="0 0 10 8" fill="none">
                        <path d="M1 4L3.5 6.5L9 1" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    </div>
                  ) : isInProgress ? (
                    <div className="w-5 h-5 rounded-full border-2 border-indigo-500 flex items-center justify-center">
                      <div className="w-2 h-2 rounded-full bg-indigo-500 animate-pulse"/>
                    </div>
                  ) : (
                    <div className="w-5 h-5 rounded-full border-2 border-gray-200 flex items-center justify-center text-[10px] text-gray-400 font-bold">
                      {i + 1}
                    </div>
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-[13px] font-bold" style={{ color: isMastered ? '#166534' : isInProgress ? 'var(--color-text-1)' : '#9CA3AF' }}>
                    {topic.title}
                  </div>
                  {topic.score !== undefined && isMastered && (
                    <div className="text-[11px] mt-1 font-semibold text-green-600 flex items-center gap-1">
                      <span className="w-1 h-1 rounded-full bg-green-600"/> Grade: {topic.score}%
                    </div>
                  )}
                  {isInProgress && (
                    <div className="text-[11px] mt-1 font-bold text-indigo-600 flex items-center gap-1">
                       <span className="w-1 h-1 rounded-full bg-indigo-600 animate-ping"/> Current Target
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
