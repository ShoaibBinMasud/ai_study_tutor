import { useState, useRef, useEffect } from "react";
import type { MessageData } from "../types";
import ReactMarkdown from "react-markdown";

interface Props {
  messages: MessageData[];
  onSendMessage: (msg: string) => void;
  agentStatus: string;
}

export default function MockChatBox({ messages, onSendMessage, agentStatus }: Props) {
  const [input, setInput] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, agentStatus]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;
    onSendMessage(input);
    setInput("");
  };

  return (
    <div className="flex-1 flex flex-col h-full bg-white relative">
      <div className="flex-1 overflow-y-auto p-8 font-[var(--font-serif-body)] text-lg md:text-xl leading-relaxed space-y-12">
        {messages.map((msg, i) => (
          <div 
            key={msg.id} 
            className={`flex flex-col animate-slide-up bg-white p-6 relative
              ${msg.role === 'user' ? 'brutal-border max-w-[80%] ml-auto bg-[var(--color-paper)]' : 'brutal-border-inset max-w-[90%] mr-auto'}
            `}
          >
            <span className="font-[var(--font-mono)] text-[10px] uppercase tracking-[0.2em] mb-4 text-[#888] font-bold">
              {msg.role === "user" ? "Student Query" : "Tutor Response"}
            </span>
            <div className={`prose prose-lg max-w-none ${msg.role === 'assistant' ? 'text-[var(--color-ink)]' : 'font-sans'}`}>
              <ReactMarkdown>{msg.text}</ReactMarkdown>
            </div>
            {msg.role === 'assistant' && i === messages.length - 1 && (
               <div className="absolute -bottom-1 -right-1 w-3 h-3 bg-black brutal-border"></div>
            )}
          </div>
        ))}
        {agentStatus !== "Idle" && (
          <div className="max-w-[80%] flex flex-col font-[var(--font-mono)] text-sm animate-pulse text-[var(--color-accent-magenta)] p-4">
             <span>[ System Active: {agentStatus} ]</span>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <div className="p-6 border-t-[1.5px] border-[var(--color-ink)] bg-[#FAFAFA]">
        <form onSubmit={handleSubmit} className="flex gap-4 max-w-4xl mx-auto items-end">
          <div className="flex-1 brutal-border bg-white focus-within:ring-2 ring-[var(--color-accent-cyan)] transition-shadow">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="E.g., teach me section 1-2..."
              className="w-full bg-transparent p-4 outline-none resize-none min-h-[60px] font-sans text-base max-h-[120px]"
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSubmit(e);
                }
              }}
            />
          </div>
          <button 
            type="submit" 
            disabled={!input.trim() || agentStatus !== "Idle"}
            className="h-[60px] px-8 bg-black text-white brutal-border font-[var(--font-mono)] uppercase text-sm tracking-widest hover:text-[var(--color-accent-cyan)] transition-colors disabled:opacity-50"
          >
            Send
          </button>
        </form>
      </div>
    </div>
  );
}
