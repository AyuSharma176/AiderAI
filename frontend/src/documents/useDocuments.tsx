import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiRequest } from "../api/http";

export type DocumentStatus = "pending" | "processing" | "ready" | "failed";

export interface DocumentRecord {
  id: string;
  filename: string;
  status: DocumentStatus;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export function pollingInterval(documents?: Array<Pick<DocumentRecord, "status">>): 3000 | false {
  return documents?.some(({ status }) => status === "pending" || status === "processing") ? 3000 : false;
}

export function useDocuments() {
  return useQuery({
    queryKey: ["documents"],
    queryFn: () => apiRequest<DocumentRecord[]>("/documents"),
    refetchInterval: (query) => pollingInterval(query.state.data),
  });
}

export function useUploadDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => {
      const body = new FormData();
      body.append("file", file);
      return apiRequest<DocumentRecord>("/documents/upload", { method: "POST", body });
    },
    onSuccess: async () => queryClient.invalidateQueries({ queryKey: ["documents"] }),
  });
}
