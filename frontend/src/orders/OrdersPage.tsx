import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type { User } from "../api/types";
import { getStoredUser } from "../auth/storage";
import type { Marketplace, OrderStatus } from "./types";
import { useOrders } from "./useOrders";

export function OrdersPage({ userId = getStoredUser<User>()?.id ?? "anonymous" }: { userId?: string }) {
  const [marketplace, setMarketplace] = useState<Marketplace | "">("");
  const [status, setStatus] = useState<OrderStatus | "">("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [since, setSince] = useState("");
  const [cursor, setCursor] = useState("");
  useEffect(() => { const timer = window.setTimeout(() => setQuery(search), 250); return () => window.clearTimeout(timer); }, [search]);
  const orders = useOrders(userId, { marketplace, status, q: query, since, cursor });
  const resetCursor = () => setCursor("");
  const money = (amount: string | null, currency: string | null) => amount && currency
    ? new Intl.NumberFormat("en-IN", { style: "currency", currency }).format(Number(amount))
    : null;

  return <section className="page orders-page">
    <div className="page-heading"><div><p className="eyebrow">One place for every purchase</p><h1>My Orders</h1><p className="muted">Amazon and Flipkart updates imported from your connected Gmail.</p></div><div className="metric-card"><strong>{orders.data?.items.length ?? 0}</strong><span>Visible orders</span></div></div>
    <div className="order-filters"><label>Marketplace<select value={marketplace} onChange={(event) => { setMarketplace(event.target.value as Marketplace | ""); resetCursor(); }}><option value="">All</option><option value="amazon">Amazon</option><option value="flipkart">Flipkart</option></select></label><label>Status<select value={status} onChange={(event) => { setStatus(event.target.value as OrderStatus | ""); resetCursor(); }}><option value="">All</option><option value="placed">Placed</option><option value="shipped">Shipped</option><option value="out_for_delivery">Out for delivery</option><option value="delivered">Delivered</option><option value="cancelled">Cancelled</option></select></label><label>Orders since<input aria-label="Orders since" type="date" value={since} onChange={(event) => { setSince(event.target.value); resetCursor(); }} /></label><label>Search<input value={search} onChange={(event) => { setSearch(event.target.value); resetCursor(); }} placeholder="Product or order ID" /></label></div>
    {orders.data?.last_sync_completed_at && <p className="sync-freshness">Last synced {new Date(orders.data.last_sync_completed_at).toLocaleString()}</p>}
    {orders.isLoading ? <p>Loading orders…</p> : orders.isError ? <p role="alert">Unable to load orders.</p> : orders.data?.items.length ? <><div className="orders-grid">{orders.data.items.map((order) => <Link className="order-card" to={`/orders/${order.id}`} key={order.id}><div><span className={`marketplace-badge ${order.marketplace}`}>{order.marketplace}</span><span className="order-status-text">{order.status.replaceAll("_", " ")}</span></div><h2>{order.items?.[0]?.title ?? order.marketplace_order_id}</h2><p>{order.marketplace_order_id}</p>{money(order.total_amount, order.currency) && <strong>{money(order.total_amount, order.currency)}</strong>}<small>{order.placed_at ? new Date(order.placed_at).toLocaleDateString() : "Date unavailable"}</small>{order.expected_delivery_at && <small>Expected {new Date(order.expected_delivery_at).toLocaleDateString()}</small>}</Link>)}</div>{orders.data.next_cursor && <button className="secondary-button orders-next" onClick={() => setCursor(orders.data!.next_cursor!)}>Next page</button>}</> : <div className="orders-empty"><h2>No matching orders</h2><p>Connect Gmail or adjust your filters.</p></div>}
  </section>;
}
