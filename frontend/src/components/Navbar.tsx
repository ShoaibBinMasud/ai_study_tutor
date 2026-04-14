export default function Navbar({ 
  sessionTitle = 'Physics Midterm Prep',
  isDarkMode,
  onToggleTheme
}: { 
  sessionTitle?: string;
  isDarkMode: boolean;
  onToggleTheme: () => void;
}) {
  return (
    <nav
      style={{
        height: '64px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 32px',
        background: 'var(--color-bg)',
        borderBottom: '1px solid var(--color-border)',
        flexShrink: 0,
        zIndex: 50,
      }}
    >
      {/* Left — Logo */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', minWidth: '160px' }}>
        <div
          style={{
            width: '28px',
            height: '28px',
            borderRadius: '8px',
            background: 'var(--color-accent-dim)',
            border: '1px solid rgba(198,168,91,0.25)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M7 1L12 4V10L7 13L2 10V4L7 1Z" stroke="var(--color-accent)" strokeWidth="1.5" strokeLinejoin="round"/>
          </svg>
        </div>
        <span style={{
          fontSize: '1.2rem',
          fontWeight: 500,
          color: 'var(--color-text-1)',
          fontFamily: '"EB Garamond", serif',
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
        }}>
          Aurum
        </span>
      </div>

      {/* Center — Session title */}
      <div style={{ textAlign: 'center' }}>
        <div style={{
          fontFamily: 'var(--font-display)',
          fontSize: '1.05rem',
          fontWeight: 500,
          color: 'var(--color-text-1)',
          letterSpacing: '-0.01em',
        }}>
          {sessionTitle}
        </div>
        <div style={{
          fontSize: '0.7rem',
          color: 'var(--color-text-3)',
          fontFamily: 'var(--font-sans)',
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
          marginTop: '1px',
        }}>
          Private Session
        </div>
      </div>

      {/* Right — Status + Avatar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px', minWidth: '160px', justifyContent: 'flex-end' }}>
        {/* Theme Toggle */}
        <button 
          className="theme-toggle"
          onClick={onToggleTheme}
          title={isDarkMode ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
        >
          {isDarkMode ? (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="5"/><path d="M12 1v2m0 18v2M4.22 4.22l1.42 1.42m12.72 12.72l1.42 1.42M1 12h2m18 0h2M4.22 19.78l1.42-1.42M17.66 6.34l1.42-1.42"/>
            </svg>
          ) : (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
            </svg>
          )}
        </button>

        <div style={{ display: 'flex', alignItems: 'center', gap: '7px' }}>
          <div style={{
            width: '7px',
            height: '7px',
            borderRadius: '50%',
            background: '#4ade80',
            boxShadow: '0 0 6px rgba(74, 222, 128, 0.6)',
          }} />
          <span style={{
            fontSize: '0.72rem',
            color: 'var(--color-text-3)',
            fontFamily: 'var(--font-sans)',
            letterSpacing: '0.03em',
          }}>
            Session Active
          </span>
        </div>

        {/* Avatar */}
        <div
          style={{
            width: '34px',
            height: '34px',
            borderRadius: '50%',
            background: 'var(--color-surface-2)',
            border: '1px solid var(--color-border-md)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '0.8rem',
            fontWeight: 600,
            color: 'var(--color-text-2)',
            fontFamily: 'var(--font-sans)',
            cursor: 'pointer',
          }}
        >
          S
        </div>
      </div>
    </nav>
  );
}
