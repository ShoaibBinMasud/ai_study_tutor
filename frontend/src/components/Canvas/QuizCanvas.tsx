import { useState } from 'react';
import type { QuizQuestion } from '../../types';

interface Props {
  questions: QuizQuestion[];
}

export default function QuizCanvas({ questions }: Props) {
  const [current, setCurrent] = useState(0);
  const [selectedOption, setSelectedOption] = useState<number | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [score, setScore] = useState(0);
  const [finished, setFinished] = useState(false);

  if (!questions || questions.length === 0) return null;
  
  const question = questions[current];
  const isLast = current === questions.length - 1;

  const handleSubmit = () => {
    if (selectedOption === null) return;
    setSubmitted(true);
    if (selectedOption === question.correctAnswer) {
      setScore(s => s + 1);
    }
  };

  const handleNext = () => {
    if (isLast) {
      setFinished(true);
    } else {
      setCurrent(c => c + 1);
      setSelectedOption(null);
      setSubmitted(false);
    }
  };

  if (finished) {
    const finalScore = Math.round((score / questions.length) * 100);
    return (
      <div className="h-full flex flex-col items-center justify-center p-8 text-center bg-white">
        <div className="w-24 h-24 rounded-full bg-indigo-50 flex items-center justify-center text-4xl mb-6 shadow-sm">
          🏆
        </div>
        <h2 className="text-2xl font-bold text-gray-900 mb-2">Quiz Complete!</h2>
        <div className="text-4xl font-black text-indigo-600 mb-4">{finalScore}%</div>
        <p className="text-gray-500 max-w-xs mb-8">
          Great work! You've mastered {score} out of {questions.length} topics in this unit.
        </p>
        <button 
          onClick={() => { setCurrent(0); setScore(0); setFinished(false); setSubmitted(false); setSelectedOption(null); }}
          className="btn-primary"
        >
          Retake Quiz
        </button>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-white overflow-hidden p-6 sm:p-8">
      {/* Header */}
      <header className="flex items-center justify-between mb-8 pb-4 border-b border-gray-50">
        <div>
          <h2 className="text-lg font-bold text-gray-900 leading-none tracking-tight">Active Assessment</h2>
          <p className="text-[10px] text-gray-400 font-bold uppercase tracking-widest mt-2 px-1">
            Question {current + 1} of {questions.length}
          </p>
        </div>
        <div className="h-2 w-32 bg-gray-100 rounded-full overflow-hidden">
          <div 
            className="h-full bg-indigo-500 transition-all duration-700" 
            style={{ width: `${((current + 1) / questions.length) * 100}%` }}
          />
        </div>
      </header>

      {/* Question */}
      <div className="flex-1 overflow-y-auto space-y-8 scrollbar-thin">
        <h3 className="text-xl font-bold text-gray-900 leading-snug">
          {question.question}
        </h3>

        <div className="space-y-3">
          {question.options.map((option, i) => {
            const isSelected = selectedOption === i;
            const isCorrect = i === question.correctAnswer;
            const showCorrect = submitted && isCorrect;
            const showWrong = submitted && isSelected && !isCorrect;

            return (
              <button
                key={i}
                disabled={submitted}
                onClick={() => setSelectedOption(i)}
                className={`w-full flex items-center p-4 rounded-2xl border-2 transition-all duration-300 text-left ${
                  showCorrect ? 'bg-green-50 border-green-500 shadow-sm' :
                  showWrong ? 'bg-red-50 border-red-500' :
                  isSelected ? 'bg-indigo-50 border-indigo-500 shadow-sm translate-x-1' :
                  'bg-white border-gray-100 hover:border-indigo-200'
                }`}
              >
                <div className={`w-7 h-7 rounded-lg flex items-center justify-center font-bold text-xs mr-4 shrink-0 transition-all ${
                  showCorrect ? 'bg-green-500 text-white' :
                  showWrong ? 'bg-red-500 text-white' :
                  isSelected ? 'bg-indigo-500 text-white' :
                  'bg-gray-100 text-gray-400'
                }`}>
                  {String.fromCharCode(65 + i)}
                </div>
                <div className={`text-sm font-semibold transition-all ${
                  showCorrect ? 'text-green-800' :
                  showWrong ? 'text-red-800' :
                  isSelected ? 'text-indigo-800' :
                  'text-gray-700'
                }`}>
                  {option}
                </div>
              </button>
            );
          })}
        </div>

        {submitted && (
          <div className={`p-5 rounded-2xl border animate-in slide-in-from-bottom duration-500 ${
            selectedOption === question.correctAnswer ? 'bg-green-50 border-green-100' : 'bg-red-50 border-red-100'
          }`}>
            <div className="flex items-center gap-2 mb-2 font-bold text-xs uppercase tracking-[0.1em]">
              {selectedOption === question.correctAnswer ? (
                <span className="text-green-600">✓ Correct</span>
              ) : (
                <span className="text-red-600">✗ Focus Required</span>
              )}
            </div>
            <p className={`text-xs leading-relaxed font-medium ${
              selectedOption === question.correctAnswer ? 'text-green-700' : 'text-red-700'
            }`}>
              {question.explanation}
            </p>
          </div>
        )}
      </div>

      {/* Footer Nav */}
      <footer className="mt-8 pt-6 border-t border-gray-50 flex items-center justify-end gap-3 shrink-0">
        {!submitted ? (
          <button
            onClick={handleSubmit}
            disabled={selectedOption === null}
            className="btn-primary px-10 py-3 rounded-2xl"
          >
            Submit Answer
          </button>
        ) : (
          <button
            onClick={handleNext}
            className="btn-primary px-10 py-3 rounded-2xl"
            style={{ background: 'var(--color-accent)', color: '#fff' }}
          >
            {isLast ? 'Finish Results' : 'Next Question →'}
          </button>
        )}
      </footer>
    </div>
  );
}
