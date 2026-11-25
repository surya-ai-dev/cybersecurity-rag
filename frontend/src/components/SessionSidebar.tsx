import { useMemo, useState } from "react";
import type { KeyboardEvent } from "react";
import {
  Check,
  PanelLeftClose,
  Pencil,
  RefreshCw,
  SquarePen,
  Trash2,
  X,
} from "lucide-react";
import type { SessionSummaryDTO } from "../types/api";

interface SessionSidebarProps {
  isOpen: boolean;
  sessions: SessionSummaryDTO[];
  activeSessionId: string | null;
  isLoading: boolean;
  onClose: () => void;
  onCreateSession: () => void;
  onSelectSession: (sessionId: string) => void;
  onRenameSession: (sessionId: string, title: string) => void;
  onDeleteSession: (sessionId: string) => void;
  onRefreshSessions: () => void;
}

const GENERIC_LABELS = new Set(["", "new session", "in-memory session"]);

function formatSessionLabel(sess: SessionSummaryDTO): string {
  const rawTitle = (sess.title ?? "").trim();
  if (!GENERIC_LABELS.has(rawTitle.toLowerCase())) {
    return rawTitle;
  }
  const summary = (sess.summary ?? "").replace(/\s+/g, " ").trim();
  if (summary) {
    return summary.length > 44 ? `${summary.slice(0, 44).trimEnd()}…` : summary;
  }
  return "New chat";
}

function getActivityTimestampMs(sess: SessionSummaryDTO): number {
  const raw = sess.updated_at || sess.created_at;
  if (!raw) return 0;
  const ms = Date.parse(raw);
  return Number.isNaN(ms) ? 0 : ms;
}

