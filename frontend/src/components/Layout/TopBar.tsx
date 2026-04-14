import type { Exam } from '../../types';

interface Props {
  currentView: string;
  onViewChange: (view: 'tutor' | 'dashboard' | 'library') => void;
  exam: Exam;
  examMode: boolean;
  onToggleExamMode: () => void;
}

function useCountdown(targetDate: Date) {
  const now = new Date();
  const diff = targetDate.getTime() - now.getTime();
  const days = Math.floor(diff / (1000 * 60 * 60 * 24));
  const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
  const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
  return { days, hours, minutes, isPast: diff < 0 };
}

export default function TopBar({ currentView, onViewChange, exam, examMode, onToggleExamMode }: Props) {
  const { days, hours } = useCountdown(exam.date);

  return (
    <div className="h-11 flex items-center justify-between px-4 border-b border-[var(--color-chrome-600)] bg-[var(--color-chrome-800)] shrink-0 z-20">
      {/* Left: Logo + Nav */}
      <div className="flex items-center gap-6">
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded-full bg-[var(--color-amber-500)] animate-pulse-amber" />
          <span className="font-semibold text-sm text-white tracking-tight">Aurum</span>
          <span className="text-[var(--color-chrome-300)] text-xs ml-1 font-mono">Private Tutor</span>
        </div>
        <div className="flex items-center gap-1">
          {(['tutor', 'dashboard', 'library'] as const).map((view) => (
            <button
              key={view}
              onClick={() => onViewChange(view)}
              className={`px-3 py-1 rounded-md text-xs font-medium transition-all capitalize ${
                currentView === view
                  ? 'bg-[var(--color-chrome-600)] text-white'
                  : 'text-[var(--color-chrome-200)] hover:text-white hover:bg-[var(--color-chrome-700)]'
              }`}
            >
              {view === 'tutor' ? '💬 Tutor' : view === 'dashboard' ? '📊 Progress' : '📚 Library'}
            </button>
          ))}
        </div>
      </div>

      {/* Center: Subject + Session Goal */}
      <div className="flex items-center gap-3 text-xs text-[var(--color-chrome-200)]">
        <span className="text-white font-medium">{exam.subject}</span>
        <span className="text-[var(--color-chrome-400)]">·</span>
        <span>Special Relativity — Ch. 1-2</span>
      </div>

      {/* Right: Exam Countdown + Mode Toggle */}
      <div className="flex items-center gap-3">
        {/* Exam countdown */}
        <div className={`flex items-center gap-1.5 text-xs font-mono px-2.5 py-1 rounded-md ${
          examMode
            ? 'bg-red-500/20 text-red-400 border border-red-500/30'
            : 'bg-[var(--color-chrome-700)] text-[var(--color-amber-400)] border border-[var(--color-chrome-500)]'
        }`}>
          <span className={examMode ? 'animate-exam-blink' : ''}>⏱</span>
          <span>{days}d {hours}h · {exam.subject} Exam</span>
        </div>

        {/* Exam mode toggle */}
        <button
          onClick={onToggleExamMode}
          data-tooltip={examMode ? 'Switch to Learning Mode' : 'Switch to Exam Mode'}
          className={`px-3 py-1 rounded-md text-xs font-medium border transition-all ${
            examMode
              ? 'bg-red-500/20 text-red-400 border-red-500/40 hover:bg-red-500/30'
              : 'bg-[var(--color-chrome-700)] text-[var(--color-chrome-200)] border-[var(--color-chrome-500)] hover:text-white hover:bg-[var(--color-chrome-600)]'
          }`}
        >
          {examMode ? '🎯 Exam Mode' : '📖 Learning Mode'}
        </button>
      </div>
    </div>
  );
}
