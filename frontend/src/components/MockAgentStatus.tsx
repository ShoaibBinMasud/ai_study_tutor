import { useEffect, useRef } from "react";

interface Props {
  status: string;
  logs: string[];
}

export default function MockAgentStatus({ status, logs }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs]);

  return (
    <div className="h-full flex flex-col pt-2 animate-slide-up bg-[#0A0A0A] text-[#E0E0E0] brutal-border p-4 relative tracking-tight shadow-none border-t-8 border-t-[var(--color-accent-magenta)] rounded-sm">
      <div className="flex justify-between items-center pb-4 border-b border-[#333]">
        <h3 className="font-[var(--font-mono)] text-sm font-bold uppercase tracking-widest text-[#FF0055]">Agent State</h3>
        <div className="flex gap-2">
          <div className="w-2 h-2 rounded-full bg-red-500"></div>
          <div className="w-2 h-2 rounded-full bg-yellow-500"></div>
          <div className="w-2 h-2 rounded-full bg-green-500"></div>
        </div>
      </div>
      
      <div className="py-6 flex-1 min-h-[150px]">
        <div className="text-[10px] font-[var(--font-mono)] text-[#666] mb-2 uppercase">Current Process</div>
        <div className="text-xl font-[var(--font-serif-display)] flex items-center gap-3">
          {status !== "Idle" && (
            <span className="w-3 h-3 bg-[var(--color-accent-cyan)] inline-block animate-pulse-glow brutal-border border-white"></span>
          )}
          <span className={status !== "Idle" ? "text-white" : "text-[#888]"}>{status}</span>
        </div>
      </div>

      <div className="flex-1 overflow-hidden flex flex-col min-h-0 border-t border-[#333] pt-4">
         <div className="text-[10px] font-[var(--font-mono)] text-[#666] mb-3 uppercase flex justify-between">
           <span>Execution Trace</span>
           <span>[SYS.LOG]</span>
         </div>
         <div 
           ref={scrollRef}
           className="flex-1 overflow-y-auto space-y-2 font-[var(--font-mono)] text-xs font-light scrollbar-hide pb-4"
           style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}
         >
           {logs.map((log, i) => (
             <div key={i} className="flex gap-3 animate-slide-up" style={{ animationDuration: '0.2s' }}>
                <span className="text-[#555]">{(i+1).toString().padStart(2, '0')}</span>
                <span className={`${log.includes('tool_call') ? 'text-[var(--color-accent-cyan)] font-bold' : log.includes('UNIT_COMPLETE') ? 'text-green-400' : 'text-[#AAA]'}`}>
                  {log}
                </span>
             </div>
           ))}
           {logs.length === 0 && (
             <div className="text-[#444] italic">Awaiting inputs...</div>
           )}
         </div>
      </div>
      
      <div className="pt-3 border-t border-[#333] flex justify-between items-center text-[10px] font-[var(--font-mono)] text-[#666]">
        <span>MEM: 24.1 MB</span>
        <span>OPS/S: 4.2K</span>
      </div>
    </div>
  );
}
