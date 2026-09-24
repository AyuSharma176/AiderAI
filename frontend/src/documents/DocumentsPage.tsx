import { DocumentTable } from "./DocumentTable";
import { UploadDropzone } from "./UploadDropzone";
import { useDocuments, useUploadDocument } from "./useDocuments";
import type { User } from "../api/types";
import { getStoredUser } from "../auth/storage";
import { ShoppingAccountsPanel } from "../integrations/ShoppingAccountsPanel";

export function DocumentsPage() {
  const documents = useDocuments();
  const upload = useUploadDocument();
  const userId = getStoredUser<User>()?.id ?? "anonymous";
  return (
    <section className="page documents-page">
      <div className="page-heading"><div><p className="eyebrow">Grounded answers</p><h1>Knowledge base</h1><p className="muted">Upload trusted company PDFs. AiderAI will index them in the background.</p></div><div className="metric-card"><strong>{documents.data?.filter((document) => document.status === "ready").length ?? 0}</strong><span>Ready documents</span></div></div>
      <UploadDropzone uploading={upload.isPending} onUpload={(file) => upload.mutate(file)} />
      {upload.isError && <p className="upload-error" role="alert">{upload.error instanceof Error ? upload.error.message : "Upload failed."}</p>}
      <ShoppingAccountsPanel userId={userId} />
      <div className="documents-section"><div><h2>Documents</h2><p className="muted">Processing documents refresh automatically.</p></div>{documents.isLoading ? <p>Loading documents…</p> : documents.isError ? <p role="alert">Unable to load documents.</p> : <DocumentTable documents={documents.data ?? []} />}</div>
    </section>
  );
}
