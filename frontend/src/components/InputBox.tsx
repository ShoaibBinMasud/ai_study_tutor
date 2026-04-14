import { useRef, useState } from 'react';

interface Props {
  onSend: (text: string) => void;
  disabled?: boolean;
  showProceedPrompt?: boolean;
  onProceed?: (choice: boolean) => void;
}

export default function InputBox({ onSend, disabled, showProceedPrompt, onProceed }: Props) {
  const [input, setInput] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const send = () => {
    const trimmed = input.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setInput('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  return (
    <div
      style={{
        borderTop: '1px solid var(--color-border)',
        background: 'var(--color-bg)',
        padding: '20px 32px 24px',
        flexShrink: 0,
      }}
    >
      <div style={{ maxWidth: '900px', margin: '0 auto' }}>
        {/* Proceed Prompt */}
        {showProceedPrompt && onProceed && (
          <div className="proceed-prompt mb-4 anim-fade-in">
            <span style={{ fontSize: '0.9rem', color: 'var(--color-text-2)', flex: 1, fontFamily: 'var(--font-sans)' }}>
              Shall we move on to the next concept?
            </span>
            <button
              onClick={() => onProceed(true)}
              style={{
                padding: '7px 18px',
                borderRadius: '99px',
                fontSize: '0.82rem',
                fontWeight: 500,
                cursor: 'pointer',
                transition: 'all 0.15s ease',
                border: '1px solid var(--color-accent)',
                background: 'var(--color-accent-dim)',
                color: 'var(--color-accent)',
                fontFamily: 'var(--font-sans)',
              }}
            >
              Yes, continue
            </button>
            <button
              onClick={() => onProceed(false)}
              style={{
                padding: '7px 18px',
                borderRadius: '99px',
                fontSize: '0.82rem',
                fontWeight: 500,
                cursor: 'pointer',
                transition: 'all 0.15s ease',
                border: '1px solid var(--color-border-md)',
                background: 'transparent',
                color: 'var(--color-text-3)',
                fontFamily: 'var(--font-sans)',
              }}
            >
              Not yet
            </button>
          </div>
        )}

        {/* Input */}
        <div
          className="input-glow flex items-end gap-3 rounded-2xl"
          style={{
            background: 'var(--color-surface)',
            border: '1px solid var(--color-border-md)',
            padding: '14px 16px',
            transition: 'box-shadow 0.2s ease',
          }}
        >
          {/* Attachment Button */}
          <button
            disabled={disabled}
            style={{
              width: '32px',
              height: '32px',
              borderRadius: '8px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              border: 'none',
              cursor: disabled ? 'not-allowed' : 'pointer',
              background: 'transparent',
              color: 'var(--color-text-3)',
              flexShrink: 0,
              transition: 'all 0.15s ease',
              marginBottom: '2px',
            }}
            className="hover:text-[var(--color-text-1)] hover:bg-[var(--color-surface-2)]"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" strokeLinecap="round" strokeLinejoin="round"/></svg>
          </button>

          <textarea
            ref={textareaRef}
            rows={1}
            value={input}
            placeholder={showProceedPrompt ? 'Or type a question…' : 'What would you like to understand next?'}
            onChange={(e) => {
              setInput(e.target.value);
              e.target.style.height = 'auto';
              e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`;
            }}
            onKeyDown={handleKeyDown}
            style={{
              flex: 1,
              resize: 'none',
              outline: 'none',
              border: 'none',
              background: 'transparent',
              fontFamily: 'var(--font-sans)',
              fontSize: '1rem',
              lineHeight: '1.6',
              color: 'var(--color-text-1)',
              minHeight: '28px',
            }}
          />
          <button
            onClick={send}
            disabled={!input.trim() || !!disabled}
            style={{
              width: '36px',
              height: '36px',
              borderRadius: '50%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              border: 'none',
              cursor: input.trim() && !disabled ? 'pointer' : 'not-allowed',
              background: input.trim() && !disabled ? 'var(--color-accent)' : 'rgba(255,255,255,0.05)',
              color: input.trim() && !disabled ? '#000' : 'var(--color-text-3)',
              flexShrink: 0,
              transition: 'all 0.15s ease',
            }}
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M8 13V3M3 8L8 3L13 8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>
        </div>

        <p style={{ textAlign: 'center', marginTop: '10px', fontSize: '0.7rem', color: 'var(--color-text-3)', fontFamily: 'var(--font-sans)' }}>
          Press Enter to send · Shift + Enter for new line
        </p>
      </div>
    </div>
  );
}
