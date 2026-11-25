import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  deleteSession,
  fetchHealth,
  getSessionDetail,
  listSessions,
  renameSession,
  sendChat,
  streamChat,
} from "./api/client";
import { ChatPanel } from "./components/ChatPanel";
import { MemoryDrawer } from "./components/MemoryDrawer";
import { DEFAULT_PREFERENCES, PreferencesModal } from "./components/PreferencesModal";
import { SessionSidebar } from "./components/SessionSidebar";
import { SourcesModal } from "./components/SourcesModal";
import type {
  ChatTurnView,
  HealthResponse,
  MemoryFactDTO,
  SessionSummaryDTO,
  SourceChunkDTO,
  UserPreferences,
} from "./types/api";

const PENDING_SESSION_ID = "__pending_session__";
const PREFERENCES_STORAGE_KEY = "cybersec_rag_preferences_v1";
const ACTIVE_SESSION_STORAGE_KEY = "cybersec_rag_active_session_id";

function loadStoredPreferences(): UserPreferences {
  if (typeof window === "undefined") return DEFAULT_PREFERENCES;
  try {
    const raw = window.localStorage.getItem(PREFERENCES_STORAGE_KEY);
    if (!raw) return DEFAULT_PREFERENCES;
    const parsed = JSON.parse(raw) as Partial<UserPreferences>;
    return {
      detail_level: parsed.detail_level ?? DEFAULT_PREFERENCES.detail_level,
      response_format: parsed.response_format ?? DEFAULT_PREFERENCES.response_format,
      focus_lens: parsed.focus_lens ?? DEFAULT_PREFERENCES.focus_lens,
      custom_instructions: parsed.custom_instructions ?? "",
    };
  } catch {
    return DEFAULT_PREFERENCES;
  }
}

function readSavedSessionId(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const saved = window.localStorage.getItem(ACTIVE_SESSION_STORAGE_KEY);
    return saved && saved.trim() ? saved.trim() : null;
  } catch {
    return null;
  }
}

function writeSavedSessionId(sessionId: string | null): void {
  if (typeof window === "undefined") return;
  try {
    if (sessionId && sessionId !== PENDING_SESSION_ID) {
      window.localStorage.setItem(ACTIVE_SESSION_STORAGE_KEY, sessionId);
    } else {
      window.localStorage.removeItem(ACTIVE_SESSION_STORAGE_KEY);
    }
  } catch {
    // Ignore storage errors
  }
}

const PLACEHOLDER_TITLES = new Set([
  "",
  "new session",
  "in-memory session",
  "new chat",
]);

function isPlaceholderTitle(title: string | null | undefined): boolean {
  return PLACEHOLDER_TITLES.has((title ?? "").trim().toLowerCase());
}

function deriveTitleFromText(text: string | null | undefined, maxLen = 48): string {
  const normalized = (text ?? "").replace(/\s+/g, " ").trim();
  if (!normalized) return "New chat";
  if (normalized.length <= maxLen) return normalized;
  const sliced = normalized.slice(0, maxLen);
  const lastSpace = sliced.lastIndexOf(" ");
  const base = lastSpace > 18 ? sliced.slice(0, lastSpace) : sliced;
  return `${base.trimEnd()}…`;
}

function getActivityMs(sess: SessionSummaryDTO): number {
  const raw = sess.updated_at || sess.created_at;
  if (!raw) return 0;
  const ms = Date.parse(raw);
  return Number.isNaN(ms) ? 0 : ms;
}

function sortSessionsByRecency(list: SessionSummaryDTO[]): SessionSummaryDTO[] {
  return [...list].sort((a, b) => getActivityMs(b) - getActivityMs(a));
}

