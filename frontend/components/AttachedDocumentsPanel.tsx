import type { AttachedDocumentRead, DocumentKind } from "@/lib/types";
import { cn } from "@/lib/utils";

const DOC_LABEL: Record<DocumentKind, string> = {
  PRESS_RELEASE: "Press release (EX-99.1)",
  FILING_COVER: "Filing cover (8-K)",
  EXHIBIT: "Additional exhibit",
  TRANSCRIPT: "Earnings call transcript",
};

const DOC_BADGE: Record<DocumentKind, string> = {
  PRESS_RELEASE: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  FILING_COVER: "bg-purple-50 text-purple-700 ring-purple-600/20",
  EXHIBIT: "bg-slate-100 text-slate-700 ring-slate-500/20",
  TRANSCRIPT: "bg-amber-50 text-amber-800 ring-amber-600/20",
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
      <section className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-900 uppercase tracking-wide">
          Attached documents
        </h2>
        <p className="mt-2 text-sm text-slate-500">
          No documents downloaded for this event yet. The Phase B document
          fetcher polls every minute for fresh 8-Ks; bodies typically land
          within ~2 minutes of the event arriving.
        </p>
      </section>
    );
  }

  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm">
      <div className="flex items-baseline justify-between mb-4">
        <h2 className="text-sm font-semibold text-slate-900 uppercase tracking-wide">
          Attached documents
          <span className="ml-2 text-slate-400 normal-case font-normal">
            ({documents.length})
          </span>
        </h2>
        <span className="text-xs text-slate-500">
          full text the LLM saw at prediction time
        </span>
      </div>

      <ul className="space-y-2.5">
        {documents.map((d, i) => (
          <li key={`${d.doc_kind}-${i}`}>
            <details className="rounded-xl border border-slate-200 bg-slate-50 group">
              <summary className="cursor-pointer p-3 text-sm flex items-center gap-3 select-none">
                <span
                  className={cn(
                    "inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold tracking-wide ring-1 ring-inset",
                    DOC_BADGE[d.doc_kind],
                  )}
                >
                  {d.doc_kind}
                </span>
                <span className="font-medium text-slate-800">
                  {DOC_LABEL[d.doc_kind]}
                </span>
                <span className="text-xs text-slate-500 ml-auto font-mono tabular-nums">
                  {formatBytes(d.byte_size)}
                </span>
              </summary>

              <div className="px-3 pb-3 space-y-2">
                <div className="text-xs text-slate-500 italic px-1">
                  {firstNonEmptyLine(d.content_text).slice(0, 200)}
                  {firstNonEmptyLine(d.content_text).length > 200 ? "…" : ""}
                </div>
                <pre className="overflow-auto max-h-96 rounded-lg bg-slate-900 p-4 text-xs text-slate-100 leading-relaxed whitespace-pre-wrap">
                  {d.content_text}
                </pre>
                <div className="text-[11px] text-slate-500 font-mono break-all px-1">
                  source:{" "}
                  <a
                    href={d.raw_url}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="text-indigo-600 hover:underline"
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
