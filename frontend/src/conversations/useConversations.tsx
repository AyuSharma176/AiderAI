import { useQuery } from "@tanstack/react-query";

import { apiRequest } from "../api/http";

export interface ConversationSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export function useConversations() {
  return useQuery({ queryKey: ["conversations"], queryFn: () => apiRequest<ConversationSummary[]>("/conversations") });
}
