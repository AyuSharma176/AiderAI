export interface Citation {
  source: string;
  page?: number;
  chunk_id?: string;
}

export function CitationList({ citations }: { citations: Citation[] }) {
  if (!citations.length) return null;
  return (
    <ul className="citation-list" aria-label="Sources">
      {citations.map((citation, index) => (
        <li key={`${citation.source}-${citation.page ?? index}`}>
          <span aria-hidden="true">▤</span>
          {citation.source}{citation.page ? ` · page ${citation.page}` : ""}
        </li>
      ))}
    </ul>
  );
}
