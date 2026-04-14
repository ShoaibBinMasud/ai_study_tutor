import type { Message } from '../types';

interface Props {
  message: Message;
}

export default function UserMessage({ message }: Props) {
  return (
    <div className="anim-fade-up flex flex-col items-end gap-2">
      <div
        className="rounded-2xl"
        style={{
          background: 'var(--color-surface-2)',
          color: 'var(--color-text-1)',
          padding: '12px 18px',
          fontFamily: 'var(--font-sans)',
          fontSize: '0.9rem',
          lineHeight: 1.5,
          border: '1px solid var(--color-border)',
        }}
      >
        <span className="whitespace-pre-wrap">{message.content}</span>
      </div>
    </div>
  );
}