export function SessionSidebar({
  isOpen,
  sessions,
  activeSessionId,
  isLoading,
  onClose,
  onCreateSession,
  onSelectSession,
  onRenameSession,
  onDeleteSession,
  onRefreshSessions,
}: SessionSidebarProps) {
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState("");

  const orderedSessions = useMemo(
    () =>
      [...sessions].sort(
        (a, b) => getActivityTimestampMs(b) - getActivityTimestampMs(a)
      ),
    [sessions]
  );

  if (!isOpen) return null;

  const startRename = (sess: SessionSummaryDTO) => {
    setEditingSessionId(sess.session_id);
    setDraftTitle(formatSessionLabel(sess));
  };

  const cancelRename = () => {
    setEditingSessionId(null);
    setDraftTitle("");
  };

  const commitRename = (sessionId: string) => {
    const trimmed = draftTitle.trim();
    setEditingSessionId(null);
    setDraftTitle("");
    if (trimmed) {
      onRenameSession(sessionId, trimmed);
    }
  };

  const handleRenameKeyDown = (
    e: KeyboardEvent<HTMLInputElement>,
    sessionId: string
  ) => {
    if (e.key === "Enter") {
      e.preventDefault();
      commitRename(sessionId);
    } else if (e.key === "Escape") {
      e.preventDefault();
      cancelRename();
    }
  };

  return (
    <>
      {/* Mobile slide-over backdrop */}
      <div
        className="fixed inset-0 z-30 bg-black/60 backdrop-blur-[1px] md:hidden"
        onClick={onClose}
        aria-hidden="true"
      />

      <aside className="fixed inset-y-0 left-0 z-40 flex h-full w-[260px] shrink-0 flex-col border-r border-white/10 bg-[#171717] md:static md:z-auto">
        {/* Top bar with collapse button & full-width rounded New chat CTA */}
        <div className="space-y-2.5 px-3 pt-3 pb-2">
          <div className="flex items-center justify-between px-1">
            <span className="text-xs font-semibold tracking-wide text-[#9B9B9B]">
              CyberSec RAG
            </span>
            <button
              type="button"
              onClick={onClose}
              title="Collapse sidebar"
              aria-label="Collapse sidebar"
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-[#9B9B9B] transition hover:bg-[#242424] hover:text-[#ECECEC]"
            >
              <PanelLeftClose className="h-4 w-4" />
            </button>
          </div>

          <button
            type="button"
            onClick={onCreateSession}
            className={`flex w-full items-center justify-between rounded-xl border px-3.5 py-2.5 text-sm font-medium text-[#ECECEC] transition ${
              activeSessionId === null
                ? "border-white/30 bg-[#242424]"
                : "border-white/15 bg-[#1a1a1a] hover:bg-[#242424]"
            }`}
          >
            <span>New chat</span>
            <SquarePen className="h-4 w-4 text-[#9B9B9B]" />
          </button>
        </div>

        {/* Recents heading + subtle refresh */}
        <div className="flex items-center justify-between px-4 pt-3 pb-1.5">
          <span className="text-[11px] font-medium tracking-wide text-[#9B9B9B]">
            Recents
          </span>
          <button
            type="button"
            onClick={onRefreshSessions}
            disabled={isLoading}
            title="Refresh chats"
            aria-label="Refresh chats"
            className="rounded-md p-1 text-[#9B9B9B] transition hover:bg-[#242424] hover:text-[#ECECEC] disabled:opacity-40"
          >
            <RefreshCw className={`h-3 w-3 ${isLoading ? "animate-spin" : ""}`} />
          </button>
        </div>

        {/* Single-line Recents list ordered by most recent activity */}
        <div className="flex-1 space-y-0.5 overflow-y-auto px-2 pb-3">
          {orderedSessions.length === 0 ? (
            <div className="px-3 py-6 text-center text-xs text-[#9B9B9B]">
              No recent chats yet.
            </div>
          ) : (
            orderedSessions.map((sess) => {
              const isActive = sess.session_id === activeSessionId;
              const isEditing = editingSessionId === sess.session_id;
              const isPending = sess.session_id === "__pending_session__";
              const label = formatSessionLabel(sess);

              return (
                <div
                  key={sess.session_id}
                  className={`group relative flex h-9 items-center rounded-lg transition ${
                    isActive
                      ? "bg-[#2F2F2F] text-white"
                      : "text-[#ECECEC]/85 hover:bg-[#242424] hover:text-white"
                  }`}
                >
                  {isEditing ? (
                    <div className="flex min-w-0 flex-1 items-center gap-1 px-2">
                      <input
                        type="text"
                        autoFocus
                        value={draftTitle}
                        onChange={(e) => setDraftTitle(e.target.value)}
                        onKeyDown={(e) => handleRenameKeyDown(e, sess.session_id)}
                        maxLength={120}
                        aria-label="Rename conversation"
                        className="min-w-0 flex-1 rounded border border-white/25 bg-[#171717] px-2 py-0.5 text-[13px] text-white focus:outline-none"
                      />
                      <button
                        type="button"
                        onClick={() => commitRename(sess.session_id)}
                        title="Save title"
                        aria-label="Save title"
                        className="rounded p-1 text-emerald-400 hover:bg-[#171717]"
                      >
                        <Check className="h-3.5 w-3.5" />
                      </button>
                      <button
                        type="button"
                        onClick={cancelRename}
                        title="Cancel rename"
                        aria-label="Cancel rename"
                        className="rounded p-1 text-[#9B9B9B] hover:bg-[#171717] hover:text-[#ECECEC]"
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ) : (
                    <>
                      <button
                        type="button"
                        onClick={() => onSelectSession(sess.session_id)}
                        disabled={isPending}
                        title={`${label} (${sess.turn_count} ${sess.turn_count === 1 ? "turn" : "turns"})`}
                        className="min-w-0 flex-1 px-2.5 py-1.5 text-left disabled:cursor-wait"
                      >
                        <span
                          className={`block truncate text-[13px] ${
                            isActive ? "font-medium text-white" : "font-normal"
                          }`}
                        >
                          {label}
                        </span>
                      </button>

                      {/* Hover/focus actions: Rename & Delete */}
                      {!isPending && (
                        <div
                          className={`flex shrink-0 items-center gap-0.5 pr-1.5 transition-opacity ${
                            isActive
                              ? "opacity-75 hover:opacity-100"
                              : "opacity-0 group-hover:opacity-100 group-focus-within:opacity-100"
                          }`}
                        >
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              startRename(sess);
                            }}
                            title="Rename chat"
                            aria-label="Rename chat"
                            className="rounded-md p-1 text-[#9B9B9B] transition hover:bg-[#171717] hover:text-[#ECECEC]"
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </button>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              onDeleteSession(sess.session_id);
                            }}
                            title="Delete chat"
                            aria-label="Delete chat"
                            className="rounded-md p-1 text-[#9B9B9B] transition hover:bg-[#171717] hover:text-rose-400"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      )}
                    </>
                  )}
                </div>
              );
            })
          )}
        </div>

        {/* Minimal Footer */}
        <div className="border-t border-white/10 px-4 py-2.5 text-[11px] text-[#9B9B9B]">
          NIST Cybersecurity Assistant
        </div>
      </aside>
    </>
  );
}
