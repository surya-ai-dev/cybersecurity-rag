import type {
  ChatRequest,
  ChatResponse,
  CreateSessionRequest,
  DeleteSessionResponse,
  HealthResponse,
  SessionDetailDTO,
  SessionSummaryDTO,
  SSEDoneEvent,
  SSEErrorEvent,
  SSEMemoryEvent,
  SSEMetadataEvent,
  SSESessionEvent,
  SSETokenEvent,
  StreamChatCallbacks,
} from "../types/api";

const RAW_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").trim().replace(/\/+$/, "");

function apiUrl(path: string): string {
  return `${RAW_BASE}${path}`;
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function parseErrorDetail(res: Response): Promise<string> {
  try {
    const data = (await res.json()) as { detail?: string };
    if (data && typeof data.detail === "string" && data.detail.trim()) {
      return data.detail;
    }
  } catch {
    // Fallback to status text when body is not JSON
  }
  return `HTTP ${res.status} ${res.statusText}`.trim();
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(apiUrl(path), {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    throw new ApiError(res.status, await parseErrorDetail(res));
  }
  return (await res.json()) as T;
}

export function fetchHealth(): Promise<HealthResponse> {
  return requestJson<HealthResponse>("/api/v1/health", { method: "GET" });
}

export function listSessions(limit = 20): Promise<SessionSummaryDTO[]> {
  return requestJson<SessionSummaryDTO[]>(`/api/v1/sessions?limit=${limit}`, {
    method: "GET",
  });
}

export function createSession(title?: string | null): Promise<SessionSummaryDTO> {
  const payload: CreateSessionRequest = title ? { title } : {};
  return requestJson<SessionSummaryDTO>("/api/v1/sessions", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function renameSession(
  sessionId: string,
  title: string
): Promise<SessionSummaryDTO> {
  return requestJson<SessionSummaryDTO>(
    `/api/v1/sessions/${encodeURIComponent(sessionId)}`,
    {
      method: "PATCH",
      body: JSON.stringify({ title }),
    }
  );
}

export function getSessionDetail(sessionId: string): Promise<SessionDetailDTO> {
  return requestJson<SessionDetailDTO>(
    `/api/v1/sessions/${encodeURIComponent(sessionId)}`,
    { method: "GET" }
  );
}

export function clearSession(sessionId: string): Promise<SessionSummaryDTO> {
  return requestJson<SessionSummaryDTO>(
    `/api/v1/sessions/${encodeURIComponent(sessionId)}/clear`,
    { method: "POST" }
  );
}

export async function deleteSession(sessionId: string): Promise<DeleteSessionResponse> {
  try {
    return await requestJson<DeleteSessionResponse>(
      `/api/v1/sessions/${encodeURIComponent(sessionId)}`,
      { method: "DELETE" }
    );
  } catch (err) {
    // Treat 404 on DELETE as already removed so stale/in-memory sessions don't fail deletion
    if (err instanceof ApiError && err.status === 404) {
      return { deleted: true, session_id: sessionId };
    }
    throw err;
  }
}

export function sendChat(req: ChatRequest): Promise<ChatResponse> {
  return requestJson<ChatResponse>("/api/v1/chat", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

function dispatchSSEBlock(rawBlock: string, callbacks: StreamChatCallbacks): void {
  const lines = rawBlock.split(/\r?\n/);
  let eventName = "message";
  const dataLines: string[] = [];

  for (const line of lines) {
    if (!line || line.startsWith(":")) continue;
    if (line.startsWith("event:")) {
      eventName = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }

  if (dataLines.length === 0) return;
  const rawJson = dataLines.join("\n");

  try {
    const parsed = JSON.parse(rawJson) as unknown;
    switch (eventName) {
      case "session":
        callbacks.onSession?.(parsed as SSESessionEvent);
        break;
      case "metadata":
        callbacks.onMetadata?.(parsed as SSEMetadataEvent);
        break;
      case "token":
        callbacks.onToken?.(parsed as SSETokenEvent);
        break;
      case "memory":
        callbacks.onMemory?.(parsed as SSEMemoryEvent);
        break;
      case "done":
        callbacks.onDone?.(parsed as SSEDoneEvent);
        break;
      case "error":
        callbacks.onError?.(parsed as SSEErrorEvent);
        break;
      default:
        break;
    }
  } catch (err) {
    callbacks.onError?.({
      detail: err instanceof Error ? `Malformed SSE payload: ${err.message}` : "Malformed SSE payload",
    });
  }
}

export async function streamChat(
  req: ChatRequest,
  callbacks: StreamChatCallbacks,
  signal?: AbortSignal
): Promise<void> {
  const res = await fetch(apiUrl("/api/v1/chat/stream"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(req),
    signal,
  });

  if (!res.ok) {
    throw new Error(await parseErrorDetail(res));
  }

  if (!res.body) {
    throw new Error("Streaming response body is unavailable.");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split(/\r?\n\r?\n/);
      buffer = blocks.pop() ?? "";

      for (const block of blocks) {
        if (block.trim()) {
          dispatchSSEBlock(block, callbacks);
        }
      }
    }

    buffer += decoder.decode();
    if (buffer.trim()) {
      dispatchSSEBlock(buffer, callbacks);
    }
  } finally {
    reader.releaseLock();
  }
}
