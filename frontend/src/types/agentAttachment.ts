export interface AgentAttachment {
  id: string;
  agent_id: string;
  attached_agent_id: string;
  attached_agent_name: string | null;
  attachment_type: string;
  label: string | null;
  priority: number;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface AgentAttachmentCreate {
  agent_id: string;
  attached_agent_id: string;
  attachment_type: string;
  label?: string;
  priority?: number;
  enabled?: boolean;
}

export interface AgentAttachmentUpdate {
  label?: string;
  priority?: number;
  enabled?: boolean;
}
