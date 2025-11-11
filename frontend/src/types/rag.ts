// RAG Filesystem types

export interface RagFolder {
  id: string;
  agent_id: string;
  path: string;
  name: string;
  max_files_open: number;
  per_file_char_limit: number;
  source_instructions?: string;
  created_at: string;
  updated_at: string;
  file_count: number;
}

export interface RagFolderCreate {
  agent_id: string;
  path: string;
  name?: string;
  max_files_open?: number;
  per_file_char_limit?: number;
  source_instructions?: string;
}

export interface RagFolderUpdate {
  name?: string;
  max_files_open?: number;
  per_file_char_limit?: number;
  source_instructions?: string;
}

export interface RagFile {
  id: string;
  folder_id: string;
  path: string;
  filename: string;
  extension?: string;
  size_bytes?: number;
  mime_type?: string;
  content_hash?: string;
  created_at: string;
  updated_at: string;
  last_indexed_at?: string;
  chunk_count: number;
}

// Search types

export interface SearchQuery {
  query: string;
  agent_id?: string;
  source_types?: string[];
  limit?: number;
  semantic?: boolean;
  full_text?: boolean;
}

export interface SearchResult {
  id: string;
  source_type: 'rag_chunk' | 'journal_block' | 'message';
  title: string;
  snippet: string;
  created_at: string;
  score: number;
  metadata?: Record<string, any>;
}

export interface SearchResponse {
  results: SearchResult[];
  total: number;
  query: string;
}
