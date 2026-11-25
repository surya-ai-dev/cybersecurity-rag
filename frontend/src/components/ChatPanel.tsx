import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  ArrowUp,
  BookOpen,
  Brain,
  Check,
  ChevronDown,
  ChevronRight,
  Copy,
  PanelLeftOpen,
  Radio,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Square,
} from "lucide-react";
import { formatPreferenceBadge } from "./PreferencesModal";
import type {
  ChatTurnView,
  HealthResponse,
  SourceChunkDTO,
  UserPreferences,
} from "../types/api";

interface ChatPanelProps {
  health: HealthResponse | null;
  activeSessionId: string | null;
  activeSessionTitle?: string | null;
  turns: ChatTurnView[];
  draftResetVersion?: number;
  newChatSignal?: number;
  preferences: UserPreferences;
  isStreamingEnabled: boolean;
  isSending: boolean;
  errorMessage: string | null;
  isSidebarOpen: boolean;
  isMemoryOpen: boolean;
  activeFactsCount: number;
  onToggleSidebar: () => void;
  onToggleStreaming: () => void;
  onToggleMemory: () => void;
  onOpenPreferences: () => void;
  onSendMessage: (question: string) => void;
  onStopStreaming: () => void;
  onInspectSources: (sources: SourceChunkDTO[], activeIndex?: number) => void;
}

function linkifySources(markdown: string): string {
  return markdown.replace(
    /\[Source\s+(\d+)\]/gi,
    (_match, num: string) => `[Source ${num}](#source-${num})`
  );
}

interface StarterPrompt {
  title: string;
  subtitle: string;
  question: string;
}

const STARTER_PROMPTS: StarterPrompt[] = [
  {
    title: "NIST SP 800-53 AU-3",
    subtitle: "Core audit record elements",
    question:
      "What six core elements must audit records establish under NIST SP 800-53 AU-3?",
  },
  {
    title: "NIST SP 800-146",
    subtitle: "Encryption of data at rest",
    question:
      "What factors must data owners verify for encryption of data at rest in NIST SP 800-146?",
  },
  {
    title: "NIST SP 800-210",
    subtitle: "Multi-tenant SaaS federation",
    question:
      "How does authorization federation alter multi-tenant SaaS policy management in NIST SP 800-210?",
  },
  {
    title: "NIST SP 800-207",
    subtitle: "Zero Trust Architecture tenets",
    question:
      "What are the core tenets of Zero Trust Architecture defined in NIST SP 800-207?",
  },
];

