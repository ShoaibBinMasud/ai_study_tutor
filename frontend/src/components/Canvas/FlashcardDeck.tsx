import { useState, memo } from 'react';
import type { Flashcard } from '../../types';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';

interface Props {
  cards: Flashcard[];
}

const Card = memo(({ card, index, total }: { card: Flashcard; index: number; total: number }) => {
  const [flipped, setFlipped] = useState(false);
  const [known, setKnown] = useState<null | boolean>(null);

  return (
    <div className="flex flex-col items-center h-full space-y-6">
      {/* 3D Flip Container */}
      <div 
        className={`relative w-full flex-1 perspective-1000 cursor-pointer max-h-[320px] transition-transform duration-500 transform-gpu ${flipped ? 'rotate-y-180' : ''}`} 
        onClick={() => setFlipped(!flipped)}
        style={{ transformStyle: 'preserve-3d' }}
      >
        {/* Front */}
        <div className={`absolute inset-0 backface-hidden flex flex-col items-center justify-center p-8 text-center bg-white border border-gray-100 rounded-3xl shadow-lg`}>
          <div className="text-[10px] font-bold text-indigo-400 uppercase tracking-[0.2em] mb-4">Question</div>
          <div className="text-xl font-bold text-gray-900 leading-snug">{card.front}</div>
          <div className="mt-8 text-[11px] text-gray-400 font-medium italic animate-pulse">tap to flip →</div>
        </div>

        {/* Back */}
        <div className={`absolute inset-0 backface-hidden rotate-y-180 flex flex-col items-center justify-center p-8 text-center bg-indigo-600 border border-indigo-500 rounded-3xl shadow-xl`}>
          <div className="text-[10px] font-bold text-indigo-200 uppercase tracking-[0.2em] mb-4">Mastery Answer</div>
          <div className="text-base font-medium text-white leading-relaxed prose-invert prose-sm">
            <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
              {card.back}
            </ReactMarkdown>
          </div>
        </div>
      </div>

      {/* Footer Actions */}
      <div className="flex items-center justify-center gap-3 w-full h-12">
        {flipped && known === null ? (
          <>
            <button 
              onClick={(e) => { e.stopPropagation(); setKnown(false); }} 
              className="flex-1 max-w-[140px] py-2.5 rounded-xl border-2 border-red-100 text-red-500 text-xs font-bold hover:bg-red-50 transition-all"
            >
              Still Learning
            </button>
            <button 
              onClick={(e) => { e.stopPropagation(); setKnown(true); }} 
              className="flex-1 max-w-[140px] py-2.5 rounded-xl border-2 border-green-100 text-green-600 text-xs font-bold hover:bg-green-50 transition-all shadow-sm shadow-green-100"
            >
              Got It!
            </button>
          </>
        ) : (
          <div className={`text-[11px] font-bold tracking-wide transition-all ${known === true ? 'text-green-600' : known === false ? 'text-red-500' : 'text-gray-400'}`}>
            {known === true ? '✓ Added to Mastery Path' : known === false ? '✗ Re-added to Focus List' : `Concept: ${card.concept}`}
          </div>
        )}
      </div>
    </div>
  );
});

export default function FlashcardDeck({ cards }: Props) {
  const [current, setCurrent] = useState(0);
  if (!cards || cards.length === 0) return null;
  const card = cards[current];
  const progress = Math.round(((current + 1) / cards.length) * 100);

  return (
    <div className="h-full flex flex-col bg-white overflow-hidden p-6">
      {/* Header Info */}
      <div className="flex items-end justify-between mb-8 shrink-0 border-b border-gray-50 pb-4">
        <div>
          <h2 className="text-xl font-extrabold text-gray-900 leading-none">Flashcards</h2>
          <p className="text-[11px] text-gray-400 font-bold uppercase tracking-wider mt-2">Active Deck: {card.concept}</p>
        </div>
        <div className="text-right">
          <div className="text-2xl font-black text-indigo-100 leading-none">{current + 1} <span className="text-xs text-gray-300">/ {cards.length}</span></div>
        </div>
      </div>

      {/* Main Container */}
      <div className="flex-1 min-h-0 flex flex-col relative">
        <Card key={card.id} card={card} index={current} total={cards.length} />
      </div>

      {/* Bottom Nav */}
      <div className="mt-8 flex items-center justify-between shrink-0">
        <button
          onClick={() => setCurrent(c => Math.max(0, c - 1))}
          disabled={current === 0}
          className="w-10 h-10 rounded-2xl flex items-center justify-center border border-gray-100 text-gray-400 hover:bg-gray-50 disabled:opacity-20 transition-all"
        >
          ←
        </button>
        <div className="flex gap-2">
          {cards.length < 15 && cards.map((_, i) => (
            <div key={i} className={`h-1 rounded-full transition-all duration-300 ${i === current ? 'w-6 bg-indigo-500' : 'w-1.5 bg-gray-100'}`} />
          ))}
        </div>
        <button
          onClick={() => setCurrent(c => Math.min(cards.length - 1, c + 1))}
          disabled={current === cards.length - 1}
          className="w-10 h-10 rounded-2xl flex items-center justify-center border border-gray-100 text-gray-400 hover:bg-gray-50 disabled:opacity-20 transition-all shadow-sm disabled:shadow-none"
        >
          →
        </button>
      </div>
    </div>
  );
}
