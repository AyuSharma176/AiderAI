import type { DocumentRecord } from "./useDocuments";

const labels = { pending: "Queued", processing: "Processing", ready: "Ready", failed: "Failed" };

export function DocumentTable({ documents }: { documents: DocumentRecord[] }) {
  if (!documents.length) return <div className="documents-empty"><strong>No documents yet</strong><p>Upload a PDF to start grounding SupportAI answers.</p></div>;
  return (
    <div className="document-table-wrap">
      <table className="document-table">
        <thead><tr><th>Document</th><th>Uploaded</th><th>Status</th><th>Details</th></tr></thead>
        <tbody>{documents.map((document) => <tr key={document.id}>
          <td><span className="pdf-icon">PDF</span><strong>{document.filename}</strong></td>
          <td>{new Date(document.created_at).toLocaleString()}</td>
          <td><span className={`document-status ${document.status}`}>{labels[document.status]}</span></td>
          <td>{document.status === "failed" ? <span className="failure-text">{document.error_message ?? "Processing failed. Try again."}</span> : document.status === "processing" ? "Extracting and indexing…" : document.status === "ready" ? "Available to chat" : "Waiting for a worker"}</td>
        </tr>)}</tbody>
      </table>
    </div>
  );
}
