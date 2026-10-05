// The shapes the API answers with. Kept in step with apps/api/schemas by hand.

export type User = {
  id: string;
  email: string;
  active_connection_id: string | null;
};

export type PaperStatus = "UPLOADED" | "PROCESSING" | "READY" | "FAILED";

export type Paper = {
  id: string;
  title: string;
  authors: string[];
  year: number | null;
  doi: string | null;
  page_count: number | null;
  original_filename: string;
  status: PaperStatus;
  processing_step: string | null;
  error_code: string | null;
  error: string | null;
  warnings: string[];
  needs_reindex: boolean;
  created_at: string;
  updated_at: string;
};

export type PaperDetail = Paper & { summary: string | null };

export type PaperPage = {
  items: Paper[];
  total: number;
  page: number;
  page_size: number;
};

export type Section = {
  id: string;
  parent_id: string | null;
  position: number;
  level: number;
  title: string;
  page: number;
};

export type IngestionRun = {
  step: string;
  attempt: number;
  status: "running" | "done" | "failed";
  started_at: string;
  finished_at: string | null;
  details: Record<string, unknown>;
  error: string | null;
};

export type Collection = {
  id: string;
  name: string;
  description: string | null;
  paper_ids: string[];
  created_at: string;
  updated_at: string;
};

export type Chat = {
  id: string;
  title: string | null;
  // Set when the session asks a whole collection; paper_ids is then what it holds now.
  collection_id: string | null;
  paper_ids: string[];
  source_count: number;
  created_at: string;
  updated_at: string;
};

export type Source = {
  marker: string;
  chunk_id: string;
  paper_id: string;
  paper_title: string;
  page: number;
  section_path: string[];
  snippet: string;
};

// How an answer was made: from the best passages, as a table of papers, or as a review across them.
export type AnswerMode = "factual" | "comparison" | "synthesis";
// What a question may ask for. auto: the kind is worked out from the question.
export type AskMode = "auto" | AnswerMode;

export type ComparisonCell = { text: string; markers: string[] };

export type Comparison = {
  columns: string[];
  rows: { paper_id: string; paper_title: string; cells: ComparisonCell[] }[];
};

export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Source[];
  mode: AnswerMode;
  table: Comparison | null;
  notice: string | null;
  created_at: string;
};

export type Retrieval = {
  message_id: string;
  trace_id: string | null;
  retrieval: Record<string, unknown> | null;
};

export type Chunk = {
  id: string;
  chunk_index: number;
  kind: string;
  text: string;
  section_path: string[];
  page_start: number;
  page_end: number;
  bboxes: Box[];
  token_count: number;
};

export type ChunkPage = { items: Chunk[]; total: number; page: number; page_size: number };

export type RagConfig = Record<string, string | number | boolean>;

export type Box = { page: number; bbox: [number, number, number, number] };

export type Passage = {
  id: string;
  paper_id: string;
  kind: string;
  text: string;
  section_path: string[];
  page_start: number;
  page_end: number;
  bboxes: Box[];
};

export type ConnectionKind = "gemini" | "bedrock" | "openai_compatible";

export type CapabilityCheck = {
  check: string;
  ok: boolean;
  error_code: string | null;
  message: string | null;
};

export type Connection = {
  id: string;
  kind: ConnectionKind;
  label: string;
  config: {
    models?: { answer?: string; fast?: string; embedding?: string };
    region?: string;
    base_url?: string;
  };
  secret_last4: string;
  capabilities: {
    checked_at: string;
    checks: CapabilityCheck[];
    usable: boolean;
    rerank_disabled: boolean;
  } | null;
  created_at: string;
  updated_at: string;
};

export type UsageRow = {
  connection_id: string | null;
  model: string;
  role: string;
  input_tokens: number;
  output_tokens: number;
};
