import { useState } from "react";
import { useGmailActions, useGmailConnection } from "./useGmailIntegration";

interface Props { userId: string; navigate?: (url: string) => void; }

function safeGoogleAuthorizationUrl(value: string): string | null {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && url.hostname === "accounts.google.com" ? url.toString() : null;
  } catch { return null; }
}

export function ShoppingAccountsPanel({ userId, navigate = (url) => window.location.assign(url) }: Props) {
  const connection = useGmailConnection(userId);
  const actions = useGmailActions(userId);
  const [actionError, setActionError] = useState<string | null>(null);
  const data = connection.data;
  const status = data?.status ?? "disconnected";
  const busy = actions.authorize.isPending || actions.sync.isPending;
  const count = (marketplace: "amazon" | "flipkart") => data?.marketplace_counts?.[marketplace] ?? 0;

  async function connect() {
    setActionError(null);
    try {
      const result = await actions.authorize.mutateAsync();
      const destination = safeGoogleAuthorizationUrl(result.authorization_url);
      if (!destination) throw new Error("invalid authorization destination");
      navigate(destination);
    } catch { setActionError("Unable to start Gmail authorization. Please try again."); }
  }

  async function disconnect() {
    if (window.confirm("Disconnect Gmail? Existing imported orders will remain available.")) await actions.disconnect.mutateAsync();
  }

  async function deleteOrders() {
    if (window.confirm("Delete all imported orders? Your Gmail connection will remain active.")) await actions.deleteOrders.mutateAsync();
  }

  return <section className="connected-accounts" aria-labelledby="connected-accounts-title">
    <div className="section-heading"><div><p className="eyebrow">Order intelligence</p><h2 id="connected-accounts-title">Connected accounts</h2><p className="muted">Import order updates from Gmail without sharing shopping passwords.</p></div><span className={`connection-status ${status}`}>{status.replaceAll("_", " ")}</span></div>
    {connection.isLoading ? <p>Loading connected accounts…</p> : connection.isError ? <p role="alert">Unable to load the Gmail connection. Please retry.</p> : status === "disconnected" ? <div className="connection-card"><div><strong>Gmail</strong><p className="muted">Read-only order-email import</p></div><button className="primary-inline-button" disabled={busy} onClick={() => void connect()}>{actions.authorize.isPending ? "Authorizing…" : "Connect Gmail"}</button></div> : <div className="connection-card connected"><div><strong>{data?.email_address ?? "Gmail"}</strong><div className="marketplace-counts"><span>{`${count("amazon")} Amazon orders`}</span><span>{`${count("flipkart")} Flipkart orders`}</span></div><small>Last synced {data?.last_sync_completed_at ? new Date(data.last_sync_completed_at).toLocaleString() : "not yet"}</small></div><div className="connection-actions">{status === "reconnect_required" ? <button className="primary-inline-button" onClick={() => void connect()}>Reconnect Gmail</button> : <button className="secondary-button" disabled={busy || status === "syncing"} onClick={() => actions.sync.mutate()}>{status === "syncing" ? "Syncing…" : "Sync now"}</button>}<button className="danger-text-button" onClick={() => void disconnect()}>Disconnect</button><button className="danger-text-button" onClick={() => void deleteOrders()}>Delete imported orders</button></div></div>}
    {(actionError || actions.sync.isError || actions.disconnect.isError || actions.deleteOrders.isError) && <p className="form-error" role="alert">{actionError ?? "The account action failed. Please try again."}</p>}
  </section>;
}
