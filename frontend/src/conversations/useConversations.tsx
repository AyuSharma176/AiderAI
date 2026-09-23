import { useQuery } from "@tanstack/react-query";

import { apiRequest } from "../api/http";
import type { User } from "../api/types";
import { getStoredUser } from "../auth/storage";

export interface ConversationSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ConversationMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  citations: Array<{ source: string; page?: number }> | null;
  created_at: string;
}

export interface ConversationDetail extends ConversationSummary {
  messages: ConversationMessage[];
}

export function useConversations() {
  const user = getStoredUser<User>();
  return useQuery({ queryKey: ["conversations", user?.id ?? "anonymous"], queryFn: () => apiRequest<ConversationSummary[]>("/conversations") });
}
