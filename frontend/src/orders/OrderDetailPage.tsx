import { Link, useParams } from "react-router-dom";
import type { User } from "../api/types";
import { getStoredUser } from "../auth/storage";
import type { CommerceOrder } from "./types";
import { useOrder } from "./useOrders";

function safeMarketplaceUrl(order: CommerceOrder): string | null {
  if (!order.marketplace_url) return null;
  try {
    const url = new URL(order.marketplace_url);
    const suffixes = order.marketplace === "amazon" ? ["amazon.in", "amazon.com"] : ["flipkart.com"];
    return url.protocol === "https:" && suffixes.some((suffix) => url.hostname === suffix || url.hostname.endsWith(`.${suffix}`)) ? url.toString() : null;
  } catch { return null; }
}

export function OrderDetailPage({ userId = getStoredUser<User>()?.id ?? "anonymous" }: { userId?: string }) {
  const { orderId } = useParams();
  const orderQuery = useOrder(userId, orderId);
  if (orderQuery.isLoading) return <section className="page"><p>Loading order…</p></section>;
  if (orderQuery.isError || !orderQuery.data) return <section className="page"><p role="alert">Order not found.</p></section>;
  const order = orderQuery.data;
  const marketplaceUrl = safeMarketplaceUrl(order);
  return <section className="page order-detail"><Link to="/orders">← All orders</Link><div className="page-heading"><div><p className="eyebrow">{order.marketplace}</p><h1>{order.marketplace_order_id}</h1><p className="muted">Status: {order.status.replaceAll("_", " ")}</p>{order.last_sync_completed_at && <small className="sync-freshness">Last synced {new Date(order.last_sync_completed_at).toLocaleString()}</small>}</div>{marketplaceUrl && <a className="secondary-button" href={marketplaceUrl} target="_blank" rel="noopener noreferrer">Open in {order.marketplace}</a>}</div><div className="order-detail-grid"><section><h2>Items</h2>{order.items?.length ? <ul className="order-items">{order.items.map((item) => <li key={item.id}><span>{item.title}</span><strong>× {item.quantity}</strong></li>)}</ul> : <p className="muted">Item details unavailable.</p>}</section><section><h2>Delivery</h2><dl><dt>Tracking</dt><dd>{order.tracking_number ?? "Unavailable"}</dd><dt>Carrier</dt><dd>{order.carrier ?? "Unavailable"}</dd><dt>Expected</dt><dd>{order.expected_delivery_at ? new Date(order.expected_delivery_at).toLocaleDateString() : "Unavailable"}</dd></dl></section></div><section className="order-timeline"><h2>Timeline</h2>{order.events?.length ? <ol>{order.events.map((event) => <li key={event.id}><strong>{event.event_type.replaceAll("_", " ")}</strong><time>{new Date(event.event_at).toLocaleString()}</time></li>)}</ol> : <p className="muted">No timeline events yet.</p>}</section></section>;
}
