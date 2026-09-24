import { useState, type FormEvent } from "react";

export function ChatComposer({ onSend, disabled }: { onSend: (message: string) => void; disabled: boolean }) {
  const [message, setMessage] = useState("");
  function submit(event: FormEvent) {
    event.preventDefault();
    const value = message.trim();
    if (!value || disabled) return;
    setMessage("");
    onSend(value);
  }
  return (
    <form className="chat-composer" onSubmit={submit}>
      <label className="sr-only" htmlFor="chat-message">Message AiderAI</label>
      <textarea id="chat-message" value={message} onChange={(event) => setMessage(event.target.value)} placeholder="Ask AiderAI anything…" rows={2} disabled={disabled} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} />
      <button type="submit" aria-label="Send message" disabled={disabled || !message.trim()}>↑</button>
    </form>
  );
}
