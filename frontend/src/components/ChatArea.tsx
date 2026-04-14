import { useEffect, useRef } from 'react';
import type { Message } from '../types';
import TutorMessage from './TutorMessage';
import UserMessage from './UserMessage';

interface Props {
  messages: Message[];
  isThinking: boolean;
  showProceedPrompt: boolean;
  onAction: (action: 'simpler' | 'deeper', messageId: string) => void;
  targetUnitId?: string | null;
}

function ThinkingIndicator() {
  return (
    <div className="anim-fade-in flex items-center gap-3" style={{ padding: '4px 0' }}>
      <div
        style={{
          width: '28px', height: '28px', borderRadius: '50%',
          background: 'rgba(198,168,91,0.1)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
        }}
      >
        <span style={{ fontSize: '10px', color: '#c6a85b', fontFamily: 'var(--font-sans)', fontWeight: 600 }}>Dr</span>
      </div>
      <div
        style={{
          display: 'flex', gap: '5px', alignItems: 'center',
          background: 'var(--color-surface)',
          border: '1px solid var(--color-border)',
          borderRadius: '16px',
          padding: '12px 18px',
        }}
      >
        <span style={{ fontSize: '0.75rem', color: 'var(--color-text-3)', marginRight: '4px', fontFamily: 'var(--font-sans)' }}>Thinking</span>
        {[0, 1, 2].map(i => (
          <div
            key={i}
            className="thinking-dot"
            style={{
              width: '5px', height: '5px', borderRadius: '50%',
              background: 'var(--color-accent)',
              animationDelay: `${i * 0.2}s`,
            }}
          />
        ))}
      </div>
    </div>
  );
}

export default function ChatArea({ 
  messages, 
  isThinking, 
  showProceedPrompt, 
  onAction,
  targetUnitId 
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  const prevMsgCountRef = useRef(messages.length);
  const prevThinkingRef = useRef(isThinking);
  const prevPromptRef = useRef(showProceedPrompt);

  // Auto-scroll to bottom on new messages or state changes
  useEffect(() => {
    const hasNewMessage = messages.length > prevMsgCountRef.current;
    const thinkingStarted = isThinking && !prevThinkingRef.current;
    const promptAppeared = showProceedPrompt && !prevPromptRef.current;
    
    prevMsgCountRef.current = messages.length;
    prevThinkingRef.current = isThinking;
    prevPromptRef.current = showProceedPrompt;

    // Only scroll to bottom if we are NOT navigating AND something active happened
    if (!targetUnitId && (hasNewMessage || thinkingStarted || promptAppeared)) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages.length, isThinking, showProceedPrompt]); // No targetUnitId here

  // Jump to specific concept
  useEffect(() => {
    if (targetUnitId) {
      const element = document.getElementById(`unit-anchor-${targetUnitId}`);
      if (element) {
        element.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    }
  }, [targetUnitId]);

  return (
    <div
      ref={scrollContainerRef}
      className="scrollbar-thin"
      style={{
        flex: 1,
        overflowY: 'auto',
        padding: '40px 40px 32px',
        scrollPaddingTop: '20px',
      }}
    >
      <div style={{ maxWidth: '760px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '32px' }}>
        {messages.map((msg, idx) => {
          // Check if this is the FIRST message of this unit to set an anchor
          const isFirstOfUnit = msg.attachedUnitId && 
            (idx === 0 || messages[idx - 1].attachedUnitId !== msg.attachedUnitId);

          return (
            <div 
              key={msg.id} 
              id={isFirstOfUnit ? `unit-anchor-${msg.attachedUnitId}` : undefined}
              className="flex flex-col"
            >
              {msg.role === 'assistant' ? (
                <TutorMessage message={msg} onAction={onAction} />
              ) : (
                <UserMessage message={msg} />
              )}
            </div>
          );
        })}

        {isThinking && <ThinkingIndicator />}

        <div ref={bottomRef} style={{ height: '8px' }} />
      </div>
    </div>
  );
}