function pickNewerTimestamp(a?: string, b?: string): string {
  const msA = a ? Date.parse(a) : NaN;
  const msB = b ? Date.parse(b) : NaN;
  if (!Number.isNaN(msA) && !Number.isNaN(msB)) {
    return msA >= msB ? (a as string) : (b as string);
  }
  if (!Number.isNaN(msA)) return a as string;
  if (!Number.isNaN(msB)) return b as string;
  return "";
}

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [sessions, setSessions] = useState<SessionSummaryDTO[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [turns, setTurns] = useState<ChatTurnView[]>([]);
  const [summary, setSummary] = useState("");
  const [activeFacts, setActiveFacts] = useState<MemoryFactDTO[]>([]);
  const [draftResetVersion, setDraftResetVersion] = useState(0);
  const [newChatSignal, setNewChatSignal] = useState(0);

  const [isLoadingSessions, setIsLoadingSessions] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [isStreamingEnabled, setIsStreamingEnabled] = useState(true);
  const [isSidebarOpen, setIsSidebarOpen] = useState(() =>
    typeof window !== "undefined" ? window.innerWidth >= 768 : true
  );
  const [isMemoryOpen, setIsMemoryOpen] = useState(false);
  const [isPreferencesOpen, setIsPreferencesOpen] = useState(false);
  const [preferences, setPreferences] = useState<UserPreferences>(loadStoredPreferences);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [inspectedSources, setInspectedSources] = useState<SourceChunkDTO[] | null>(null);
  const [highlightedSourceIndex, setHighlightedSourceIndex] = useState<number | undefined>(
    undefined
  );

  const abortControllerRef = useRef<AbortController | null>(null);
  const requestTokenRef = useRef(0);
  const navigationEpochRef = useRef(0);
  const suppressAutoSelectRef = useRef(false);
  const didMountInitRef = useRef(false);
  const derivedTitlesRef = useRef<Record<string, string>>({});
  const localUpdatedAtRef = useRef<Record<string, string>>({});
  const deletedSessionIdsRef = useRef<Set<string>>(new Set());
  const activeSessionIdRef = useRef<string | null>(activeSessionId);
  const turnsRef = useRef<ChatTurnView[]>(turns);

  useEffect(() => {
    activeSessionIdRef.current = activeSessionId;
  }, [activeSessionId]);

  useEffect(() => {
    turnsRef.current = turns;
  }, [turns]);

  const abortActiveRequest = useCallback(() => {
    requestTokenRef.current += 1;
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsSending(false);
  }, []);

  const normalizeSessions = useCallback(
    (rawList: SessionSummaryDTO[]): SessionSummaryDTO[] => {
      const currentSid = activeSessionIdRef.current;
      const currentTurns = turnsRef.current;

      const normalized = rawList
        .filter((sess) => !deletedSessionIdsRef.current.has(sess.session_id))
        .map((sess) => {
          const isCurrent = currentSid !== null && sess.session_id === currentSid;
          const firstUserText = isCurrent ? currentTurns[0]?.user : undefined;

          if (firstUserText && !derivedTitlesRef.current[sess.session_id]) {
            derivedTitlesRef.current[sess.session_id] = deriveTitleFromText(firstUserText);
          }

          const cachedTitle = derivedTitlesRef.current[sess.session_id];
          let resolvedTitle = sess.title;

          if (!isPlaceholderTitle(sess.title)) {
            resolvedTitle = sess.title;
          } else if (cachedTitle) {
            resolvedTitle = cachedTitle;
          } else if (sess.summary?.trim()) {
            resolvedTitle = deriveTitleFromText(sess.summary);
          } else {
            resolvedTitle = "New chat";
          }

          const resolvedTurnCount =
            isCurrent && currentTurns.length > 0
              ? Math.max(sess.turn_count, currentTurns.length)
              : sess.turn_count;

          const updatedAt = pickNewerTimestamp(
            sess.updated_at || sess.created_at,
            localUpdatedAtRef.current[sess.session_id]
          );

          return {
            ...sess,
            title: resolvedTitle,
            turn_count: resolvedTurnCount,
            updated_at: updatedAt,
          };
        });

      return sortSessionsByRecency(normalized);
    },
    []
  );

  const upsertLocalSession = useCallback(
    (
      sessionId: string,
      patch: Partial<SessionSummaryDTO> & { replacePendingId?: string }
    ) => {
      const now = patch.updated_at ?? new Date().toISOString();
      deletedSessionIdsRef.current.delete(sessionId);
      localUpdatedAtRef.current[sessionId] = pickNewerTimestamp(
        now,
        localUpdatedAtRef.current[sessionId]
      );

      setSessions((prev) => {
        const filtered = patch.replacePendingId
          ? prev.filter((s) => s.session_id !== patch.replacePendingId)
          : prev;
        const existingIdx = filtered.findIndex((s) => s.session_id === sessionId);

        let nextList: SessionSummaryDTO[];
        if (existingIdx >= 0) {
          const updated = {
            ...filtered[existingIdx],
            ...patch,
            session_id: sessionId,
            updated_at: localUpdatedAtRef.current[sessionId],
          };
          nextList = filtered.map((item, idx) => (idx === existingIdx ? updated : item));
        } else {
          const created: SessionSummaryDTO = {
            session_id: sessionId,
            title: patch.title ?? derivedTitlesRef.current[sessionId] ?? "New chat",
            summary: patch.summary ?? "",
            turn_count: patch.turn_count ?? 0,
            created_at: patch.created_at ?? now,
            updated_at: localUpdatedAtRef.current[sessionId],
          };
          nextList = [created, ...filtered];
        }

        return sortSessionsByRecency(nextList);
      });
    },
    []
  );

  const refreshSessionsAndHealth = useCallback(async () => {
    setIsLoadingSessions(true);
    try {
      const [h, sessList] = await Promise.all([fetchHealth(), listSessions(30)]);
      setHealth(h);
      const normalized = normalizeSessions(sessList);
      setSessions(normalized);
      return normalized;
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to connect to backend API."
      );
      return [] as SessionSummaryDTO[];
    } finally {
      setIsLoadingSessions(false);
    }
  }, [normalizeSessions]);

  const loadSession = useCallback(
    async (sessionId: string) => {
      if (!sessionId || sessionId === PENDING_SESSION_ID) return;
      if (sessionId === activeSessionIdRef.current) {
        if (typeof window !== "undefined" && window.innerWidth < 768) {
          setIsSidebarOpen(false);
        }
        return;
      }

      // Explicit session click cancels active stream and allows navigation
      suppressAutoSelectRef.current = false;
      abortActiveRequest();
      const myEpoch = ++navigationEpochRef.current;
      setErrorMessage(null);
      setInspectedSources(null);
      setHighlightedSourceIndex(undefined);

      activeSessionIdRef.current = sessionId;
      setActiveSessionId(sessionId);

      try {
        const detail = await getSessionDetail(sessionId);
        if (navigationEpochRef.current !== myEpoch) return;

        const sid = detail.session.session_id;
        deletedSessionIdsRef.current.delete(sid);
        activeSessionIdRef.current = sid;
        setActiveSessionId(sid);
        writeSavedSessionId(sid);
        setTurns(detail.turns);
        setSummary(detail.session.summary);
        setActiveFacts(detail.active_facts);
        setDraftResetVersion((v) => v + 1);

        if (detail.turns.length > 0 && isPlaceholderTitle(detail.session.title)) {
          derivedTitlesRef.current[sid] = deriveTitleFromText(detail.turns[0].user);
        }

        const resolvedTitle = !isPlaceholderTitle(detail.session.title)
          ? detail.session.title
          : derivedTitlesRef.current[sid] ??
            (detail.session.summary?.trim()
              ? deriveTitleFromText(detail.session.summary)
              : "New chat");

        setSessions((prev) =>
          sortSessionsByRecency(
            prev.map((s) =>
              s.session_id === sid
                ? {
                    ...s,
                    title: resolvedTitle,
                    summary: detail.session.summary,
                    turn_count: detail.turns.length,
                  }
                : s
            )
          )
        );

        if (typeof window !== "undefined" && window.innerWidth < 768) {
          setIsSidebarOpen(false);
        }
      } catch (err) {
        if (navigationEpochRef.current !== myEpoch) return;
        if (err instanceof ApiError && err.status === 404) {
          deletedSessionIdsRef.current.add(sessionId);
          delete derivedTitlesRef.current[sessionId];
          setSessions((prev) => prev.filter((s) => s.session_id !== sessionId));
          if (readSavedSessionId() === sessionId) {
            writeSavedSessionId(null);
          }
          if (activeSessionIdRef.current === sessionId) {
            activeSessionIdRef.current = null;
            setActiveSessionId(null);
            setTurns([]);
            setSummary("");
            setActiveFacts([]);
          }
          return;
        }
        setErrorMessage(err instanceof Error ? err.message : "Failed to load session.");
      }
    },
    [abortActiveRequest]
  );

  // Run strictly once on initial mount; never re-run on state changes so "New chat" cannot blink back
  useEffect(() => {
    if (didMountInitRef.current) return;
    didMountInitRef.current = true;
    const initEpoch = navigationEpochRef.current;

    void (async () => {
      const sessList = await refreshSessionsAndHealth();
      if (suppressAutoSelectRef.current || navigationEpochRef.current !== initEpoch) {
        return;
      }

      const savedSid = readSavedSessionId();
      if (savedSid) {
        const matchedSaved = sessList.find((s) => s.session_id === savedSid);
        if (matchedSaved) {
          await loadSession(matchedSaved.session_id);
        } else {
          writeSavedSessionId(null);
        }
      } else if (sessList.length > 0 && sessList[0].turn_count > 0) {
        await loadSession(sessList[0].session_id);
      }

      const unnamed = sessList
        .slice(1, 10)
        .filter((s) => s.turn_count > 0 && isPlaceholderTitle(s.title));
      if (unnamed.length > 0) {
        await Promise.all(
          unnamed.map(async (s) => {
            try {
              const detail = await getSessionDetail(s.session_id);
              if (detail.turns.length > 0) {
                const label = deriveTitleFromText(detail.turns[0].user);
                derivedTitlesRef.current[s.session_id] = label;
                setSessions((prev) =>
                  prev.map((item) =>
                    item.session_id === s.session_id
                      ? { ...item, title: label, turn_count: detail.turns.length }
                      : item
                  )
                );
              }
            } catch {
              // Ignore 404 or transient errors during background title hydration
            }
          })
        );
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleCreateSession = () => {
    // Prevent initial useEffect or in-flight fetches from auto-selecting sessions[0]
    suppressAutoSelectRef.current = true;
    navigationEpochRef.current += 1;
    abortActiveRequest();

    setErrorMessage(null);
    setInspectedSources(null);
    setHighlightedSourceIndex(undefined);
    writeSavedSessionId(null);

    activeSessionIdRef.current = null;
    setActiveSessionId(null);
    setTurns([]);
    setSummary("");
    setActiveFacts([]);
    setDraftResetVersion((v) => v + 1);
    setNewChatSignal((v) => v + 1);
    setSessions((prev) => prev.filter((s) => s.session_id !== PENDING_SESSION_ID));

    if (typeof window !== "undefined" && window.innerWidth < 768) {
      setIsSidebarOpen(false);
    }
  };

  const handleRenameSession = async (sessionId: string, newTitle: string) => {
    const cleanTitle = newTitle.replace(/\s+/g, " ").trim().slice(0, 120);
    if (!cleanTitle || sessionId === PENDING_SESSION_ID) return;
    setErrorMessage(null);

    derivedTitlesRef.current[sessionId] = cleanTitle;
    setSessions((prev) =>
      prev.map((s) => (s.session_id === sessionId ? { ...s, title: cleanTitle } : s))
    );

    try {
      const updated = await renameSession(sessionId, cleanTitle);
      setSessions((prev) =>
        prev.map((s) =>
          s.session_id === sessionId ? { ...s, title: updated.title } : s
        )
      );
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        return;
      }
      setErrorMessage(err instanceof Error ? err.message : "Could not rename session.");
    }
  };

  const handleDeleteSession = async (sessionId: string) => {
    setErrorMessage(null);

    if (sessionId === activeSessionIdRef.current) {
      suppressAutoSelectRef.current = true;
      abortActiveRequest();
      navigationEpochRef.current += 1;
      activeSessionIdRef.current = null;
      setActiveSessionId(null);
      setTurns([]);
      setSummary("");
      setActiveFacts([]);
      setInspectedSources(null);
      setHighlightedSourceIndex(undefined);
      setDraftResetVersion((v) => v + 1);
    }

    if (readSavedSessionId() === sessionId) {
      writeSavedSessionId(null);
    }

    deletedSessionIdsRef.current.add(sessionId);
    delete derivedTitlesRef.current[sessionId];
    delete localUpdatedAtRef.current[sessionId];
    setSessions((prev) => prev.filter((s) => s.session_id !== sessionId));

    if (sessionId === PENDING_SESSION_ID) return;

    try {
      await deleteSession(sessionId);
      await refreshSessionsAndHealth();
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        return;
      }
      setErrorMessage(err instanceof Error ? err.message : "Could not delete session.");
    }
  };

  const handleSavePreferences = (next: UserPreferences) => {
    setPreferences(next);
    if (typeof window !== "undefined") {
      try {
        window.localStorage.setItem(PREFERENCES_STORAGE_KEY, JSON.stringify(next));
      } catch {
        // Ignore storage quota errors
      }
    }
  };

  const handleStopStreaming = () => {
    abortActiveRequest();
    setTurns((prev) =>
      prev.map((t, i) => (i === prev.length - 1 ? { ...t, isStreaming: false } : t))
    );
  };

  const handleSendMessage = async (question: string) => {
    if (isSending) return;
    setErrorMessage(null);
    setIsSending(true);

    suppressAutoSelectRef.current = true;
    const myToken = ++requestTokenRef.current;
    navigationEpochRef.current += 1;

    const now = new Date().toISOString();
    const isFirstTurn = turns.length === 0;
    const optimisticIndex = turns.length + 1;
    const firstTurnTitle = isFirstTurn ? deriveTitleFromText(question) : undefined;
    const currentSid = activeSessionIdRef.current;
    const backendSessionId =
      currentSid && currentSid !== PENDING_SESSION_ID ? currentSid : null;

    if (backendSessionId) {
      deletedSessionIdsRef.current.delete(backendSessionId);
      if (firstTurnTitle && !derivedTitlesRef.current[backendSessionId]) {
        derivedTitlesRef.current[backendSessionId] = firstTurnTitle;
      }
      upsertLocalSession(backendSessionId, {
        ...(firstTurnTitle ? { title: firstTurnTitle } : {}),
        turn_count: optimisticIndex,
        updated_at: now,
      });
    } else {
      activeSessionIdRef.current = PENDING_SESSION_ID;
      setActiveSessionId(PENDING_SESSION_ID);
      upsertLocalSession(PENDING_SESSION_ID, {
        title: firstTurnTitle ?? "New chat",
        turn_count: optimisticIndex,
        created_at: now,
        updated_at: now,
      });
    }

    setTurns((prev) => [
      ...prev,
      {
        turn_index: optimisticIndex,
        user: question,
        assistant: "",
        standalone_question: null,
        source_chunk_ids: [],
        timestamp: now,
        sources: [],
        isStreaming: isStreamingEnabled,
      },
    ]);

    if (!isStreamingEnabled) {
      try {
        const res = await sendChat({
          question,
          session_id: backendSessionId,
          preferences,
        });
        if (requestTokenRef.current !== myToken) return;

        const resolvedSid = res.session_id;
        const doneAt = new Date().toISOString();
        deletedSessionIdsRef.current.delete(resolvedSid);
        if (firstTurnTitle && !derivedTitlesRef.current[resolvedSid]) {
          derivedTitlesRef.current[resolvedSid] = firstTurnTitle;
        }
        activeSessionIdRef.current = resolvedSid;
        setActiveSessionId(resolvedSid);
        writeSavedSessionId(resolvedSid);
        setSummary(res.memory_context.summary);
        setActiveFacts(res.memory_context.active_facts);
        setTurns((prev) =>
          prev.map((t, i) =>
            i === prev.length - 1
              ? {
                  ...t,
                  assistant: res.answer,
                  standalone_question: res.standalone_question,
                  source_chunk_ids: res.sources.map((s) => s.chunk_id),
                  sources: res.sources,
                  isStreaming: false,
                }
              : t
          )
        );
        upsertLocalSession(resolvedSid, {
          replacePendingId: backendSessionId ? undefined : PENDING_SESSION_ID,
          title: derivedTitlesRef.current[resolvedSid] ?? firstTurnTitle,
          summary: res.memory_context.summary,
          turn_count: optimisticIndex,
          updated_at: doneAt,
        });
        await refreshSessionsAndHealth();
      } catch (err) {
        if (requestTokenRef.current !== myToken) return;
        setErrorMessage(err instanceof Error ? err.message : "Chat request failed.");
        setTurns((prev) =>
          prev.map((t, i) => (i === prev.length - 1 ? { ...t, isStreaming: false } : t))
        );
      } finally {
        if (requestTokenRef.current === myToken) {
          setIsSending(false);
        }
      }
      return;
    }

    const controller = new AbortController();
    abortControllerRef.current = controller;
    let streamSessionId = backendSessionId;

    try {
      await streamChat(
        { question, session_id: backendSessionId, preferences },
        {
          onSession: (ev) => {
            if (requestTokenRef.current !== myToken) return;
            streamSessionId = ev.session_id;
            deletedSessionIdsRef.current.delete(ev.session_id);
            if (firstTurnTitle && !derivedTitlesRef.current[ev.session_id]) {
              derivedTitlesRef.current[ev.session_id] = firstTurnTitle;
            }
            activeSessionIdRef.current = ev.session_id;
            setActiveSessionId(ev.session_id);
            writeSavedSessionId(ev.session_id);
            upsertLocalSession(ev.session_id, {
              replacePendingId: backendSessionId ? undefined : PENDING_SESSION_ID,
              title: derivedTitlesRef.current[ev.session_id] ?? firstTurnTitle,
              turn_count: optimisticIndex,
              updated_at: new Date().toISOString(),
            });
          },
          onMetadata: (ev) => {
            if (requestTokenRef.current !== myToken) return;
            setTurns((prev) =>
              prev.map((t, i) =>
                i === prev.length - 1
                  ? {
                      ...t,
                      standalone_question: ev.standalone_question,
                      sources: ev.sources,
                      source_chunk_ids: ev.sources.map((s) => s.chunk_id),
                    }
                  : t
              )
            );
          },
          onToken: (ev) => {
            if (requestTokenRef.current !== myToken) return;
            setTurns((prev) =>
              prev.map((t, i) =>
                i === prev.length - 1
                  ? { ...t, assistant: `${t.assistant}${ev.token}` }
                  : t
              )
            );
          },
          onMemory: (ev) => {
            if (requestTokenRef.current !== myToken) return;
            setSummary(ev.summary);
            setActiveFacts(ev.active_facts);
            if (streamSessionId) {
              upsertLocalSession(streamSessionId, {
                summary: ev.summary,
              });
            }
          },
          onError: (ev) => {
            if (requestTokenRef.current !== myToken) return;
            setErrorMessage(ev.detail || "Streaming error occurred.");
          },
          onDone: () => {
            if (requestTokenRef.current !== myToken) return;
            const doneAt = new Date().toISOString();
            setTurns((prev) =>
              prev.map((t, i) =>
                i === prev.length - 1 ? { ...t, isStreaming: false } : t
              )
            );
            if (streamSessionId) {
              upsertLocalSession(streamSessionId, {
                title: derivedTitlesRef.current[streamSessionId] ?? firstTurnTitle,
                turn_count: optimisticIndex,
                updated_at: doneAt,
              });
            }
          },
        },
        controller.signal
      );
      if (requestTokenRef.current === myToken) {
        await refreshSessionsAndHealth();
      }
    } catch (err) {
      if (requestTokenRef.current !== myToken) return;
      if (!(err instanceof DOMException && err.name === "AbortError")) {
        setErrorMessage(err instanceof Error ? err.message : "SSE stream failed.");
      }
      setTurns((prev) =>
        prev.map((t, i) => (i === prev.length - 1 ? { ...t, isStreaming: false } : t))
      );
    } finally {
      if (abortControllerRef.current === controller) {
        abortControllerRef.current = null;
      }
      if (requestTokenRef.current === myToken) {
        setIsSending(false);
      }
    }
  };

  return (
    <div className="relative flex h-screen w-screen overflow-hidden bg-[#212121] text-[#ECECEC]">
      <SessionSidebar
        isOpen={isSidebarOpen}
        sessions={sessions}
        activeSessionId={activeSessionId}
        isLoading={isLoadingSessions}
        onClose={() => setIsSidebarOpen(false)}
        onCreateSession={handleCreateSession}
        onSelectSession={loadSession}
        onRenameSession={handleRenameSession}
        onDeleteSession={handleDeleteSession}
        onRefreshSessions={refreshSessionsAndHealth}
      />

      <ChatPanel
        health={health}
        activeSessionId={activeSessionId === PENDING_SESSION_ID ? null : activeSessionId}
        activeSessionTitle={
          activeSessionId
            ? sessions.find((s) => s.session_id === activeSessionId)?.title ?? null
            : null
        }
        turns={turns}
        draftResetVersion={draftResetVersion}
        newChatSignal={newChatSignal}
        preferences={preferences}
        isStreamingEnabled={isStreamingEnabled}
        isSending={isSending}
        errorMessage={errorMessage}
        isSidebarOpen={isSidebarOpen}
        isMemoryOpen={isMemoryOpen}
        activeFactsCount={activeFacts.length}
        onToggleSidebar={() => setIsSidebarOpen((prev) => !prev)}
        onToggleStreaming={() => setIsStreamingEnabled((prev) => !prev)}
        onToggleMemory={() => setIsMemoryOpen((prev) => !prev)}
        onOpenPreferences={() => setIsPreferencesOpen(true)}
        onSendMessage={handleSendMessage}
        onStopStreaming={handleStopStreaming}
        onInspectSources={(sources, activeIdx) => {
          setInspectedSources(sources);
          setHighlightedSourceIndex(activeIdx);
        }}
      />

      <MemoryDrawer
        isOpen={isMemoryOpen}
        health={health}
        activeSessionId={activeSessionId === PENDING_SESSION_ID ? null : activeSessionId}
        summary={summary}
        activeFacts={activeFacts}
        turnCount={turns.length}
        onClose={() => setIsMemoryOpen(false)}
      />

      <PreferencesModal
        isOpen={isPreferencesOpen}
        preferences={preferences}
        onClose={() => setIsPreferencesOpen(false)}
        onSave={handleSavePreferences}
      />

      <SourcesModal
        sources={inspectedSources}
        highlightedIndex={highlightedSourceIndex}
        onClose={() => {
          setInspectedSources(null);
          setHighlightedSourceIndex(undefined);
        }}
      />
    </div>
  );
}
