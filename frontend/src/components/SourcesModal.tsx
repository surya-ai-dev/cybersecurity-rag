import { useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { BookOpen, FileText, X } from "lucide-react";
import type { SourceChunkDTO } from "../types/api";

interface SourcesModalProps {
  sources: SourceChunkDTO[] | null;
  highlightedIndex?: number;
  onClose: () => void;
}

function normalizeExcerptForDedup(text: string): string {
  return text.trim().replace(/\s+/g, " ").toLowerCase();
}

function cleanChunkMarkdown(raw: string): string {
  let cleaned = raw.replace(/\r\n/g, "\n").trim();
  // Remove truncated trailing heading/hash artifacts at snippet end
  cleaned = cleaned.replace(/\s+#+$/, "").trimEnd();
  // Close an unclosed bold span caused by substring truncation
  const boldMarkers = cleaned.match(/\*\*/g);
  if (boldMarkers && boldMarkers.length % 2 === 1) {
    cleaned = `${cleaned}**`;
  }
  const fenceMarkers = cleaned.match(/```/g);
  if (fenceMarkers && fenceMarkers.length % 2 === 1) {
    cleaned = `${cleaned}\n\`\`\``;
  }
  return cleaned;
}

export function SourcesModal({ sources, highlightedIndex, onClose }: SourcesModalProps) {
  const dedupedSources = useMemo(() => {
    if (!sources || sources.length === 0) return [];
    const seenIds = new Set<string>();
    const seenContent = new Set<string>();
    const unique: SourceChunkDTO[] = [];

    for (const src of sources) {
      const idKey = src.chunk_id.trim();
      const contentKey = normalizeExcerptForDedup(src.text_preview ?? "");

      if (idKey && seenIds.has(idKey)) continue;
      if (contentKey && seenContent.has(contentKey)) continue;

      if (idKey) seenIds.add(idKey);
      if (contentKey) seenContent.add(contentKey);
      unique.push(src);
    }

    return unique;
  }, [sources]);

  if (!sources || dedupedSources.length === 0) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="flex max-h-[85vh] w-full max-w-3xl flex-col rounded-2xl border border-white/10 bg-[#212121] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-white/10 px-5 py-3.5">
          <div className="flex items-center gap-2">
            <BookOpen className="h-4 w-4 text-[#ECECEC]" />
            <h3 className="text-sm font-semibold text-[#ECECEC]">
              Retrieved Evidence Chunks ({dedupedSources.length})
            </h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close sources modal"
            className="rounded-lg p-1 text-[#9B9B9B] transition hover:bg-[#2F2F2F] hover:text-[#ECECEC]"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 space-y-3.5 overflow-y-auto p-5">
          {dedupedSources.map((src) => {
            const isHighlighted = highlightedIndex === src.source_index;
            const hasDistinctTitle =
              Boolean(src.title?.trim()) &&
              src.title.trim().toLowerCase() !== src.doc_id.trim().toLowerCase();
            const hasSection =
              Boolean(src.section?.trim()) &&
              src.section.trim().toLowerCase() !== "unknown";

            return (
              <article
                key={src.chunk_id}
                className={`rounded-2xl border p-4 transition ${
                  isHighlighted
                    ? "border-white/30 bg-[#2F2F2F] ring-1 ring-white/20"
                    : "border-white/10 bg-[#171717]"
                }`}
              >
                {/* Top Row: Source N badge + rounded score */}
                <div className="flex items-center justify-between gap-3">
                  <span
                    className={`inline-flex items-center rounded-md px-2.5 py-0.5 text-xs font-semibold ${
                      isHighlighted
                        ? "bg-[#ECECEC] text-[#171717]"
                        : "bg-[#2F2F2F] text-[#ECECEC]"
                    }`}
                  >
                    Source {src.source_index}
                  </span>

                  <span className="inline-flex items-center rounded-full border border-emerald-500/25 bg-emerald-500/10 px-2.5 py-0.5 font-mono text-xs font-medium tabular-nums text-emerald-400">
                    Score {src.score.toFixed(2)}
                  </span>
                </div>

                {/* Clean Document & Page Metadata Badges */}
                <div className="mt-2.5 flex flex-wrap items-center gap-1.5 text-[11px]">
                  <span className="inline-flex items-center gap-1 rounded-md border border-white/10 bg-[#212121] px-2 py-0.5 font-medium text-[#ECECEC]">
                    <FileText className="h-3 w-3 text-[#9B9B9B]" />
                    <span>{src.doc_id}</span>
                  </span>

                  {hasDistinctTitle && (
                    <span className="rounded-md border border-white/10 bg-[#212121] px-2 py-0.5 text-[#9B9B9B]">
                      {src.title}
                    </span>
                  )}

                  {src.page !== null && src.page !== undefined && (
                    <span className="rounded-md border border-white/10 bg-[#212121] px-2 py-0.5 text-[#9B9B9B]">
                      Page {src.page}
                    </span>
                  )}

                  {hasSection && (
                    <span className="rounded-md border border-white/10 bg-[#212121] px-2 py-0.5 text-[#9B9B9B]">
                      Section: {src.section}
                    </span>
                  )}
                </div>

                {/* Rendered Markdown Excerpt Body */}
                <div className="mt-3 rounded-xl border border-white/10 bg-[#212121] px-3.5 py-3">
                  <div className="prose prose-invert max-w-none !text-[13px] !leading-relaxed text-[#ECECEC]">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {cleanChunkMarkdown(src.text_preview ?? "")}
                    </ReactMarkdown>
                  </div>
                </div>

                {/* Subtle Chunk ID Footer */}
                <div className="mt-2.5 flex items-center justify-between text-[11px] text-[#9B9B9B]">
                  <span className="truncate font-mono">Chunk ID: {src.chunk_id}</span>
                </div>
              </article>
            );
          })}
        </div>
      </div>
    </div>
  );
}
