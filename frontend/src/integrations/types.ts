export type GmailConnectionStatus = "connected" | "syncing" | "reconnect_required" | "disconnected";

export interface GmailConnection {
  status: GmailConnectionStatus;
  email_address?: string | null;
  last_sync_completed_at?: string | null;
  imported_order_count?: number;
  marketplace_counts: Partial<Record<"amazon" | "flipkart", number>>;
  reconnect_required?: boolean;
}

export interface GmailAuthorization { authorization_url: string; }
