import {
  Brain,
  CheckCircle2,
  Cpu,
  Database,
  FileText,
  Tag,
  X,
  XCircle,
} from "lucide-react";
import type { HealthResponse, MemoryFactDTO } from "../types/api";

interface MemoryDrawerProps {
  isOpen: boolean;
  health: HealthResponse | null;
  activeSessionId: string | null;
  summary: string;
  activeFacts: MemoryFactDTO[];
  turnCount: number;
  onClose: () => void;
}

const CATEGORY_STYLE: Record<string, string> = {
  standard: "border-white/15 bg-[#2F2F2F] text-[#ECECEC]",
  control: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
  environment: "border-sky-500/30 bg-sky-500/10 text-sky-300",
  identifier: "border-amber-500/30 bg-amber-500/10 text-amber-300",
};

function StatusBadge({ label, enabled }: { label: string; enabled: boolean }) {
  return (
    <div className="flex items-center justify-between rounded-xl border border-white/10 bg-[#212121] px-3 py-2 text-xs">
      <span className="text-[#ECECEC]">{label}</span>
      {enabled ? (
        <span className="inline-flex items-center gap-1 font-medium text-emerald-400">
          <CheckCircle2 className="h-3.5 w-3.5" />
          ON
        </span>
      ) : (
        <span className="inline-flex items-center gap-1 font-medium text-[#9B9B9B]">
          <XCircle className="h-3.5 w-3.5" />
          OFF
        </span>
      )}
    </div>
  );
}

export function MemoryDrawer({
  isOpen,
  health,
  activeSessionId,
  summary,
  activeFacts,
  turnCount,
  onClose,
}: MemoryDrawerProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 backdrop-blur-[1px]"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Slide-over Panel */}
      <aside className="relative z-50 flex h-full w-80 max-w-full shrink-0 flex-col border-l border-white/10 bg-[#171717] shadow-2xl">
        <div className="flex items-center justify-between border-b border-white/10 px-4 py-3.5">
          <div className="flex items-center gap-2">
            <Brain className="h-4 w-4 text-[#ECECEC]" />
            <h2 className="text-sm font-semibold text-[#ECECEC]">Memory Inspector</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close Memory Inspector"
            className="rounded-lg p-1 text-[#9B9B9B] transition hover:bg-[#2F2F2F] hover:text-[#ECECEC]"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto p-4">
          {/* Backend Feature Flags */}
          <section className="space-y-2">
            <div className="flex items-center gap-1.5 text-[11px] font-semibold tracking-wider text-[#9B9B9B] uppercase">
              <Cpu className="h-3.5 w-3.5" />
              Memory Subsystems
            </div>
            {health ? (
              <div className="space-y-1.5">
                <StatusBadge label="Persistent SQLite" enabled={health.persistent_memory_enabled} />
                <StatusBadge label="Rolling Summary" enabled={health.summarization_enabled} />
                <StatusBadge label="Long-Term Scope" enabled={health.long_term_memory_enabled} />
              </div>
            ) : (
              <div className="rounded-xl border border-white/10 bg-[#212121] p-3 text-xs text-[#9B9B9B]">
                Backend health unavailable.
              </div>
            )}
          </section>

          {/* Tier 1: Working Session */}
          <section className="space-y-2">
            <div className="flex items-center gap-1.5 text-[11px] font-semibold tracking-wider text-[#9B9B9B] uppercase">
              <Database className="h-3.5 w-3.5" />
              Tier 1 — Working Session
            </div>
            <div className="rounded-xl border border-white/10 bg-[#212121] p-3 text-xs">
              <div className="flex justify-between text-[#9B9B9B]">
                <span>Session ID</span>
                <span className="font-mono text-[11px] text-[#ECECEC]">
                  {activeSessionId ? activeSessionId.slice(0, 14) : "New chat"}
                </span>
              </div>
              <div className="mt-1.5 flex justify-between text-[#9B9B9B]">
                <span>Recorded Turns</span>
                <span className="font-semibold text-[#ECECEC]">{turnCount}</span>
              </div>
            </div>
          </section>

          {/* Tier 2: Rolling Summary */}
          <section className="space-y-2">
            <div className="flex items-center gap-1.5 text-[11px] font-semibold tracking-wider text-[#9B9B9B] uppercase">
              <FileText className="h-3.5 w-3.5" />
              Tier 2 — Rolling Summary
            </div>
            <div className="rounded-xl border border-white/10 bg-[#212121] p-3 text-xs leading-relaxed text-[#ECECEC]">
              {summary.trim() ? (
                summary
              ) : (
                <span className="italic text-[#9B9B9B]">
                  No rolled summary yet. Summaries appear automatically once older turns exceed the
                  short-term window.
                </span>
              )}
            </div>
          </section>

          {/* Tier 3: Active Domain Scope & Facts */}
          <section className="space-y-2">
            <div className="flex items-center gap-1.5 text-[11px] font-semibold tracking-wider text-[#9B9B9B] uppercase">
              <Tag className="h-3.5 w-3.5" />
              Tier 3 — Active Scope ({activeFacts.length})
            </div>
            {activeFacts.length === 0 ? (
              <div className="rounded-xl border border-white/10 bg-[#212121] p-3 text-xs italic text-[#9B9B9B]">
                No extracted standards, controls, or deployment models yet.
              </div>
            ) : (
              <div className="space-y-2">
                {activeFacts.map((fact) => {
                  const pillClass =
                    CATEGORY_STYLE[fact.category] ??
                    "border-white/15 bg-[#2F2F2F] text-[#ECECEC]";
                  return (
                    <div
                      key={fact.fact_id}
                      className="rounded-xl border border-white/10 bg-[#212121] p-3"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span
                          className={`rounded-md border px-1.5 py-0.5 text-[10px] font-semibold uppercase ${pillClass}`}
                        >
                          {fact.category}
                        </span>
                        {fact.source_turn !== null && (
                          <span className="text-[10px] text-[#9B9B9B]">
                            Turn {fact.source_turn}
                          </span>
                        )}
                      </div>
                      <div className="mt-1.5 text-xs font-semibold text-[#ECECEC]">
                        {fact.key}
                      </div>
                      <div className="mt-0.5 text-[11px] text-[#9B9B9B]">
                        {fact.value}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        </div>
      </aside>
    </div>
  );
}
