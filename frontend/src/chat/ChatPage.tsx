import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

import { API_URL } from "../api/http";
import { consumeSSE, type SSEEvent } from "../api/sse";
import { getAccessToken } from "../auth/storage";
import { AgentStage } from "./AgentStage";
import { ChatComposer } from "./ChatComposer";
import type { Citation } from "./CitationList";
import { MessageList } from "./MessageList";
import type { ChatMessageView } from "./MessageBubble";

export function ChatPage() {
  const queryClient = useQueryClient();
  const [messages, setMessages] = useState<ChatMessageView[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [stage, setStage] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [failedMessage, setFailedMessage] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  const send = useCallback(async (content: string) => {
    if (streaming) return;
    setError("");
    setFailedMessage("");
    setStreaming(true);
    setStage("analyzing");
    const userMessage: ChatMessageView = { id: crypto.randomUUID(), role: "user", content, citations: [], timestamp: new Date() };
    const assistantId = crypto.randomUUID();
    setMessages((current) => [...current, userMessage, { id: assistantId, role: "assistant", content: "", citations: [], timestamp: new Date() }]);
    const controller = new AbortController();
    abortRef.current = controller;
    let streamError = "";
    try {
      const response = await fetch(`${API_URL}/chat/message`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(getAccessToken() ? { Authorization: `Bearer ${getAccessToken()}` } : {}) },
        body: JSON.stringify({ content, conversation_id: conversationId }),
        signal: controller.signal,
      });
      if (!response.ok || !response.body) throw new Error("Unable to start chat");
      await consumeSSE(response.body, (event: SSEEvent) => {
        if (event.event === "stage") setStage(String(event.data.name));
        if (event.event === "token") setMessages((current) => current.map((message) => message.id === assistantId ? { ...message, content: message.content + String(event.data.text ?? "") } : message));
        if (event.event === "citation") setMessages((current) => current.map((message) => message.id === assistantId ? { ...message, citations: [...message.citations, event.data as unknown as Citation] } : message));
        if (event.event === "complete") setConversationId(String(event.data.conversation_id));
        if (event.event === "error") streamError = String(event.data.message ?? "Unable to complete the message");
      });
      if (streamError) throw new Error(streamError);
      await queryClient.invalidateQueries({ queryKey: ["conversations"] });
    } catch (caught) {
      if (!controller.signal.aborted) {
        setError(caught instanceof Error ? caught.message : "Unable to complete the message");
        setFailedMessage(content);
        setMessages((current) => current.filter((message) => message.id !== assistantId));
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }, [conversationId, queryClient, streaming]);

  return (
    <section className="chat-page">
      <header className="chat-header"><div><p className="eyebrow">AI support workspace</p><h1>Support chat</h1></div><span className="status-pill"><i /> Online</span></header>
      <div className="chat-body">
        {stage && <AgentStage name={stage} active={streaming} />}
        <MessageList messages={messages} />
        {error && <div className="stream-error" role="alert"><span>{error}</span><button type="button" onClick={() => send(failedMessage)}>Retry</button></div>}
      </div>
      <footer className="composer-wrap"><ChatComposer onSend={send} disabled={streaming} /><small>SupportAI can make mistakes. Verify important account details.</small></footer>
    </section>
  );
}
