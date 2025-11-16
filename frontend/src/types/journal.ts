// Journal block types

export interface JournalBlock {
  id: string;
  agent_id: string;
  label: string;
  block_id: string;
  value: string;
  description?: string;
  read_only: boolean;
  editable_by_main_agent: boolean;
  editable_by_memory_agent: boolean;
  attached: boolean;
  always_in_context: boolean;
  created_at: string;
  updated_at: string;
}

export interface JournalBlockCreate {
  label: string;
  value: string;
  description?: string;
  read_only?: boolean;
  editable_by_main_agent?: boolean;
  editable_by_memory_agent?: boolean;
  attached?: boolean;
  always_in_context?: boolean;
}

export interface JournalBlockUpdate {
  label?: string;
  value?: string;
  description?: string;
  read_only?: boolean;
  editable_by_main_agent?: boolean;
  editable_by_memory_agent?: boolean;
  attached?: boolean;
  always_in_context?: boolean;
}
