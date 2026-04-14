import { useEffect, useRef, useState, memo } from 'react';
import mermaid from 'mermaid';

// Initialize mermaid once outside the component
mermaid.initialize({
  startOnLoad: false,
  theme: 'base',
  themeVariables: {
    fontFamily: 'var(--font-sans), system-ui, sans-serif',
    primaryColor: '#EEF2FF',
    primaryTextColor: '#1A1A1A',
    primaryBorderColor: '#4F46E5',
    lineColor: '#9B9A95',
    secondaryColor: '#fff',
    tertiaryColor: '#fff',
    fontSize: '14px',
  },
  securityLevel: 'loose',
});

interface MermaidProps {
  chart: string;
}

const Mermaid = memo(({ chart }: MermaidProps) => {
  const [svg, setSvg] = useState<string>('');
  const [error, setError] = useState<boolean>(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const chartId = useRef(`mermaid-${Math.random().toString(36).slice(2, 9)}`).current;

  useEffect(() => {
    let isMounted = true;

    const renderChart = async () => {
      try {
        // Validate chart before rendering
        const isValid = await mermaid.parse(chart);
        if (!isValid) throw new Error('Invalid mermaid syntax');

        const { svg: renderedSvg } = await mermaid.render(chartId, chart);
        
        if (isMounted) {
          setSvg(renderedSvg);
          setError(false);
        }
      } catch (err) {
        console.error('Mermaid render error:', err);
        if (isMounted) {
          setError(true);
        }
      }
    };

    renderChart();

    return () => {
      isMounted = false;
    };
  }, [chart, chartId]);

  if (error) {
    return (
      <div className="p-4 bg-red-50 border border-red-100 rounded-xl text-center">
        <p className="text-xs text-red-600 font-mono">⚠️ Diagram format error</p>
        <pre className="mt-2 text-[10px] text-red-400 overflow-x-auto text-left whitespace-pre-wrap">{chart}</pre>
      </div>
    );
  }

  return (
    <div 
      ref={containerRef}
      className="mermaid-container flex justify-center w-full overflow-x-auto py-2"
      dangerouslySetInnerHTML={{ __html: svg || '<div class="h-32 w-full bg-gray-50 animate-pulse rounded-lg"></div>' }}
    />
  );
});

export default Mermaid;
