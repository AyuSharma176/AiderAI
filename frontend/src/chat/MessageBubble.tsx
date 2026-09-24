import { CitationList, type Citation } from "./CitationList";

export interface ChatMessageView {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  timestamp: Date;
}

export function MessageBubble({ message }: { message: ChatMessageView }) {
  return (
    <article className={`message-row ${message.role}`}>
      <div className="message-avatar" aria-hidden="true">{message.role === "assistant" ? "◇" : "You"}</div>
      <div>
        <div className="message-meta"><strong>{message.role === "assistant" ? "AiderAI" : "You"}</strong><time>{message.timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</time></div>
        <div className="message-bubble">{message.content || <span className="typing-dots">•••</span>}</div>
        <CitationList citations={message.citations} />
      </div>
    </article>
  );
}
