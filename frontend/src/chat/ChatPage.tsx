import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { apiRequest, authenticatedFetch } from "../api/http";
import { consumeSSE, type SSEEvent } from "../api/sse";
import type { ConversationDetail } from "../conversations/useConversations";
import { AgentStage } from "./AgentStage";
import { ChatComposer } from "./ChatComposer";
import type { Citation } from "./CitationList";
import { MessageList } from "./MessageList";
import type { ChatMessageView } from "./MessageBubble";

interface FailedAttempt { content: string; id: string }

export function ChatPage() {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedId = searchParams.get("conversation");
  const [messages, setMessages] = useState<ChatMessageView[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [stage, setStage] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [failedAttempt, setFailedAttempt] = useState<FailedAttempt | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(selectedId);
  const abortRef = useRef<AbortController | null>(null);
  const loadedConversationRef = useRef<string | null>(null);

  const detail = useQuery({
    queryKey: ["conversation", selectedId],
    queryFn: () => apiRequest<ConversationDetail>(`/conversations/${selectedId}`),
    enabled: Boolean(selectedId) && !streaming,
  });

  useEffect(() => {
    if (!detail.data || streaming || loadedConversationRef.current === detail.data.id) return;
    loadedConversationRef.current = detail.data.id;
    setConversationId(detail.data.id);
    setMessages(detail.data.messages.filter((message) => message.role !== "system").map((message) => ({
      id: message.id,
      role: message.role as "user" | "assistant",
      content: message.content,
      citations: (message.citations ?? []) as Citation[],
      timestamp: new Date(message.created_at),
    })));
  }, [detail.data, streaming]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const send = useCallback(async (
    content: string,
    attemptId: string = crypto.randomUUID(),
    appendUser = true,
  ) => {
    if (streaming) return;
    setError("");
    setFailedAttempt(null);
    setStreaming(true);
    setStage("analyzing");
    const assistantId = crypto.randomUUID();
    const additions: ChatMessageView[] = [];
    if (appendUser) additions.push({ id: attemptId, role: "user", content, citations: [], timestamp: new Date() });
    additions.push({ id: assistantId, role: "assistant", content: "", citations: [], timestamp: new Date() });
    setMessages((current) => [...current, ...additions]);
    const controller = new AbortController();
    abortRef.current = controller;
    let streamError = "";
    let terminal = false;
    try {
      const response = await authenticatedFetch("/chat/message", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content, conversation_id: conversationId, client_message_id: attemptId }),
        signal: controller.signal,
      });
      if (!response.ok || !response.body) throw new Error(response.status === 401 ? "Session expired" : "Unable to start chat");
      await consumeSSE(response.body, (event: SSEEvent) => {
        if (event.event === "conversation" || event.event === "complete") {
          const id = String(event.data.conversation_id);
          setConversationId(id);
          setSearchParams({ conversation: id }, { replace: true });
        }
        if (event.event === "stage") setStage(String(event.data.name));
        if (event.event === "token") setMessages((current) => current.map((message) => message.id === assistantId ? { ...message, content: message.content + String(event.data.text ?? "") } : message));
        if (event.event === "citation") setMessages((current) => current.map((message) => message.id === assistantId ? { ...message, citations: [...message.citations, event.data as unknown as Citation] } : message));
        if (event.event === "complete") terminal = true;
        if (event.event === "error") { streamError = String(event.data.message ?? "Unable to complete the message"); terminal = true; }
      });
      if (streamError) throw new Error(streamError);
      if (!terminal) throw new Error("The response stream ended before completion");
      await queryClient.invalidateQueries({ queryKey: ["conversations"] });
    } catch (caught) {
      if (!controller.signal.aborted) {
        setError(caught instanceof Error ? caught.message : "Unable to complete the message");
        setFailedAttempt({ content, id: attemptId });
        setMessages((current) => current.filter((message) => message.id !== assistantId));
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }, [conversationId, queryClient, setSearchParams, streaming]);

  return (
    <section className="chat-page">
      <header className="chat-header"><div><p className="eyebrow">AI support workspace</p><h1>Support chat</h1></div><span className="status-pill"><i /> Online</span></header>
      <div className="chat-body">
        {stage && <AgentStage name={stage} active={streaming} />}
        {detail.isLoading && !messages.length ? <p>Loading conversation…</p> : <MessageList messages={messages} />}
        {error && failedAttempt && <div className="stream-error" role="alert"><span>{error}</span><button type="button" onClick={() => send(failedAttempt.content, failedAttempt.id, false)}>Retry</button></div>}
      </div>
      <footer className="composer-wrap"><ChatComposer onSend={send} disabled={streaming} /><small>SupportAI can make mistakes. Verify important account details.</small></footer>
    </section>
  );
}
