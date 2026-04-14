import { useState } from 'react';
import type { StudioMode, Flashcard, QuizQuestion } from '../../types';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';

interface Props {
  mode: StudioMode;
  onClose: () => void;
}

/* ── Flashcard Component ─────────────────────────────── */
function FlashcardViewer({ cards }: { cards: Flashcard[] }) {
  const [current, setCurrent] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const [results, setResults] = useState<Record<string, boolean>>({});

  const card = cards[current];
  const known = Object.values(results).filter(Boolean).length;
  const progress = Math.round((Object.keys(results).length / cards.length) * 100);

  const mark = (knew: boolean) => {
    setResults(r => ({ ...r, [card.id]: knew }));
    setTimeout(() => {
      setCurrent(c => (c + 1) % cards.length);
      setFlipped(false);
    }, 300);
  };

  if (!card) return null;

  return (
    <div className="flex flex-col h-full p-4 gap-4 overflow-y-auto">
      {/* Header */}
      <div className="flex items-center justify-between shrink-0">
        <div>
          <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-1)' }}>Flashcards</h3>
          <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-3)' }}>
            {current + 1} / {cards.length}
            {Object.keys(results).length > 0 && ` · ${known} known`}
          </p>
        </div>
        <div className="badge badge-accent">{progress}% done</div>
      </div>

      {/* Progress */}
      <div className="progress-bar-track h-1.5 w-full shrink-0">
        <div className="progress-bar-fill h-1.5" style={{ width: `${progress}%` }} />
      </div>

      {/* Card */}
      <div
        className={`flashcard flex-1 cursor-pointer`}
        style={{ minHeight: '200px' }}
        onClick={() => setFlipped(f => !f)}
      >
        <div className={`flashcard-inner ${flipped ? 'flipped' : ''}`} style={{ minHeight: '200px' }}>
          {/* Front */}
          <div
            className="flashcard-front flex flex-col items-center justify-center p-6 text-center"
            style={{ background: '#fff', border: '1px solid var(--color-border)', minHeight: '200px' }}
          >
            {card.tag && <div className="badge badge-accent mb-3">{card.tag}</div>}
            <div className="text-sm font-medium leading-relaxed" style={{ color: 'var(--color-text-1)', fontFamily: 'var(--font-sans)' }}>
              {card.front}
            </div>
            <div className="text-xs mt-3" style={{ color: 'var(--color-text-3)' }}>tap to reveal →</div>
          </div>

          {/* Back */}
          <div
            className="flashcard-back flex flex-col items-center justify-center p-6 text-center"
            style={{ background: 'var(--color-accent-light)', border: '1.5px solid var(--color-accent)', minHeight: '200px' }}
          >
            <div className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: 'var(--color-accent)' }}>Answer</div>
            <div className="text-sm leading-relaxed" style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-text-1)' }}>
              <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                {card.back}
              </ReactMarkdown>
            </div>
          </div>
        </div>
      </div>

      {/* Actions */}
      {flipped && (
        <div className="flex gap-2 shrink-0 anim-pop-in">
          <button
            onClick={() => mark(false)}
            className="flex-1 py-2.5 rounded-xl text-sm font-medium border transition-all"
            style={{
              border: '1px solid #FCA5A5',
              background: '#FEF2F2',
              color: '#DC2626',
            }}
          >
            ✗ Still learning
          </button>
          <button
            onClick={() => mark(true)}
            className="flex-1 py-2.5 rounded-xl text-sm font-medium transition-all"
            style={{
              background: 'var(--color-accent)',
              color: '#fff',
            }}
          >
            ✓ Got it
          </button>
        </div>
      )}

      {/* Nav */}
      <div className="flex items-center gap-2 shrink-0">
        <button
          className="btn-ghost flex-1 justify-center"
          onClick={() => { setCurrent(c => Math.max(0, c - 1)); setFlipped(false); }}
          disabled={current === 0}
        >
          ← Prev
        </button>
        <button
          className="btn-ghost flex-1 justify-center"
          onClick={() => { setCurrent(c => Math.min(cards.length - 1, c + 1)); setFlipped(false); }}
          disabled={current === cards.length - 1}
        >
          Next →
        </button>
      </div>
    </div>
  );
}

