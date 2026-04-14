import { useEffect, useRef, useMemo } from 'react';
import ProgressRing from './ProgressRing';
import type { LearningPathPlan, LearningPathUnit } from '../types';

interface Props {
  plan: LearningPathPlan;
  onConceptClick?: (unitId: string) => void;
}

export default function ContextPanel({ plan, onConceptClick }: Props) {
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const currentRef = useRef<HTMLDivElement>(null);

  // Split plan into sections safely with useMemo
  const { mastered, current, upcoming } = useMemo(() => {
    const m: LearningPathUnit[] = [];
    const u: LearningPathUnit[] = [];
    let cur: LearningPathUnit | null = null;
    let found = false;

    if (plan && plan.sources) {
      plan.sources.forEach(src => {
        if (src.units) {
          src.units.forEach(unit => {
            if (unit.completed) {
              m.push({ ...unit, sourceId: src.sourceId });
            } else if (!found) {
              cur = { ...unit, sourceId: src.sourceId };
              found = true;
            } else {
              u.push({ ...unit, sourceId: src.sourceId });
            }
          });
        }
      });
    }

    return { mastered: m, current: cur, upcoming: u };
  }, [plan]);

  // Auto-scroll logic (scroll the current concept into view when it changes)
  useEffect(() => {
    if (currentRef.current && scrollContainerRef.current) {
      const container = scrollContainerRef.current;
      const element = currentRef.current;
      const offset = 40; // Pin to top with small margin
      container.scrollTo({
        top: element.offsetTop - offset,
        behavior: 'smooth'
      });
    }
  }, [current?.unitId]);

  const total = mastered.length + upcoming.length + (current ? 1 : 0);
  const pct = total === 0 ? 0 : Math.round((mastered.length / total) * 100);

  const ringLabel = pct === 0
    ? "You're just getting started"
    : pct === 100
    ? 'All concepts completed'
    : `${pct}% completed`;

  return (
    <div
      style={{
        width: '300px',
        flexShrink: 0,
        borderLeft: '1px solid var(--color-border)',
        background: 'var(--color-bg)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      {/* Top - Fixed Progress Section */}
      <div style={{ 
        padding: '32px 24px 24px', 
        display: 'flex', 
        flexDirection: 'column', 
        alignItems: 'center', 
        gap: '12px', 
        textAlign: 'center',
        borderBottom: '1px solid var(--color-border)',
        zIndex: 10,
        background: 'var(--color-bg)',
      }}>
        <ProgressRing pct={pct} size={72} strokeWidth={3}>
          <span style={{
            fontSize: '0.9rem',
            fontWeight: 600,
            color: pct === 0 ? 'var(--color-text-3)' : 'var(--color-accent)',
            fontFamily: 'var(--font-sans)',
          }}>
            {pct}%
          </span>
        </ProgressRing>
        <p style={{
          fontSize: '0.75rem',
          color: 'var(--color-text-3)',
          fontFamily: 'var(--font-sans)',
          letterSpacing: '0.01em',
          margin: 0,
        }}>
          {ringLabel}
        </p>
      </div>

      {/* Bottom - Scrollable Learning Timeline */}
      <div 
        ref={scrollContainerRef}
        className="scrollbar-thin"
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '32px 24px 80px',
          position: 'relative',
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '48px', position: 'relative' }}>
          
          {/* Vertical Track Line */}
          <div style={{
            position: 'absolute',
            left: '5px',
            top: '8px',
            bottom: '8px',
            width: '1px',
            background: 'var(--color-border)',
            opacity: 0.6,
          }} />

          {/* Completed Section */}
          {mastered.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
              <span style={{
                fontSize: '0.62rem', letterSpacing: '0.1em', textTransform: 'uppercase',
                color: 'var(--color-text-3)', fontFamily: 'var(--font-sans)', fontWeight: 600,
              }}>
                Completed
              </span>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                {mastered.map((item) => (
                  <div 
                    key={item.unitId} 
                    onClick={() => onConceptClick?.(item.unitId)}
                    style={{ 
                      display: 'flex', 
                      gap: '20px', 
                      position: 'relative', 
                      cursor: 'pointer',
                    }}
                  >
                    <div style={{
                      width: '11px', height: '11px', borderRadius: '50%',
                      background: '#4ade80',
                      border: '3px solid var(--color-bg)',
                      zIndex: 2,
                      marginTop: '5px',
                    }} />
                    <div style={{ opacity: 0.6 }}>
                      <h4 style={{
                        margin: 0, fontSize: '0.88rem', color: 'var(--color-text-3)',
                        fontFamily: 'var(--font-serif)', fontStyle: 'italic',
                        fontWeight: 400,
                        lineHeight: 1.4,
                      }}>
                        {item.title}
                      </h4>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Current Section */}
          {current && (
            <div ref={currentRef} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <span style={{
                fontSize: '0.62rem', letterSpacing: '0.12em', textTransform: 'uppercase',
                color: 'var(--color-accent)', fontFamily: 'var(--font-sans)', fontWeight: 700,
              }}>
                Current
              </span>
              <div 
                onClick={() => onConceptClick?.(current!.unitId)}
                style={{ display: 'flex', gap: '20px', position: 'relative', cursor: 'pointer' }}
              >
                <div style={{
                  width: '12px', height: '12px', borderRadius: '50%',
                  background: 'var(--color-accent)',
                  boxShadow: '0 0 12px rgba(198,168,91,0.5)',
                  border: '3px solid var(--color-bg)',
                  zIndex: 2,
                  marginTop: '8px',
                }} />
                <div>
                  <h3 style={{
                    fontFamily: 'var(--font-display)', fontSize: '1.35rem', fontWeight: 800,
                    color: 'var(--color-text-1)', margin: 0, lineHeight: 1.2,
                    letterSpacing: '-0.02em',
                  }}>
                    {current.title}
                  </h3>
                  <p style={{ margin: '6px 0 0', fontSize: '0.78rem', color: 'var(--color-text-3)', fontFamily: 'var(--font-sans)', fontStyle: 'italic' }}>
                    {(current as any).sourceId?.replace(/_/g, ' ')}
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Upcoming Section */}
          {upcoming.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
              <span style={{
                fontSize: '0.62rem', letterSpacing: '0.1em', textTransform: 'uppercase',
                color: 'var(--color-text-3)', fontFamily: 'var(--font-sans)', fontWeight: 600,
              }}>
                Upcoming
              </span>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                {upcoming.map((item) => (
                  <div key={item.unitId} style={{ display: 'flex', gap: '20px', position: 'relative' }}>
                    <div style={{
                      width: '11px', height: '11px', borderRadius: '50%',
                      background: 'var(--color-bg)',
                      border: '2px solid var(--color-border-md)',
                      zIndex: 2,
                      marginTop: '5px',
                    }} />
                    <div>
                      <h4 style={{
                        margin: 0, fontSize: '0.88rem', color: 'var(--color-text-2)',
                        fontFamily: 'var(--font-serif)', fontWeight: 400,
                        lineHeight: 1.4,
                        opacity: 0.9,
                      }}>
                        {item.title}
                      </h4>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      <div style={{ padding: '20px 24px', borderTop: '1px solid var(--color-border)', background: 'var(--color-surface)' }}>
        <p style={{
          fontSize: '0.65rem',
          color: 'var(--color-text-3)',
          fontFamily: 'var(--font-sans)',
          lineHeight: 1.6,
          margin: 0,
          opacity: 0.8,
        }}>
          Every concept completed builds the foundation for the next.
        </p>
      </div>
    </div>
  );
}
