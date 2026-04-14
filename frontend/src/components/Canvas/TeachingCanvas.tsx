import type { CanvasMode } from '../../types';
import DocumentView from './DocumentView';
import FlashcardDeck from './FlashcardDeck';
import QuizCanvas from './QuizCanvas';
import Scratchpad from './Scratchpad';
import SyllabusView from '../TeachingPlanPanel';
import LearningPathPanel from './LearningPathPanel';

interface Props {
  mode: CanvasMode;
  onModeChange: (mode: CanvasMode) => void;
  onClose: () => void;
}

export default function TeachingCanvas({ mode, onModeChange, onClose }: Props) {

  const TABS: { type: CanvasMode['type']; label: string; emoji: string }[] = [
    { type: 'syllabus', label: 'Syllabus', emoji: '📋' },
    { type: 'document', label: 'Notes', emoji: '📖' },
    { type: 'scratchpad', label: 'Scratchpad', emoji: '✏️' },
  ];

  if (mode.type === 'quiz' || mode.type === 'flashcards') {
    TABS.push({
      type: mode.type,
      label: mode.type === 'quiz' ? 'Quiz' : 'Practice',
      emoji: mode.type === 'quiz' ? '🎯' : '🃏'
    });
  }

  const handleTabClick = (type: CanvasMode['type']) => {
    if (type === mode.type) return;
    if (type === 'scratchpad') {
      onModeChange({ type: 'scratchpad' });
    }
  };

  return (
    <div
      className="flex flex-col h-full shrink-0 border-l animate-in slide-in-from-right duration-300"
      style={{
        width: '400px',
        background: '#FAFBFF',
        borderColor: '#E5E7EB',
      }}
    >
      {/* ── Header ── */}
      <div className="flex flex-col shrink-0" style={{ borderBottom: '1px solid #E5E7EB', background: 'white' }}>
        <div className="flex items-center justify-between px-5 pt-4 pb-2">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-lg bg-indigo-600 flex items-center justify-center text-xs">🎓</div>
            <span className="text-[0.65rem] font-extrabold uppercase tracking-widest text-indigo-600">
              Tutor Hub
            </span>
          </div>
          <button
            onClick={onClose}
            className="w-7 h-7 rounded-full flex items-center justify-center hover:bg-gray-100 transition-colors text-sm"
            style={{ color: '#9CA3AF' }}
          >
            ✕
          </button>
        </div>

        {/* Tab Bar */}
        <div className="flex px-3 pb-2.5 gap-1 overflow-x-auto scrollbar-none text-[0.95rem]">
          {TABS.map(tab => {
            const isActive = mode.type === tab.type;
            return (
              <button
                key={tab.type}
                onClick={() => handleTabClick(tab.type)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all duration-200 ${
                  isActive
                    ? 'bg-indigo-600 text-white shadow-md shadow-indigo-200'
                    : 'text-gray-500 hover:text-gray-900 hover:bg-gray-50'
                }`}
              >
                <span>{tab.emoji}</span>
                {tab.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* ── Content Area ── */}
      <div className="flex-1 overflow-hidden relative">

        {mode.type === 'syllabus' && (
          // If the plan has 'sources', it's the new LearningPathPlan
          'sources' in mode.plan ? (
            <LearningPathPanel plan={mode.plan} />
          ) : (
            <SyllabusView plan={mode.plan} />
          )
        )}

        {mode.type === 'document' && (
          <DocumentView sectionTitle={mode.sectionTitle} content={mode.content} />
        )}

        {mode.type === 'flashcards' && (
          <FlashcardDeck cards={mode.cards} />
        )}

        {mode.type === 'quiz' && (
          <QuizCanvas questions={mode.questions} />
        )}

        {mode.type === 'scratchpad' && (
          <Scratchpad />
        )}

        {mode.type === 'welcome' && (
          <div className="p-8 text-center flex flex-col items-center justify-center h-full">
            <div className="w-16 h-16 rounded-3xl bg-indigo-50 flex items-center justify-center text-3xl mb-4 shadow-sm">
              🎓
            </div>
            <h3 className="text-xl font-bold text-gray-900 mb-2">Ready to Learn?</h3>
            <p className="text-sm text-gray-500 max-w-xs leading-relaxed">
              Ask for a <strong>Syllabus</strong> in the chat and I'll build you a custom learning plan right here!
            </p>
          </div>
        )}

      </div>
    </div>
  );
}
