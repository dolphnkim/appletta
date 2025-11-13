// Agent types matching backend schema

export type AgentType = 'main' | 'memory' | 'tool' | 'reflection' | 'other';

export interface LLMConfig {
  reasoning_enabled: boolean;
  temperature: number;
  top_p: number;
  top_k: number;
  seed?: number;
  max_output_tokens_enabled: boolean;
  max_output_tokens: number;
}

export interface EmbeddingConfig {
  model_path: string;
  dimensions: number;
  chunk_size: number;
}

export interface Agent {
  id: string;
  name: string;
  description?: string;
  agent_type: AgentType;
  is_template: boolean;
  model_path: string;
  adapter_path?: string;
  system_instructions: string;
  llm_config: LLMConfig;
  embedding_config: EmbeddingConfig;
  created_at: string;
  updated_at: string;
}

export interface AgentCreate {
  name: string;
  description?: string;
  agent_type?: AgentType;
  is_template?: boolean;
  model_path: string;
  adapter_path?: string;
  system_instructions: string;
  llm_config: LLMConfig;
  embedding_config: EmbeddingConfig;
}

export interface AgentUpdate {
  name?: string;
  description?: string;
  agent_type?: AgentType;
  is_template?: boolean;
  model_path?: string;
  adapter_path?: string;
  system_instructions?: string;
  llm_config?: Partial<LLMConfig>;
  embedding_config?: Partial<EmbeddingConfig>;
}

export interface AgentFile {
  version: string;
  agent: {
    name: string;
    description: string;
    agent_type?: AgentType;
    model_path: string;
    adapter_path?: string;
    system_instructions: string;
    llm_config: LLMConfig;
    embedding_config: EmbeddingConfig;
  };
}

export interface FileItem {
  name: string;
  path: string;
  is_directory: boolean;
  size?: number;
  modified?: string;
}

export interface FileBrowserResponse {
  current_path: string;
  parent_path?: string;
  items: FileItem[];
}
