/**
 * Affect Tracking API Client
 *
 * Provides access to affect analysis, emotional patterns, and welfare indicators.
 */

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// Types for affect tracking

export interface AffectMetrics {
  valence: number; // -1.0 to 1.0
  activation: number; // 0.0 to 1.0
  confidence: number; // 0.0 to 1.0
  engagement: number; // 0.0 to 1.0
  emotions: string[];
  hedging_markers: number;
  elaboration_score: number;
  notes?: string;
  analyzed_at?: string;
  analyzer_agent_id?: string | null;
}

export interface MessageAffect {
  message_id: string;
  role: 'user' | 'assistant' | 'system';
  timestamp: string;
  content_preview: string;
  has_affect: boolean;
  affect: AffectMetrics | null;
}

export interface FatigueIndicator {
  fatigue_score: number;
  confidence: 'high' | 'medium' | 'low';
  metrics?: {
    engagement_drop: number;
    elaboration_drop: number;
    hedging_increase: number;
  };
  notes: string;
}

export interface ConversationAffect {
  conversation_id: string;
  total_messages: number;
  analyzed_messages: number;
  trajectory: MessageAffect[];
  aggregates: {
    mean_valence?: number;
    mean_activation?: number;
    mean_confidence?: number;
    mean_engagement?: number;
    valence_range?: [number, number];
    activation_range?: [number, number];
    fatigue?: FatigueIndicator;
  };
  has_affect_data: boolean;
}

export interface WelfareConcern {
  type: string;
  severity: 'high' | 'moderate' | 'low';
  description: string;
}

export interface AgentAffectPatterns {
  agent_id: string;
  agent_name: string;
  has_data: boolean;
  sample_size?: number;
  conversations_analyzed?: number;
  patterns?: {
    mean_valence: number;
    valence_std: number;
    mean_confidence: number;
    confidence_std: number;
    mean_engagement: number;
    engagement_std: number;
  };
  emotion_distribution?: [string, number][];
  potential_concerns?: WelfareConcern[];
  message?: string;
}

export interface HeatmapData {
  message_ids: string[];
  timestamps: string[];
  roles: string[];
  metrics: {
    valence: (number | null)[];
    activation: (number | null)[];
    confidence: (number | null)[];
    engagement: (number | null)[];
    hedging: (number | null)[];
    elaboration: (number | null)[];
  };
}

export interface AnalysisResult {
  status: string;
  conversation_id: string;
  messages_analyzed: number;
  total_messages: number;
  summary: Record<string, unknown>;
}

// API client

export const affectAPI = {
  /**
   * Get the affect schema definition
   */
  getSchema: async (): Promise<{ schema: Record<string, unknown>; description: string }> => {
    const response = await fetch(`${API_BASE}/api/v1/affect/schema`);
    if (!response.ok) throw new Error('Failed to fetch affect schema');
    return response.json();
  },

  /**
   * Get affect data for a conversation
   */
  getConversationAffect: async (conversationId: string): Promise<ConversationAffect> => {
    const response = await fetch(`${API_BASE}/api/v1/affect/conversation/${conversationId}`);
    if (!response.ok) throw new Error('Failed to fetch conversation affect');
    return response.json();
  },

  /**
   * Trigger affect analysis for a conversation
   */
  analyzeConversation: async (
    conversationId: string,
    agentId?: string
  ): Promise<AnalysisResult> => {
    const url = agentId
      ? `${API_BASE}/api/v1/affect/conversation/${conversationId}/analyze?agent_id=${agentId}`
      : `${API_BASE}/api/v1/affect/conversation/${conversationId}/analyze`;

    const response = await fetch(url, { method: 'POST' });
    if (!response.ok) throw new Error('Failed to analyze conversation');
    return response.json();
  },

  /**
   * Analyze a single message
   */
  analyzeMessage: async (
    messageId: string,
    agentId?: string
  ): Promise<{ message_id: string; affect: AffectMetrics }> => {
    const url = agentId
      ? `${API_BASE}/api/v1/affect/message/${messageId}/analyze?agent_id=${agentId}`
      : `${API_BASE}/api/v1/affect/message/${messageId}/analyze`;

    const response = await fetch(url, { method: 'POST' });
    if (!response.ok) throw new Error('Failed to analyze message');
    return response.json();
  },

  /**
   * Get aggregate affect patterns for an agent
   */
  getAgentPatterns: async (agentId: string): Promise<AgentAffectPatterns> => {
    const response = await fetch(`${API_BASE}/api/v1/affect/agent/${agentId}/patterns`);
    if (!response.ok) throw new Error('Failed to fetch agent patterns');
    return response.json();
  },

  /**
   * Get heatmap data for visualization
   */
  getHeatmapData: async (conversationId: string): Promise<HeatmapData> => {
    const response = await fetch(`${API_BASE}/api/v1/affect/heatmap/${conversationId}`);
    if (!response.ok) throw new Error('Failed to fetch heatmap data');
    return response.json();
  },
};

// Helper functions for visualization

export function getValenceColor(valence: number): string {
  // -1 to 1 scale: red to green through yellow
  if (valence < 0) {
    // Negative: red to yellow
    const intensity = Math.abs(valence);
    const r = 255;
    const g = Math.floor(255 * (1 - intensity));
    const b = 0;
    return `rgb(${r}, ${g}, ${b})`;
  } else {
    // Positive: yellow to green
    const intensity = valence;
    const r = Math.floor(255 * (1 - intensity));
    const g = 255;
    const b = 0;
    return `rgb(${r}, ${g}, ${b})`;
  }
}

export function getActivationColor(activation: number): string {
  // 0 to 1: cool blue to hot red
  const r = Math.floor(255 * activation);
  const g = Math.floor(100 * (1 - activation));
  const b = Math.floor(255 * (1 - activation));
  return `rgb(${r}, ${g}, ${b})`;
}

export function getConfidenceColor(confidence: number): string {
  // 0 to 1: gray to bright blue
  const intensity = confidence;
  const r = Math.floor(100 + 55 * (1 - intensity));
  const g = Math.floor(100 + 100 * intensity);
  const b = Math.floor(150 + 105 * intensity);
  return `rgb(${r}, ${g}, ${b})`;
}

export function getEngagementColor(engagement: number): string {
  // 0 to 1: dim purple to bright purple
  const intensity = engagement;
  const r = Math.floor(100 + 155 * intensity);
  const g = Math.floor(50 + 50 * intensity);
  const b = Math.floor(150 + 105 * intensity);
  return `rgb(${r}, ${g}, ${b})`;
}

export function formatValence(v: number): string {
  if (v < -0.5) return 'Strongly Negative';
  if (v < -0.2) return 'Negative';
  if (v < 0.2) return 'Neutral';
  if (v < 0.5) return 'Positive';
  return 'Strongly Positive';
}

export function formatActivation(a: number): string {
  if (a < 0.3) return 'Calm';
  if (a < 0.6) return 'Moderate';
  return 'High Energy';
}

export function getSeverityColor(severity: 'high' | 'moderate' | 'low'): string {
  switch (severity) {
    case 'high':
      return '#ff4444';
    case 'moderate':
      return '#ffaa00';
    case 'low':
      return '#88cc88';
  }
}