/* ── Quiz Component ──────────────────────────────────── */
function QuizViewer({ questions }: { questions: QuizQuestion[] }) {
  const [current, setCurrent] = useState(0);
  const [selected, setSelected] = useState<number | null>(null);
  const [answers, setAnswers] = useState<(number | null)[]>(Array(questions.length).fill(null));
  const [done, setDone] = useState(false);

  const q = questions[current];
  const score = answers.filter((a, i) => a === questions[i].correctIndex).length;

  const pick = (idx: number) => {
    if (selected !== null) return;
    setSelected(idx);
    const a = [...answers]; a[current] = idx; setAnswers(a);
  };

  const next = () => {
    if (current < questions.length - 1) { setCurrent(c => c + 1); setSelected(null); }
    else setDone(true);
  };

  if (done) {
    const pct = Math.round((score / questions.length) * 100);
    return (
      <div className="flex flex-col items-center justify-center h-full p-6 text-center anim-pop-in">
        <div className="text-5xl font-bold mb-3" style={{ color: pct >= 70 ? 'var(--color-success)' : 'var(--color-danger)' }}>{pct}%</div>
        <div className="text-base font-semibold mb-1" style={{ color: 'var(--color-text-1)' }}>
          {pct >= 80 ? 'Excellent!' : pct >= 60 ? 'Good progress' : 'Keep studying'}
        </div>
        <div className="text-sm mb-6" style={{ color: 'var(--color-text-2)' }}>{score}/{questions.length} correct</div>
        <div className="space-y-2 w-full text-left">
          {questions.map((q, i) => (
            <div key={q.id} className="flex items-center gap-2 text-xs px-3 py-2 rounded-lg"
              style={{ background: answers[i] === q.correctIndex ? '#DCFCE7' : '#FEF2F2', color: answers[i] === q.correctIndex ? '#16A34A' : '#DC2626' }}>
              <span>{answers[i] === q.correctIndex ? '✓' : '✗'}</span>
              <span className="flex-1 truncate">{q.question.substring(0, 50)}...</span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full p-4 gap-4 overflow-y-auto">
      <div className="flex items-center justify-between shrink-0">
        <div>
          <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-1)' }}>Quiz</h3>
          <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-3)' }}>Question {current + 1} of {questions.length}</p>
        </div>
        <div className="badge badge-neutral">{Math.round((current / questions.length) * 100)}%</div>
      </div>

      <div className="progress-bar-track h-1.5 shrink-0">
        <div className="progress-bar-fill h-1.5" style={{ width: `${(current / questions.length) * 100}%` }} />
      </div>

      {/* Question */}
      <div className="rounded-xl p-4 shrink-0" style={{ background: '#fff', border: '1px solid var(--color-border)' }}>
        <div className="text-sm leading-relaxed" style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-text-1)' }}>
          <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>{q.question}</ReactMarkdown>
        </div>
      </div>

      {/* Options */}
      <div className="space-y-2">
        {q.options.map((opt, i) => {
          let bg = '#fff', border = 'var(--color-border)', color = 'var(--color-text-1)';
          if (selected !== null) {
            if (i === q.correctIndex) { bg = '#DCFCE7'; border = '#16A34A'; color = '#16A34A'; }
            else if (i === selected) { bg = '#FEF2F2'; border = '#DC2626'; color = '#DC2626'; }
            else { bg = 'var(--color-surface-sub)'; color = 'var(--color-text-3)'; }
          }
          return (
            <button
              key={i}
              onClick={() => pick(i)}
              disabled={selected !== null}
              className="w-full text-left px-4 py-3 rounded-xl text-sm transition-all"
              style={{ background: bg, border: `1.5px solid ${border}`, color }}
            >
              <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>{opt}</ReactMarkdown>
            </button>
          );
        })}
      </div>

      {selected !== null && (
        <>
          <div className="rounded-xl p-3 text-sm shrink-0" style={{ background: 'var(--color-accent-light)', border: '1px solid var(--color-accent)', color: 'var(--color-text-1)' }}>
            <div className="text-xs font-semibold mb-1" style={{ color: 'var(--color-accent)' }}>📝 Explanation</div>
            <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>{q.explanation}</ReactMarkdown>
          </div>
          <button onClick={next} className="btn-primary w-full justify-center shrink-0">
            {current < questions.length - 1 ? 'Next question →' : 'See results'}
          </button>
        </>
      )}
    </div>
  );
}

/* ── Summary Component ───────────────────────────────── */
function SummaryViewer({ markdown }: { markdown: string }) {
  return (
    <div className="h-full overflow-y-auto p-4">
      <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--color-text-1)' }}>Summary</h3>
      <div className="prose prose-sm max-w-none text-sm leading-relaxed" style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-text-1)' }}>
        <ReactMarkdown remarkPlugins={[remarkMath, remarkGfm]} rehypePlugins={[rehypeKatex]}>{markdown}</ReactMarkdown>
      </div>
    </div>
  );
}

