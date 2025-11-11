// Conversation and message types

export interface Conversation {
  id: string;
  agent_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface ConversationCreate {
  agent_id: string;
  title?: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  metadata?: Record<string, any>;
  created_at: string;
}

export interface ChatRequest {
  message: string;
}

export interface ChatResponse {
  user_message: Message;
  assistant_message: Message;
}
