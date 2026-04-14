import { useState } from "react";

interface Props {
  onComplete: () => void;
}

export default function MockQuizCard({ onComplete }: Props) {
  const [selected, setSelected] = useState<number | null>(null);
  const [step, setStep] = useState(0);

  const question = "Which optical instrument was used to measure the change in the speed of light in the Michelson-Morley experiment?";
  const options = [
    "A) Diffraction Grating",
    "B) Michelson Interferometer",
    "C) Electron Microscope",
    "D) Prismatic Spectrometer"
  ];

  const handleSelect = (idx: number) => {
    setSelected(idx);
    setStep(1); // Evaluating
    setTimeout(() => {
      if (idx === 1) { // B is correct
        setStep(2); // Correct!
        setTimeout(() => {
          onComplete(); // Jump back to chat
        }, 2000);
      } else {
        setStep(3); // Incorrect
        setTimeout(() => {
          setSelected(null);
          setStep(0);
        }, 1500);
      }
    }, 1000);
  };

  return (
    <div className="flex-1 flex items-center justify-center p-8 bg-[url('https://www.transparenttextures.com/patterns/notebook.png')] animate-slide-up relative bg-cover bg-center" style={{ backgroundColor: '#F8F6F0' }}>
      
      <div className="absolute top-0 right-0 p-8 font-[var(--font-mono)] text-sm tracking-[0.2em] uppercase text-[var(--color-ink-light)] text-right">
        Assessment <br/> Target: Section 01
      </div>

      <div className="w-full max-w-2xl bg-white brutal-border p-10 md:p-14 relative overflow-hidden">
        {step === 1 && (
          <div className="absolute inset-0 bg-black/5 flex items-center justify-center z-10 font-[var(--font-mono)] text-[var(--color-accent-cyan)] font-bold text-xl uppercase tracking-widest backdrop-blur-sm">
            <span className="animate-pulse">Evaluating Sequence...</span>
          </div>
        )}
        
        {step === 2 && (
          <div className="absolute inset-0 bg-[var(--color-accent-cyan)] flex items-center justify-center z-10 font-[var(--font-mono)] text-black font-bold text-3xl uppercase tracking-widest animate-slide-up">
            Response Verified
          </div>
        )}

        {step === 3 && (
          <div className="absolute inset-0 bg-[var(--color-accent-magenta)] flex items-center justify-center z-10 font-[var(--font-mono)] text-white font-bold text-3xl uppercase tracking-widest animate-slide-up">
            Calibration Error
          </div>
        )}

        <div className="font-[var(--font-mono)] text-xs font-bold bg-black text-white inline-block px-3 py-1 mb-8">
          MODULE 01 /// QUESTION 01
        </div>
        
        <h2 className="text-3xl lg:text-4xl font-[var(--font-serif-display)] leading-tight mb-10 text-balance border-b border-black pb-8">
          {question}
        </h2>

        <div className="space-y-4 font-sans text-lg">
          {options.map((opt, i) => (
            <button
              key={i}
              onClick={() => handleSelect(i)}
              disabled={step !== 0}
              className={`w-full text-left p-5 brutal-border transition-all flex items-center group
                ${selected === i ? 'bg-black text-[var(--color-accent-cyan)]' : 'bg-white hover:bg-[var(--color-paper)]'}
              `}
            >
              <span className={`inline-block w-8 font-[var(--font-mono)] font-bold transition-transform group-hover:translate-x-2 ${selected === i ? 'text-[var(--color-accent-magenta)]' : 'text-[#888]'}`}>
                {">"}
              </span>
              <span className={selected === i ? 'font-bold' : ''}>{opt}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
