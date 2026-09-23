import { MessageBubble, type ChatMessageView } from "./MessageBubble";

export function MessageList({ messages }: { messages: ChatMessageView[] }) {
  if (!messages.length) {
    return <div className="empty-chat"><div className="empty-icon">◇</div><h2>How can I help today?</h2><p>Ask about policies, orders, account details, or create a support ticket.</p></div>;
  }
  return <div className="message-list" aria-live="polite">{messages.map((message) => <MessageBubble key={message.id} message={message} />)}</div>;
}
