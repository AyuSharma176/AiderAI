export type Marketplace = "amazon" | "flipkart";
export type OrderStatus = "placed" | "shipped" | "out_for_delivery" | "delivered" | "cancelled" | "return_update" | "unknown";
export interface OrderItem { id: string; title: string; quantity: number; unit_price: string | null; marketplace_product_id: string | null; }
export interface OrderEvent { id: string; event_type: OrderStatus; event_at: string; parser_name: string; parser_version: string; facts: Record<string, unknown>; }
export interface CommerceOrder {
  id: string; marketplace: Marketplace; marketplace_order_id: string; status: OrderStatus;
  placed_at: string | null; currency: string | null; total_amount: string | null;
  expected_delivery_at: string | null; delivered_at: string | null; tracking_number: string | null;
  carrier: string | null; marketplace_url: string | null; last_source_message_at: string | null;
  items?: OrderItem[]; events?: OrderEvent[];
}
export interface OrderListResponse { items: CommerceOrder[]; next_cursor: string | null; last_sync_completed_at: string | null; }
export interface OrderFilters { marketplace?: Marketplace | ""; status?: OrderStatus | ""; q?: string; cursor?: string; }
