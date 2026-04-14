import { useRef, useEffect, useState } from 'react';

export default function Scratchpad() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [isDrawing, setIsDrawing] = useState(false);
  const [color, setColor] = useState('#4F46E5');

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Set canvas size to match container
    const resize = () => {
      const rect = canvas.parentElement?.getBoundingClientRect();
      if (rect) {
        canvas.width = rect.width;
        canvas.height = rect.height;
        ctx.lineJoin = 'round';
        ctx.lineCap = 'round';
        ctx.lineWidth = 3;
      }
    };

    resize();
    window.addEventListener('resize', resize);
    return () => window.removeEventListener('resize', resize);
  }, []);

  const startDrawing = (e: React.MouseEvent | React.TouchEvent) => {
    setIsDrawing(true);
    draw(e);
  };

  const stopDrawing = () => {
    setIsDrawing(false);
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    ctx?.beginPath();
  };

  const draw = (e: React.MouseEvent | React.TouchEvent) => {
    if (!isDrawing) return;
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!ctx || !canvas) return;

    ctx.strokeStyle = color;

    const rect = canvas.getBoundingClientRect();
    const x = ('touches' in e ? e.touches[0].clientX : e.clientX) - rect.left;
    const y = ('touches' in e ? e.touches[0].clientY : e.clientY) - rect.top;

    ctx.lineTo(x, y);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(x, y);
  };

  const clear = () => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (ctx && canvas) {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
    }
  };

  return (
    <div className="h-full flex flex-col bg-white overflow-hidden">
      {/* Toolbar */}
      <div className="px-6 py-3 border-b bg-white border-gray-100 shrink-0 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="flex gap-1.5 bg-gray-50 p-1 rounded-xl">
            {['#4F46E5', '#10B981', '#EF4444', '#111827'].map(c => (
              <button
                key={c}
                onClick={() => setColor(c)}
                className={`w-6 h-6 rounded-lg transition-all border-2 ${color === c ? 'border-white ring-2 ring-indigo-500 scale-110' : 'border-transparent'}`}
                style={{ background: c }}
              />
            ))}
          </div>
          <span className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Scratchpad</span>
        </div>
        <button
          onClick={clear}
          className="text-[10px] font-bold text-red-500 uppercase tracking-widest hover:bg-red-50 px-3 py-1.5 rounded-lg transition-all"
        >
          Clear Workspace
        </button>
      </div>

      {/* Canvas */}
      <div className="flex-1 relative touch-none">
        <canvas
          ref={canvasRef}
          onMouseDown={startDrawing}
          onMouseUp={stopDrawing}
          onMouseMove={draw}
          onMouseOut={stopDrawing}
          onTouchStart={startDrawing}
          onTouchEnd={stopDrawing}
          onTouchMove={draw}
          className="w-full h-full cursor-crosshair"
        />
      </div>
      
      {/* Tip */}
      <div className="p-4 text-center bg-gray-50/50 border-t border-gray-50">
        <p className="text-[10px] font-medium text-gray-400 italic">
          Use this space to work out derivations or sketch diagrams.
        </p>
      </div>
    </div>
  );
}
