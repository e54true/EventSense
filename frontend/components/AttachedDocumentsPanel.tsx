import type { AttachedDocumentRead, DocumentKind } from "@/lib/types";
import { cn } from "@/lib/utils";

const DOC_LABEL: Record<DocumentKind, string> = {
  PRESS_RELEASE: "Press release (EX-99.1)",
  FILING_COVER: "Filing cover (8-K)",
  EXHIBIT: "Additional exhibit",
  TRANSCRIPT: "Earnings call transcript",
};

const DOC_BADGE: Record<DocumentKind, string> = {
  PRESS_RELEASE: "text-src-earn border-src-earn/40 bg-src-earn/10",
  FILING_COVER: "text-src-sec border-src-sec/40 bg-src-sec/10",
  EXHIBIT: "text-term-muted border-term-muted/40 bg-term-muted/10",
  TRANSCRIPT: "text-term-amber border-term-amber/40 bg-term-amber/10",
};

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

function firstNonEmptyLine(text: string): string {
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (trimmed.length > 0) return trimmed;
  }
  return "";
}

export function AttachedDocumentsPanel({
  documents,
}: {
  documents: AttachedDocumentRead[];
}) {
  if (documents.length === 0) {
    return (
      <section className="border border-term-border bg-term-panel p-5">
        <h2 className="font-mono text-xs font-bold tracking-[0.2em] text-term-muted uppercase">
          <span className="text-term-amber">▮</span> Attached documents
        </h2>
        <p className="mt-2 text-sm text-term-muted">
          No documents downloaded for this event yet. The Phase B document
          fetcher polls every minute for fresh 8-Ks; bodies typically land
          within ~2 minutes of the event arriving.
        </p>
      </section>
    );
  }

  return (
    <section className="border border-term-border bg-term-panel p-5">
      <div className="flex items-baseline justify-between mb-4">
        <h2 className="font-mono text-xs font-bold tracking-[0.2em] text-term-muted uppercase">
          <span className="text-term-amber">▮</span> Attached documents
          <span className="ml-2 text-term-dim font-normal normal-case">
            ({documents.length})
          </span>
        </h2>
        <span className="font-mono text-[10px] tracking-wider text-term-dim">
          full text the LLM saw at prediction time
        </span>
      </div>

      <ul className="space-y-2">
        {documents.map((d, i) => (
          <li key={`${d.doc_kind}-${i}`}>
            <details className="border border-term-border bg-term-panel2/60 group">
              <summary className="cursor-pointer p-3 text-sm flex items-center gap-3 select-none">
                <span
                  className={cn(
                    "inline-flex items-center border px-1.5 py-px font-mono text-[10px] font-bold tracking-widest",
                    DOC_BADGE[d.doc_kind],
                  )}
                >
                  {d.doc_kind}
                </span>
                <span className="font-medium text-term-text">
                  {DOC_LABEL[d.doc_kind]}
                </span>
                <span className="font-mono text-[11px] text-term-dim ml-auto tabular-nums">
                  {formatBytes(d.byte_size)}
                </span>
              </summary>

              <div className="px-3 pb-3 space-y-2">
                <div className="text-xs text-term-muted italic px-1">
                  {firstNonEmptyLine(d.content_text).slice(0, 200)}
                  {firstNonEmptyLine(d.content_text).length > 200 ? "…" : ""}
                </div>
                <pre className="overflow-auto max-h-96 border border-term-border bg-[#070b10] p-4 text-xs text-term-text/90 leading-relaxed whitespace-pre-wrap">
                  {d.content_text}
                </pre>
                <div className="font-mono text-[11px] text-term-dim break-all px-1">
                  source:{" "}
                  <a
                    href={d.raw_url}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="text-term-amber hover:underline"
                  >
                    {d.raw_url}
                  </a>
                </div>
              </div>
            </details>
          </li>
        ))}
      </ul>
    </section>
  );
}