/* ── Progress Viewer ─────────────────────────────────── */
function ProgressViewer() {
  const concepts = [
    { label: 'Core Concepts', pct: 72 },
    { label: 'Key Definitions', pct: 88 },
    { label: 'Problem Solving', pct: 45 },
    { label: 'Advanced Topics', pct: 20 },
  ];
  const overall = Math.round(concepts.reduce((s, c) => s + c.pct, 0) / concepts.length);
  const r = 38, circ = 2 * Math.PI * r;

  return (
    <div className="p-4 overflow-y-auto h-full">
      <h3 className="text-sm font-semibold mb-4" style={{ color: 'var(--color-text-1)' }}>Your Progress</h3>
      {/* Ring */}
      <div className="flex flex-col items-center mb-5">
        <svg width="100" height="100">
          <circle cx="50" cy="50" r={r} className="ring-track" strokeWidth="8" />
          <circle
            cx="50" cy="50" r={r}
            className="ring-fill"
            strokeWidth="8"
            strokeDasharray={circ}
            strokeDashoffset={circ - (overall / 100) * circ}
            transform="rotate(-90 50 50)"
          />
          <text x="50" y="46" textAnchor="middle" fontSize="16" fontWeight="700" fill="var(--color-accent)">{overall}%</text>
          <text x="50" y="60" textAnchor="middle" fontSize="9" fill="var(--color-text-3)">mastery</text>
        </svg>
      </div>
      <div className="space-y-3">
        {concepts.map(c => (
          <div key={c.label}>
            <div className="flex justify-between text-xs mb-1" style={{ color: 'var(--color-text-2)' }}>
              <span>{c.label}</span>
              <span className="font-medium">{c.pct}%</span>
            </div>
            <div className="progress-bar-track h-1.5">
              <div className="progress-bar-fill h-1.5" style={{ width: `${c.pct}%` }} />
            </div>
          </div>
        ))}
      </div>
      <div className="mt-5 p-3 rounded-xl text-xs leading-relaxed" style={{ background: 'var(--color-accent-light)', color: 'var(--color-accent)' }}>
        💡 Keep going! Focus on Problem Solving and Advanced Topics to reach 80%+ overall mastery.
      </div>
    </div>
  );
}

/* ── Tool Grid (idle state) ──────────────────────────── */
const TOOLS = [
  { type: 'flashcards', icon: '🃏', label: 'Flashcards', desc: 'Study key terms' },
  { type: 'quiz',       icon: '🎯', label: 'Quiz',       desc: 'Test yourself' },
  { type: 'summary',    icon: '📋', label: 'Summary',    desc: 'Quick overview' },
  { type: 'progress',   icon: '📊', label: 'Progress',   desc: 'Your mastery' },
];

/* ── Main StudioPanel ────────────────────────────────── */
export default function StudioPanel({ mode, onClose }: Props) {
  return (
    <div
      className="flex flex-col h-full"
      style={{
        width: '280px',
        minWidth: '280px',
        background: '#fff',
        borderLeft: '1px solid var(--color-border)',
      }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-3 shrink-0"
        style={{ borderBottom: '1px solid var(--color-border)' }}
      >
        <span className="text-sm font-semibold" style={{ color: 'var(--color-text-1)' }}>
          {mode.type === 'idle' ? 'Studio' :
           mode.type === 'flashcards' ? '🃏 Flashcards' :
           mode.type === 'quiz'       ? '🎯 Quiz' :
           mode.type === 'summary'    ? '📋 Summary' : '📊 Progress'}
        </span>
        {mode.type !== 'idle' && (
          <button
            onClick={onClose}
            className="text-sm px-2 py-1 rounded-md transition-colors"
            style={{ color: 'var(--color-text-3)' }}
            onMouseEnter={e => (e.currentTarget as HTMLElement).style.color = 'var(--color-text-1)'}
            onMouseLeave={e => (e.currentTarget as HTMLElement).style.color = 'var(--color-text-3)'}
          >
            ✕
          </button>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {mode.type === 'idle' && (
          <div className="p-4">
            <p className="text-xs mb-4" style={{ color: 'var(--color-text-3)' }}>
              Studio output will be saved here. Add sources and use the chat to generate study tools.
            </p>
            <div className="grid grid-cols-2 gap-2">
              {TOOLS.map(tool => (
                <div key={tool.type} className="studio-tool">
                  <span className="studio-tool-icon">{tool.icon}</span>
                  <span className="studio-tool-label">{tool.label}</span>
                  <span className="studio-tool-desc">{tool.desc}</span>
                </div>
              ))}
            </div>
            <div
              className="mt-4 rounded-xl p-4 text-center"
              style={{ border: '1.5px dashed var(--color-border-strong)' }}
            >
              <div className="text-2xl mb-1">✨</div>
              <div className="text-xs" style={{ color: 'var(--color-text-3)' }}>
                Use the chat commands or buttons to generate flashcards, quizzes, and more
              </div>
            </div>
          </div>
        )}
        {mode.type === 'flashcards' && <FlashcardViewer cards={mode.cards} />}
        {mode.type === 'quiz'       && <QuizViewer questions={mode.questions} />}
        {mode.type === 'summary'    && <SummaryViewer markdown={mode.markdown} />}
        {mode.type === 'progress'   && <ProgressViewer />}
      </div>
    </div>
  );
}
