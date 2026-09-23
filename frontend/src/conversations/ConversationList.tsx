import { Link } from "react-router-dom";

import { useConversations } from "./useConversations";

export function ConversationList() {
  const conversations = useConversations();
  return (
    <section className="page">
      <p className="eyebrow">History</p><h1>Conversations</h1><p className="muted">Resume a previous support thread.</p>
      {conversations.isLoading && <p>Loading conversations…</p>}
      {conversations.isError && <p role="alert">Unable to load conversations.</p>}
      <div className="conversation-grid">
        {conversations.data?.map((conversation) => <Link key={conversation.id} to={`/chat?conversation=${conversation.id}`}><strong>{conversation.title}</strong><time>{new Date(conversation.updated_at).toLocaleString()}</time><span>Open conversation →</span></Link>)}
      </div>
    </section>
  );
}