export function ChatPanel({
  health,
  activeSessionId,
  activeSessionTitle = null,
  turns,
  draftResetVersion = 0,
  newChatSignal = 0,
  preferences,
  isStreamingEnabled,
  isSending,
  errorMessage,
  isSidebarOpen,
  isMemoryOpen,
  activeFactsCount,
  onToggleSidebar,
  onToggleStreaming,
  onToggleMemory,
  onOpenPreferences,
  onSendMessage,
  onStopStreaming,
  onInspectSources,
}: ChatPanelProps) {
  const [input, setInput] = useState("");
  const [expandedRewrites, setExpandedRewrites] = useState<Record<string, boolean>>({});
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [newChatHighlight, setNewChatHighlight] = useState(false);

  const endRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    setInput("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [draftResetVersion]);

  useEffect(() => {
    if (newChatSignal <= 0) return;
    setNewChatHighlight(true);
    const frameId = window.requestAnimationFrame(() => {
      textareaRef.current?.focus();
    });
    const timerId = window.setTimeout(() => {
      setNewChatHighlight(false);
    }, 1600);
    return () => {
      window.cancelAnimationFrame(frameId);
      window.clearTimeout(timerId);
    };
  }, [newChatSignal]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, isSending]);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [input]);

  const submit = () => {
    const trimmed = input.trim();
    if (!trimmed || isSending) return;
    setInput("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
    onSendMessage(trimmed);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };

  const toggleRewrite = (key: string) => {
    setExpandedRewrites((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const handleCopyResponse = async (key: string, text: string) => {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopiedKey(key);
      window.setTimeout(() => {
        setCopiedKey((current) => (current === key ? null : current));
      }, 1800);
    } catch {
      // Clipboard API unavailable
    }
  };

  const isHealthy = health?.status === "ok" || health?.status === "healthy";

  return (
    <main className="relative flex min-w-0 flex-1 flex-col bg-[#212121]">
      {/* Minimal Sticky Top Bar */}
      <header className="sticky top-0 z-20 flex h-14 shrink-0 items-center justify-between border-b border-white/10 bg-[#212121]/95 px-4 backdrop-blur-md">
        <div className="flex min-w-0 items-center gap-2.5">
          <button
            type="button"
            onClick={onToggleSidebar}
            title={isSidebarOpen ? "Toggle sidebar" : "Open sidebar"}
            aria-label="Open sidebar"
            className={`inline-flex h-9 w-9 items-center justify-center rounded-lg text-[#9B9B9B] transition hover:bg-[#2F2F2F] hover:text-[#ECECEC] ${
              isSidebarOpen ? "md:hidden" : "inline-flex"
            }`}
          >
            <PanelLeftOpen className="h-4 w-4" />
          </button>

          <div className="flex min-w-0 items-center gap-2">
            <span className="truncate text-sm font-semibold text-[#ECECEC]">
              CyberSec RAG
            </span>
            <span
              className={`hidden max-w-[220px] truncate rounded-full border px-2.5 py-0.5 text-[11px] font-medium transition sm:inline-flex ${
                newChatHighlight
                  ? "border-white/40 bg-white/15 text-white"
                  : activeSessionId === null
                    ? "border-white/15 bg-[#2F2F2F] text-[#ECECEC]"
                    : "border-white/10 bg-transparent text-[#9B9B9B]"
              }`}
            >
              {activeSessionId === null
                ? newChatHighlight
                  ? "New chat ready"
                  : "New chat"
                : activeSessionTitle || "Conversation"}
            </span>
            <span
              title={
                health
                  ? `API ${health.status}${activeSessionId ? ` • Session ${activeSessionId.slice(0, 8)}` : ""}`
                  : "Connecting to API"
              }
              className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-[#2F2F2F]/70 px-2.5 py-0.5 text-[11px] font-medium text-[#9B9B9B]"
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  health === null
                    ? "bg-amber-400"
                    : isHealthy
                      ? "bg-emerald-400"
                      : "bg-rose-400"
                }`}
              />
              <span>
                {health === null ? "Connecting" : isHealthy ? "NIST RAG Ready" : health.status}
              </span>
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onOpenPreferences}
            title="Configure response style and focus preferences"
            className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-transparent px-3 py-1.5 text-xs font-medium text-[#9B9B9B] transition hover:bg-[#2F2F2F] hover:text-[#ECECEC]"
          >
            <SlidersHorizontal className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Preferences</span>
          </button>

          <button
            type="button"
            onClick={onToggleMemory}
            title="Toggle Memory Inspector drawer"
            className={`inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
              isMemoryOpen
                ? "border-white/20 bg-[#2F2F2F] text-[#ECECEC]"
                : "border-white/10 bg-transparent text-[#9B9B9B] hover:bg-[#2F2F2F] hover:text-[#ECECEC]"
            }`}
          >
            <Brain className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Memory Inspector</span>
            <span className="sm:hidden">Memory</span>
            {activeFactsCount > 0 && (
              <span className="rounded-full bg-white/10 px-1.5 py-0.2 text-[10px] font-semibold text-[#ECECEC]">
                {activeFactsCount}
              </span>
            )}
          </button>
        </div>
      </header>

      {/* Error banner */}
      {errorMessage && (
        <div className="border-b border-rose-500/30 bg-rose-950/40 px-4 py-2 text-xs text-rose-200">
          <div className="mx-auto max-w-3xl">
            <span className="font-semibold">Error:</span> {errorMessage}
          </div>
        </div>
      )}

      {/* Scrollable Conversation Area */}
      <div className="flex-1 overflow-y-auto">
        {turns.length === 0 ? (
          <div className="mx-auto flex min-h-full max-w-3xl flex-col items-center justify-center px-4 py-12">
            <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl border border-white/10 bg-[#2F2F2F] text-[#ECECEC]">
              <ShieldCheck className="h-6 w-6" />
            </div>
            <h1 className="text-center text-2xl font-semibold tracking-tight text-[#ECECEC]">
              CyberSec RAG
            </h1>
            <p className="mt-2 max-w-lg text-center text-sm text-[#9B9B9B]">
              Ask grounded questions across NIST Special Publications with multi-turn memory and
              verifiable source citations.
            </p>

            <div className="mt-8 grid w-full grid-cols-1 gap-3 sm:grid-cols-2">
              {STARTER_PROMPTS.map((item) => (
                <button
                  key={item.title}
                  type="button"
                  onClick={() => onSendMessage(item.question)}
                  disabled={isSending}
                  className="group rounded-2xl border border-white/10 bg-[#2F2F2F]/50 p-4 text-left transition hover:border-white/20 hover:bg-[#2F2F2F] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-semibold text-[#ECECEC]">
                      {item.title}
                    </span>
                    <span className="text-[11px] text-[#9B9B9B]">{item.subtitle}</span>
                  </div>
                  <p className="mt-1.5 line-clamp-2 text-xs leading-relaxed text-[#9B9B9B] group-hover:text-[#ECECEC]/90">
                    {item.question}
                  </p>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="mx-auto max-w-3xl space-y-8 px-4 pt-6 pb-8">
            {turns.map((turn, idx) => {
              const turnKey = `${turn.turn_index}-${idx}`;
              const hasRewrite =
                Boolean(turn.standalone_question) &&
                turn.standalone_question?.trim() !== turn.user.trim();
              const isRewriteExpanded = Boolean(expandedRewrites[turnKey]);
              const sources = turn.sources ?? [];

              return (
                <div key={turnKey} className="space-y-6">
                  {/* User Message Pill */}
                  <div className="flex justify-end">
                    <div className="max-w-[75%] rounded-3xl bg-[#2F2F2F] px-5 py-3 text-[15px] leading-relaxed whitespace-pre-wrap text-[#ECECEC]">
                      {turn.user}
                    </div>
                  </div>

                  {/* Assistant Turn */}
                  <div className="flex items-start gap-4">
                    <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-white/10 bg-[#171717] text-[#ECECEC]">
                      <ShieldCheck className="h-4 w-4" />
                    </div>

                    <div className="min-w-0 flex-1 space-y-2.5">
                      {/* Collapsible Standalone Rewritten Query Pill */}
                      {hasRewrite && (
                        <div>
                          <button
                            type="button"
                            onClick={() => toggleRewrite(turnKey)}
                            className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-[#171717] px-2.5 py-1 text-[11px] font-medium text-[#9B9B9B] transition hover:border-white/20 hover:text-[#ECECEC]"
                          >
                            <Sparkles className="h-3 w-3" />
                            <span>Rewritten query</span>
                            {isRewriteExpanded ? (
                              <ChevronDown className="h-3 w-3" />
                            ) : (
                              <ChevronRight className="h-3 w-3" />
                            )}
                          </button>
                          {isRewriteExpanded && (
                            <div className="mt-1.5 rounded-xl border border-white/10 bg-[#171717] px-3 py-2 text-xs text-[#9B9B9B]">
                              {turn.standalone_question}
                            </div>
                          )}
                        </div>
                      )}

                      {/* Markdown Answer Body */}
                      {turn.assistant ? (
                        <div className="prose prose-invert max-w-none">
                          <ReactMarkdown
                            remarkPlugins={[remarkGfm]}
                            components={{
                              a: ({ href, children }) => {
                                const match = href?.match(/^#source-(\d+)$/);
                                if (match) {
                                  const sourceIndex = Number(match[1]);
                                  if (sources.length > 0) {
                                    return (
                                      <button
                                        type="button"
                                        onClick={() => onInspectSources(sources, sourceIndex)}
                                        className="mx-0.5 inline-flex items-center rounded-md border border-white/15 bg-[#2F2F2F] px-1.5 py-0.5 text-[11px] font-medium text-[#ECECEC] transition hover:border-white/30 hover:bg-white/15"
                                      >
                                        {children}
                                      </button>
                                    );
                                  }
                                  return (
                                    <span className="mx-0.5 inline-flex items-center rounded-md border border-white/10 bg-[#2F2F2F]/70 px-1.5 py-0.5 text-[11px] font-medium text-[#9B9B9B]">
                                      {children}
                                    </span>
                                  );
                                }
                                return (
                                  <a
                                    href={href}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="text-[#ECECEC] underline decoration-white/30 underline-offset-2 hover:decoration-white"
                                  >
                                    {children}
                                  </a>
                                );
                              },
                            }}
                          >
                            {linkifySources(turn.assistant)}
                          </ReactMarkdown>
                        </div>
                      ) : turn.isStreaming ? (
                        <div className="inline-flex items-center gap-2 py-1 text-sm text-[#9B9B9B]">
                          <span className="h-2 w-2 animate-pulse rounded-full bg-[#ECECEC]" />
                          <span>Searching NIST standards and drafting response...</span>
                        </div>
                      ) : (
                        <span className="text-xs italic text-[#9B9B9B]">(No response)</span>
                      )}

                      {/* Compact Footer Action Bar */}
                      {(turn.assistant || sources.length > 0) && !turn.isStreaming && (
                        <div className="flex flex-wrap items-center gap-2 pt-1">
                          {turn.assistant && (
                            <button
                              type="button"
                              onClick={() => handleCopyResponse(turnKey, turn.assistant)}
                              className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs text-[#9B9B9B] transition hover:bg-[#2F2F2F] hover:text-[#ECECEC]"
                            >
                              {copiedKey === turnKey ? (
                                <>
                                  <Check className="h-3.5 w-3.5 text-emerald-400" />
                                  <span className="text-[#ECECEC]">Copied</span>
                                </>
                              ) : (
                                <>
                                  <Copy className="h-3.5 w-3.5" />
                                  <span>Copy</span>
                                </>
                              )}
                            </button>
                          )}

                          {sources.length > 0 ? (
                            <button
                              type="button"
                              onClick={() => onInspectSources(sources)}
                              className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs text-[#9B9B9B] transition hover:bg-[#2F2F2F] hover:text-[#ECECEC]"
                            >
                              <BookOpen className="h-3.5 w-3.5" />
                              <span>View Sources ({sources.length})</span>
                            </button>
                          ) : (
                            turn.source_chunk_ids &&
                            turn.source_chunk_ids.length > 0 && (
                              <span className="inline-flex items-center gap-1.5 px-2 py-1 text-xs text-[#9B9B9B]">
                                <BookOpen className="h-3.5 w-3.5" />
                                <span>{turn.source_chunk_ids.length} cited chunks</span>
                              </span>
                            )
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
            <div ref={endRef} />
          </div>
        )}
      </div>

      {/* Bottom Floating Pill Composer with Gradient Fade */}
      <div className="relative shrink-0 bg-[#212121] px-4 pt-2 pb-4">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-x-0 -top-8 h-8 bg-gradient-to-t from-[#212121] to-transparent"
        />

        <div className="mx-auto max-w-3xl">
          <div
            className={`rounded-3xl border bg-[#2F2F2F] px-4 pt-3 pb-2.5 shadow-lg transition ${
              newChatHighlight
                ? "border-white/35 ring-2 ring-white/20"
                : "border-white/10"
            }`}
          >
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={1}
              disabled={isSending}
              placeholder="Message CyberSec RAG..."
              className="max-h-[200px] w-full resize-none bg-transparent text-[15px] leading-relaxed text-[#ECECEC] placeholder-[#9B9B9B] focus:outline-none disabled:opacity-60"
            />

            <div className="mt-2 flex items-center justify-between gap-2">
              <div className="flex flex-wrap items-center gap-1.5">
                <button
                  type="button"
                  onClick={onToggleStreaming}
                  disabled={isSending}
                  title="Toggle between SSE token streaming and standard /chat JSON"
                  className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium transition disabled:opacity-50 ${
                    isStreamingEnabled
                      ? "border-white/20 bg-white/10 text-[#ECECEC]"
                      : "border-white/10 bg-transparent text-[#9B9B9B] hover:border-white/20 hover:text-[#ECECEC]"
                  }`}
                >
                  <Radio className="h-3 w-3" />
                  <span>{isStreamingEnabled ? "Stream SSE" : "Standard JSON"}</span>
                </button>

                <button
                  type="button"
                  onClick={onOpenPreferences}
                  title="Active response style — click to customize preferences"
                  className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-[11px] font-medium text-[#9B9B9B] transition hover:border-white/20 hover:bg-white/10 hover:text-[#ECECEC]"
                >
                  <SlidersHorizontal className="h-3 w-3" />
                  <span>{formatPreferenceBadge(preferences)}</span>
                </button>
              </div>

              {isSending && isStreamingEnabled ? (
                <button
                  type="button"
                  onClick={onStopStreaming}
                  title="Stop generating"
                  aria-label="Stop generating"
                  className="flex h-8 w-8 items-center justify-center rounded-full bg-[#ECECEC] text-[#171717] transition hover:bg-white"
                >
                  <Square className="h-3.5 w-3.5 fill-current" />
                </button>
              ) : (
                <button
                  type="button"
                  onClick={submit}
                  disabled={isSending || !input.trim()}
                  title="Send message"
                  aria-label="Send message"
                  className="flex h-8 w-8 items-center justify-center rounded-full bg-[#ECECEC] text-[#171717] transition hover:bg-white disabled:cursor-not-allowed disabled:bg-white/20 disabled:text-[#212121]"
                >
                  <ArrowUp className="h-4 w-4 stroke-[2.25]" />
                </button>
              )}
            </div>
          </div>

          <p className="mt-2 text-center text-[11px] text-[#9B9B9B]">
            Grounded in NIST Special Publications. Verify cited sources before production use.
          </p>
        </div>
      </div>
    </main>
  );
}
