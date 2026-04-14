import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import Diagram from "./Diagram";

export interface MessageData {
  role: "user" | "assistant";
  text: string;
  diagram?: string | null;
}

interface MessageProps {
  message: MessageData;
}

export default function Message({ message }: MessageProps) {
  const isUser = message.role === "user";

  return (
    <div className={`message ${isUser ? "message-user" : "message-assistant"}`}>
      <div className="message-bubble">
        <ReactMarkdown
          remarkPlugins={[remarkMath]}
          rehypePlugins={[rehypeKatex]}
        >
          {message.text}
        </ReactMarkdown>
      </div>
      {message.diagram && (
        <div className="message-diagram">
          <Diagram html={message.diagram} />
        </div>
      )}
    </div>
  );
}
