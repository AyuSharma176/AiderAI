import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "../api/http";
import type { GmailAuthorization, GmailConnection } from "./types";

export function gmailConnectionKey(userId: string) { return ["gmail-connection", userId] as const; }

export function useGmailConnection(userId: string) {
  return useQuery({ queryKey: gmailConnectionKey(userId), queryFn: () => apiRequest<GmailConnection>("/integrations/gmail") });
}

export function useGmailActions(userId: string) {
  const queryClient = useQueryClient();
  const invalidate = () => queryClient.invalidateQueries({ queryKey: gmailConnectionKey(userId) });
  const authorize = useMutation({ mutationFn: () => apiRequest<GmailAuthorization>("/integrations/gmail/authorize", { method: "POST" }) });
  const sync = useMutation({ mutationFn: () => apiRequest<{ status: string }>("/integrations/gmail/sync", { method: "POST" }), onSuccess: invalidate });
  const disconnect = useMutation({ mutationFn: () => apiRequest<void>("/integrations/gmail", { method: "DELETE" }), onSuccess: invalidate });
  const deleteOrders = useMutation({ mutationFn: () => apiRequest<void>("/integrations/gmail/orders", { method: "DELETE" }), onSuccess: invalidate });
  return { authorize, sync, disconnect, deleteOrders };
}
