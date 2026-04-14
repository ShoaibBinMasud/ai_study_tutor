import { useEffect, useRef, useState } from "react";
import { sendMessage } from "../api";
import Message, { type MessageData } from "./Message";

interface ChatProps {
  messages: MessageData[];
  onMessages: (msgs: MessageData[]) => void;
}

export default function Chat({ messages, onMessages }: ChatProps) {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function submit() {
    const text = input.trim();
    if (!text || loading) return;

    const userMsg: MessageData = { role: "user", text };
    const withUser = [...messages, userMsg];
    onMessages(withUser);
    setInput("");
    setLoading(true);

    try {
      const res = await sendMessage(text);
      const assistantMsg: MessageData = {
        role: "assistant",
        text: res.text,
        diagram: res.diagram,
      };
      onMessages([...withUser, assistantMsg]);
    } catch (e: unknown) {
      onMessages([
        ...withUser,
        { role: "assistant", text: `Error: ${e instanceof Error ? e.message : String(e)}` },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <div className="chat-container">
      <div className="chat-messages">
        {messages.map((m, i) => (
          <Message key={i} message={m} />
        ))}
        {loading && (
          <div className="message message-assistant">
            <div className="message-bubble typing-indicator">
              <span /><span /><span />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="chat-input-row">
        <textarea
          className="chat-input"
          placeholder="'teach me section 1-2', 'yes', 'what about chapter 3?'..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          rows={1}
          disabled={loading}
        />
        <button
          className="send-btn"
          onClick={submit}
          disabled={loading || !input.trim()}
        >
          Send
        </button>
      </div>
    </div>
  );
}
