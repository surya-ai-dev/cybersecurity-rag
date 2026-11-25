export interface HealthResponse {
  status: string;
  persistent_memory_enabled: boolean;
  summarization_enabled: boolean;
  long_term_memory_enabled: boolean;
  active_session_id: string | null;
}

export interface SourceChunkDTO {
  source_index: number;
  chunk_id: string;
  doc_id: string;
  title: string;
  section: string;
  page: number | string | null;
  score: number;
  text_preview: string;
}

export type DetailLevel = "Concise" | "Balanced" | "Deep Dive";

export type ResponseFormat =
  | "Structured Bullets & Tables"
  | "Step-by-Step"
  | "TL;DR First";

export type FocusLens =
  | "AI / Product Engineering"
  | "Security & Compliance"
  | "Hands-On Code";

export interface UserPreferences {
  detail_level: DetailLevel;
  response_format: ResponseFormat;
  focus_lens: FocusLens;
  custom_instructions?: string;
}

export interface ChatRequest {
  question: string;
  session_id?: string | null;
  preferences?: UserPreferences | null;
}

export interface MemoryFactDTO {
  fact_id: string;
  category: string;
  key: string;
  value: string;
  source_turn: number | null;
  confidence: number;
}

export interface MemoryContextDTO {
  session_id: string | null;
  summary: string;
  active_facts: MemoryFactDTO[];
  recent_turn_count: number;
}

export interface ChatResponse {
  session_id: string;
  question: string;
  standalone_question: string;
  answer: string;
  sources: SourceChunkDTO[];
  memory_context: MemoryContextDTO;
}

export interface TurnDTO {
  turn_index: number;
  user: string;
  assistant: string;
  standalone_question: string | null;
  source_chunk_ids: string[];
  timestamp: string | null;
}

export interface ChatTurnView extends TurnDTO {
  sources?: SourceChunkDTO[];
  isStreaming?: boolean;
}

export interface CreateSessionRequest {
  title?: string | null;
}

export interface SessionSummaryDTO {
  session_id: string;
  title: string;
  summary: string;
  turn_count: number;
  created_at: string;
  updated_at: string;
}

export interface SessionDetailDTO {
  session: SessionSummaryDTO;
  turns: TurnDTO[];
  active_facts: MemoryFactDTO[];
}

export interface DeleteSessionResponse {
  deleted: boolean;
  session_id: string;
}

export interface SSESessionEvent {
  session_id: string;
}

export interface SSEMetadataEvent {
  standalone_question: string;
  sources: SourceChunkDTO[];
}

export interface SSETokenEvent {
  token: string;
}

export interface SSEMemoryEvent {
  summary: string;
  active_facts: MemoryFactDTO[];
}

export interface SSEDoneEvent {
  ok: boolean;
}

export interface SSEErrorEvent {
  detail: string;
}

export interface StreamChatCallbacks {
  onSession?: (event: SSESessionEvent) => void;
  onMetadata?: (event: SSEMetadataEvent) => void;
  onToken?: (event: SSETokenEvent) => void;
  onMemory?: (event: SSEMemoryEvent) => void;
  onDone?: (event: SSEDoneEvent) => void;
  onError?: (event: SSEErrorEvent) => void;
}
