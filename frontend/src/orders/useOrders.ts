import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { apiRequest } from "../api/http";
import type { CommerceOrder, OrderFilters, OrderListResponse } from "./types";

function orderParams(filters: OrderFilters) {
  const params = new URLSearchParams();
  if (filters.marketplace) params.set("marketplace", filters.marketplace);
  if (filters.status) params.set("status", filters.status);
  if (filters.q?.trim()) params.set("q", filters.q.trim());
  if (filters.since) params.set("since", new Date(`${filters.since}T00:00:00Z`).toISOString());
  if (filters.cursor) params.set("cursor", filters.cursor);
  const query = params.toString();
  return query ? `?${query}` : "";
}

export function useOrders(userId: string, filters: OrderFilters) {
  return useQuery({
    queryKey: ["orders", userId, filters],
    queryFn: () => apiRequest<OrderListResponse>(`/orders${orderParams(filters)}`),
    placeholderData: keepPreviousData,
  });
}

export function useOrder(userId: string, orderId: string | undefined) {
  return useQuery({
    queryKey: ["order", userId, orderId],
    queryFn: () => apiRequest<CommerceOrder>(`/orders/${orderId}`),
    enabled: Boolean(orderId),
  });
}
