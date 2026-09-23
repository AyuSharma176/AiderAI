import { useRef, useState, type DragEvent } from "react";

const MAX_UPLOAD_BYTES = Number(import.meta.env.VITE_MAX_UPLOAD_BYTES ?? 10 * 1024 * 1024);

export function UploadDropzone({ onUpload, uploading }: { onUpload: (file: File) => void; uploading: boolean }) {
  const input = useRef<HTMLInputElement>(null);
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState(false);

  function accept(file?: File) {
    setError("");
    if (!file || file.type !== "application/pdf" || !file.name.toLowerCase().endsWith(".pdf")) {
      setError("Choose a PDF file.");
      return;
    }
    if (file.size > MAX_UPLOAD_BYTES) {
      setError(`PDFs must be smaller than ${Math.floor(MAX_UPLOAD_BYTES / 1024 / 1024)} MB.`);
      return;
    }
    onUpload(file);
  }

  function drop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    accept(event.dataTransfer.files[0]);
  }

  return (
    <div>
      <div className={dragging ? "upload-dropzone dragging" : "upload-dropzone"} onDragEnter={(event) => { event.preventDefault(); setDragging(true); }} onDragOver={(event) => event.preventDefault()} onDragLeave={() => setDragging(false)} onDrop={drop}>
        <input ref={input} id="pdf-upload" className="sr-only" type="file" accept="application/pdf,.pdf" aria-label="Upload PDF" disabled={uploading} onChange={(event) => { accept(event.target.files?.[0]); event.target.value = ""; }} />
        <div className="upload-icon" aria-hidden="true">⇧</div>
        <h2>{uploading ? "Uploading document…" : "Add knowledge"}</h2>
        <p>Drop a PDF here, or choose one from your computer.</p>
        <button type="button" className="secondary-button" disabled={uploading} onClick={() => input.current?.click()}>{uploading ? "Uploading…" : "Choose PDF"}</button>
        <small>PDF only · up to {Math.floor(MAX_UPLOAD_BYTES / 1024 / 1024)} MB</small>
      </div>
      {error && <p className="upload-error" role="alert">{error}</p>}
    </div>
  );
}
